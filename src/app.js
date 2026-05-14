/* jwd */
(function () {
  "use strict";

  const STYLE = "https://tiles.openfreemap.org/styles/positron";
  const app = document.getElementById("app");
  let data = null, maps = [], dMap = null;

  function color(type) {
    if (type === "hiking" || type === "walking") return "#1b4965";
    if (type === "running" || type === "trail running") return "#c4621a";
    return "#1a5c3a";
  }

  function route() {
    const h = location.hash || "#/";
    return h.startsWith("#/trail/") ? { v: "detail", slug: h.slice(8) } : { v: "list" };
  }

  async function load() {
    if (data) return data;
    try {
      const res = await fetch("data/trails.json");
      if (!res.ok) throw new Error(res.status);
      data = await res.json();
    } catch (e) {
      app.innerHTML = `<div class="wrap"><p>Failed to load routes. Please try again later.</p></div>`;
      throw e;
    }
    return data;
  }

  function cleanup() {
    maps.forEach((m) => m.remove()); maps = [];
    if (dMap) { dMap.remove(); dMap = null; }
  }

  function addTrail(map, t, thick) {
    const coords = t.coordinates;
    map.addSource("trail", {
      type: "geojson",
      data: { type: "Feature", geometry: { type: "LineString", coordinates: coords } },
    });
    map.addLayer({
      id: "trail-cas", type: "line", source: "trail",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": color(t.type), "line-width": thick ? 8 : 6, "line-opacity": 0.18 },
    });
    map.addLayer({
      id: "trail-line", type: "line", source: "trail",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": color(t.type), "line-width": thick ? 4 : 3 },
    });
    if (thick && coords.length >= 2) {
      const start = coords[0];
      const end = coords[coords.length - 1];
      const mkEl = (svg) => {
        const el = document.createElement("div");
        el.innerHTML = svg;
        return el;
      };
      const c = color(t.type);
      const startSvg = `<svg width="28" height="28" viewBox="0 0 28 28"><circle cx="14" cy="14" r="12" fill="#fff" stroke="${c}" stroke-width="2.5"/><polygon points="11,8 11,20 21,14" fill="${c}"/></svg>`;
      const endSvg = `<svg width="28" height="28" viewBox="0 0 28 28"><circle cx="14" cy="14" r="12" fill="#fff" stroke="${c}" stroke-width="2.5"/><rect x="9" y="9" width="10" height="10" rx="1" fill="${c}"/></svg>`;
      new maplibregl.Marker({ element: mkEl(startSvg), anchor: "center" }).setLngLat(start).addTo(map);
      new maplibregl.Marker({ element: mkEl(endSvg), anchor: "center" }).setLngLat(end).addTo(map);
    }
  }

  // --- LIST ---
  function renderList(trails) {
    cleanup();
    app.innerHTML = `<div class="wrap"><div class="grid"></div></div>`;
    const grid = app.querySelector(".grid");

    if (!trails.length) { grid.innerHTML = "<p>No routes yet.</p>"; return; }

    trails.forEach((t) => {
      const el = document.createElement("a");
      el.href = `#/trail/${t.slug}`;
      el.className = "card";
      el.innerHTML = `
        <div class="card-map" id="m-${t.slug}"></div>
        <div class="card-body">
          <h3>${t.name}</h3>
          <div class="card-meta">
            ${t.date ? `<span class="pill muted">${t.date}</span>` : ""}
            <span class="pill type-${t.type}">${t.type}</span>
            <span class="pill muted">${t.length_km} km</span>
            <span class="pill muted">↑ ${t.elevation_gain_m} Hm</span>
            <span class="pill muted">${t.est_time}</span>
          </div>
        </div>`;
      grid.appendChild(el);
    });

    const obs = new IntersectionObserver((es) => {
      es.forEach((e) => {
        if (!e.isIntersecting) return;
        const t = trails.find((x) => x.slug === e.target.id.slice(2));
        if (t) initThumb(e.target, t);
        obs.unobserve(e.target);
      });
    }, { rootMargin: "300px" });
    grid.querySelectorAll(".card-map").forEach((el) => obs.observe(el));
  }

  function initThumb(el, t) {
    if (!t.bounds) return;
    const m = new maplibregl.Map({
      container: el, style: STYLE,
      bounds: [[t.bounds[1], t.bounds[0]], [t.bounds[3], t.bounds[2]]],
      fitBoundsOptions: { padding: 40 },
      interactive: false, attributionControl: false,
    });
    m.on("load", () => addTrail(m, t, false));
    maps.push(m);
  }

  // --- DETAIL ---
  function renderDetail(t) {
    cleanup();
    if (!t) { app.innerHTML = `<div class="wrap"><p>Not found. <a href="#/">Back</a></p></div>`; return; }

    const hasProfile = t.elevation_profile && t.elevation_profile.length > 2;
    app.innerHTML = `
      <div class="detail-map" id="dmap"></div>
      <div class="wrap detail-body">
        <a href="#/" class="back" aria-label="Back to all routes">← All routes</a>
        <h1>${t.name}</h1>
        ${t.date ? `<p class="detail-date">${t.date}</p>` : ""}
        ${t.description ? `<p class="desc">${t.description}</p>` : ""}
        <div class="stats">
          <div class="stat"><strong>${t.length_km} <span class="unit">km</span></strong><small>Distance</small></div>
          <div class="stat"><strong>↑ ${t.elevation_gain_m} <span class="unit">m</span></strong><small>Ascent</small></div>
          <div class="stat"><strong>↓ ${t.elevation_loss_m} <span class="unit">m</span></strong><small>Descent</small></div>
          <div class="stat"><strong>${t.est_time}</strong><small>Est. time</small></div>
        </div>
        ${hasProfile ? `<div class="profile" id="prof"></div>` : ""}
        <div class="actions">
          <a href="gpx/${t.slug}.gpx" download class="dl-btn" role="button" style="--btn-color:${color(t.type)}">↓ Download GPX</a>
          ${t.link ? `<a href="${t.link}" target="_blank" rel="noopener noreferrer" class="dl-btn secondary" role="button" style="--btn-color:${color(t.type)}">${t.link_text || "Open route"} ↗</a>` : ""}
        </div>
      </div>`;

    dMap = new maplibregl.Map({
      container: "dmap", style: STYLE,
      bounds: [[t.bounds[1], t.bounds[0]], [t.bounds[3], t.bounds[2]]],
      fitBoundsOptions: { padding: 70 },
    });
    dMap.addControl(new maplibregl.NavigationControl(), "top-right");
    dMap.on("load", () => addTrail(dMap, t, true));

    if (hasProfile) drawProfile(t);
  }

  function drawProfile(t) {
    const box = document.getElementById("prof");
    if (!box) return;
    const pts = t.elevation_profile, W = 800, H = 80;
    const ds = pts.map((p) => p[0]), es = pts.map((p) => p[1]);
    const minE = t.min_elevation_m != null ? t.min_elevation_m : Math.min(...es);
    const maxE = t.max_elevation_m != null ? t.max_elevation_m : Math.max(...es);
    const maxD = Math.max(...ds) || 1;
    const padTop = 14, padBot = 14;
    const x = (d) => (d / maxD) * W;
    const y = (e) => padTop + (1 - (e - minE) / (maxE - minE || 1)) * (H - padTop - padBot);

    let path = `M${x(ds[0])},${y(es[0])}`;
    for (let i = 1; i < pts.length; i++) path += `L${x(ds[i])},${y(es[i])}`;
    const area = path + `L${W},${H}L0,${H}Z`;
    const c = color(t.type);

    box.innerHTML = `
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <defs><linearGradient id="eg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${c}" stop-opacity="0.2"/>
          <stop offset="100%" stop-color="${c}" stop-opacity="0.02"/>
        </linearGradient></defs>
        <path d="${area}" fill="url(#eg)"/>
        <path d="${path}" fill="none" stroke="${c}" stroke-width="2" vector-effect="non-scaling-stroke"/>
      </svg>
      <div class="profile-labels">
        <span class="profile-y-max">${Math.round(maxE)} m</span>
        <span class="profile-y-min">${Math.round(minE)} m</span>
        <span class="profile-x-end">${t.length_km} km</span>
      </div>`;
  }

  async function go() {
    const r = route();
    const trails = await load();
    if (r.v === "detail") renderDetail(trails.find((t) => t.slug === r.slug));
    else renderList(trails);
    window.scrollTo(0, 0);
  }

  window.addEventListener("hashchange", go);
  go();
})();
