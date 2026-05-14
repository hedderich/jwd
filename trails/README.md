# Adding Routes

Drop GPX files into the folder matching the activity type.

## Naming

Prefix the filename with a date for automatic sorting:

```
2026-05-14 Berlin ride.gpx
```

## Descriptions

Descriptions can come from two places:

1. **Inside the GPX file** - the `<desc>` element inside `<trk>`:
   ```xml
   <trk>
     <name>Berlin ride</name>
     <desc>Description here</desc>
     ...
   </trk>
   ```

2. **A companion `.md` file** with the same name as the GPX:
   ```
   trails/cycling/2026-05-14 Berlin ride.gpx
   trails/cycling/2026-05-14 Berlin ride.md
   ```

If both exist the `.md` file takes priority.
