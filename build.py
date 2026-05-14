#!/usr/bin/env python3
"""Build script for jwd: discovers GPX files, extracts metadata, assembles dist/."""

import glob
import html as html_mod
import json
import math
import os
import re
import shutil
import unicodedata

import gpxpy


def slugify(filename):
    """Derive URL-safe slug from GPX filename."""
    name = os.path.splitext(os.path.basename(filename))[0]
    # Normalize unicode, decompose accents, drop combining marks
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    # Replace any non-alphanumeric with hyphens
    name = re.sub(r"[^a-z0-9]+", "-", name)
    # Collapse multiple hyphens, strip leading/trailing
    name = re.sub(r"-+", "-", name).strip("-")
    return name


def simplify_coords(coords, max_points=200):
    """Keep every Nth point to stay under max_points for rendering."""
    if len(coords) <= max_points:
        return coords
    step = math.ceil(len(coords) / max_points)
    simplified = coords[::step]
    # Always include the last point
    if simplified[-1] != coords[-1]:
        simplified.append(coords[-1])
    return simplified


def _filtered_elevation(elevations, threshold=3):
    """Calculate gain/loss with a threshold to filter GPS noise."""
    if len(elevations) < 2:
        return 0, 0
    gain = 0
    loss = 0
    ref = elevations[0]
    for ele in elevations[1:]:
        diff = ele - ref
        if diff > threshold:
            gain += diff
            ref = ele
        elif diff < -threshold:
            loss += abs(diff)
            ref = ele
    return round(gain), round(loss)


def extract_trail(gpx_path, type_override=None, desc_override=None):
    """Parse a GPX file and return trail metadata dict."""
    with open(gpx_path, "r", encoding="utf-8") as f:
        raw_content = f.read()

    # Try to extract BRouter's "filtered ascend" from XML comment
    brouter_ascend = None
    m = re.search(r"filtered ascend\s*=\s*(\d+)", raw_content)
    if m:
        brouter_ascend = int(m.group(1))

    brouter_time_min = None
    m = re.search(r"time=(\d+)h\s*(\d+)m", raw_content)
    if m:
        brouter_time_min = int(m.group(1)) * 60 + int(m.group(2))

    gpx = gpxpy.parse(raw_content)

    slug = slugify(gpx_path)

    # Extract date: filename pattern YYYY-MM-DD, then GPX metadata, then trackpoint time
    trail_date = None
    dm = re.match(r"(\d{4}-\d{2}-\d{2})", os.path.basename(gpx_path))
    if dm:
        trail_date = dm.group(1)
    elif gpx.time:
        trail_date = gpx.time.strftime("%Y-%m-%d")
    else:
        for track in gpx.tracks:
            for seg in track.segments:
                if seg.points and seg.points[0].time:
                    trail_date = seg.points[0].time.strftime("%Y-%m-%d")
                    break
            if trail_date:
                break

    # Get name: prefer track name, then metadata name, then filename
    name = None
    trail_type = type_override or "cycling"  # folder overrides GPX <type>
    description = desc_override or ""

    link = None
    link_text = None

    if gpx.tracks:
        track = gpx.tracks[0]
        name = track.name
        if not type_override and track.type:
            trail_type = track.type.lower()
        if not desc_override and track.description:
            description = track.description
        if track.link:
            link = track.link
            link_text = track.link_text or None

    if not name and gpx.name:
        name = gpx.name
    if not name:
        name = slug.replace("-", " ").title()

    # Strip leading date from name if date was already extracted
    if trail_date and name:
        name = re.sub(r"^\d{4}-\d{2}-\d{2}\s*[-–—]?\s*", "", name).strip()

    if not description and not desc_override and gpx.description:
        description = gpx.description

    # Collect all points from all tracks/segments
    all_points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                all_points.append(point)

    # Fallback: if no tracks, try routes (BRouter exports may use <rte>)
    if not all_points and gpx.routes:
        route = gpx.routes[0]
        if not name and route.name:
            name = route.name
        if not description and route.description:
            description = route.description
        for point in route.points:
            all_points.append(point)

    if not all_points:
        return None

    # Compute metrics using gpxpy
    length_3d = gpx.length_3d() or gpx.length_2d() or 0
    length_km = round(length_3d / 1000, 2)

    # Filtered elevation gain/loss using threshold to ignore GPS noise
    elevations_raw = [p.elevation for p in all_points if p.elevation is not None]
    if brouter_ascend is not None:
        elevation_gain_m = brouter_ascend
        _, elevation_loss_m = _filtered_elevation(elevations_raw, threshold=5)
    else:
        elevation_gain_m, elevation_loss_m = _filtered_elevation(elevations_raw, threshold=5)

    elevations = [p.elevation for p in all_points if p.elevation is not None]
    min_elevation_m = round(min(elevations)) if elevations else None
    max_elevation_m = round(max(elevations)) if elevations else None

    # Bounding box
    bounds = gpx.get_bounds()
    bbox = [bounds.min_latitude, bounds.min_longitude, bounds.max_latitude, bounds.max_longitude] if bounds else None

    # Coordinates for GeoJSON rendering (lon, lat)
    coords = [[round(p.longitude, 6), round(p.latitude, 6)] for p in all_points]
    coords_simplified = simplify_coords(coords)

    # Elevation profile data (distance_km, elevation_m) - simplified
    elevation_profile = []
    if elevations:
        cumulative_dist = 0
        prev_point = all_points[0]
        step = max(1, len(all_points) // 100)
        for i in range(0, len(all_points), step):
            p = all_points[i]
            if i > 0:
                cumulative_dist += p.distance_3d(prev_point) or p.distance_2d(prev_point) or 0
            if p.elevation is not None:
                elevation_profile.append([round(cumulative_dist / 1000, 2), round(p.elevation)])
            prev_point = p

    # Cycling: base 20 km/h + 1 min per 10m climbing
    # Running: base 10 km/h + 1 min per 10m climbing
    # Hiking: base 5 km/h + 1 min per 10m ascent
    if trail_type in ("hiking", "walking"):
        est_minutes = round((length_km / 5 + (elevation_gain_m / 10) / 60) * 60)
    elif trail_type in ("running", "trail running"):
        est_minutes = round((length_km / 10 + (elevation_gain_m / 10) / 60) * 60)
    elif brouter_time_min is not None:
        est_minutes = brouter_time_min
    else:
        est_minutes = round((length_km / 20 + (elevation_gain_m / 10) / 60) * 60)
    if est_minutes >= 60:
        est_time = f"{est_minutes // 60}:{est_minutes % 60:02d} h"
    else:
        est_time = f"0:{est_minutes:02d} h"

    return {
        "slug": slug,
        "name": html_mod.escape(name),
        "date": trail_date,
        "description": html_mod.escape(description) if description else "",
        "type": trail_type,
        "link": link,
        "link_text": html_mod.escape(link_text) if link_text else None,
        "length_km": length_km,
        "elevation_gain_m": elevation_gain_m,
        "elevation_loss_m": elevation_loss_m,
        "min_elevation_m": min_elevation_m,
        "max_elevation_m": max_elevation_m,
        "est_time": est_time,
        "bounds": bbox,
        "coordinates": coords_simplified,
        "elevation_profile": elevation_profile,
    }


def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    trails_dir = os.path.join(project_root, "trails")
    src_dir = os.path.join(project_root, "src")
    dist_dir = os.path.join(project_root, "dist")

    # Clean and create dist
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    os.makedirs(dist_dir)
    os.makedirs(os.path.join(dist_dir, "data"))
    os.makedirs(os.path.join(dist_dir, "gpx"))

    # Copy static source files to dist
    for filename in os.listdir(src_dir):
        src_path = os.path.join(src_dir, filename)
        if os.path.isfile(src_path):
            shutil.copy2(src_path, dist_dir)

    # Discover and process GPX files
    # Supports: trails/*.gpx (type from GPX or default cycling)
    #           trails/<type>/*.gpx (type from folder name)
    #           companion .md file for description (same name as .gpx)
    VALID_TYPES = {"cycling", "running", "hiking", "walking"}
    gpx_files = []

    # Root-level GPX files
    for f in sorted(glob.glob(os.path.join(trails_dir, "*.gpx"))):
        gpx_files.append((f, None))

    # Type subfolders
    for entry in sorted(os.listdir(trails_dir)):
        subdir = os.path.join(trails_dir, entry)
        if os.path.isdir(subdir) and entry.lower() in VALID_TYPES:
            for f in sorted(glob.glob(os.path.join(subdir, "*.gpx"))):
                gpx_files.append((f, entry.lower()))

    trails = []

    for gpx_path, folder_type in gpx_files:
        print(f"Processing: {os.path.basename(gpx_path)}")

        # Check for companion .md description file
        md_path = os.path.splitext(gpx_path)[0] + ".md"
        desc_override = None
        if os.path.isfile(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                desc_override = f.read().strip()

        trail = None
        try:
            trail = extract_trail(gpx_path, type_override=folder_type, desc_override=desc_override)
        except Exception as e:
            print(f"  ERROR: {e}, skipping.")
            continue
        if trail:
            trails.append(trail)
            # Copy GPX file for download
            slug = trail["slug"]
            shutil.copy2(gpx_path, os.path.join(dist_dir, "gpx", f"{slug}.gpx"))
        else:
            print(f"  WARNING: No track points found, skipping.")

    # Write trails.json (sorted by date, newest first; undated trails last)
    trails.sort(key=lambda t: t["date"] or "0000-00-00", reverse=True)
    trails_json_path = os.path.join(dist_dir, "data", "trails.json")
    with open(trails_json_path, "w", encoding="utf-8") as f:
        json.dump(trails, f, ensure_ascii=False)

    print(f"\nBuild complete: {len(trails)} trail(s) → dist/")


if __name__ == "__main__":
    main()
