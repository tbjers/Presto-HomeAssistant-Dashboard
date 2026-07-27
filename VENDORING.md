# Vendored dependencies

Files below are copied verbatim from upstream and deployed to the device as-is.
Do not hand-edit them — patch by re-vendoring at a newer commit instead, so diffs
stay reviewable.

## TmOS

Source: https://github.com/themissingcow/pimoroni-presto-tmos
Pinned commit: `24c0a3fb75659993bd4df484b1f5f16985aef9a8` (`main`)

Files:
- `tmos.py`
- `tmos_ui.py`
- `tmos_apps.py`
- `tmos_themes.py`

Re-vendor:
```
COMMIT=<new-sha>
for f in tmos.py tmos_ui.py tmos_apps.py tmos_themes.py; do
  curl -sf -o "$f" "https://raw.githubusercontent.com/themissingcow/pimoroni-presto-tmos/$COMMIT/src/$f"
done
```
Then update the pinned commit above and diff against git history before committing.

## umqtt.simple

Source: https://github.com/micropython/micropython-lib
Pinned commit: `0400c5683028417897a7e071df8350e2d4746b74` (`master`)

Files:
- `umqtt/simple.py`

Re-vendor:
```
COMMIT=<new-sha>
curl -sf -o umqtt/simple.py "https://raw.githubusercontent.com/micropython/micropython-lib/$COMMIT/micropython/umqtt.simple/umqtt/simple.py"
```

Deliberately **not** `umqtt.robust` — see the "MQTT client" decision in
`dashboard/mqtt_client.py`'s module docstring / the project plan for why (its
`reconnect()` blocks the whole cooperative asyncio loop on retry).

## MDI icons (dashboard/icons.py, dashboard/weather_icons.py)

Source: https://github.com/Templarian/MaterialDesign (Apache-2.0)

Not verbatim copies like the other entries above — `picovector.Polygon.path()` can't parse SVG path
syntax, so each glyph's `d` attribute is flattened host-side into straight-line points (see
`scripts/flatten_icon.py`/`scripts/flatten_weather_icons.py`, which embed the source `d` strings
copied as-is from the upstream repo). Listed here anyway since `dashboard/weather_icons.py` bakes in
15 icons — a bigger vendored-asset footprint than `icons.py`'s single glyph — so it's worth tracking
where they came from and how to regenerate them if MDI's glyphs change:

Files:
- `dashboard/icons.py` (mdi-home-assistant)
- `dashboard/weather_icons.py` (mdi-weather-\*, see `scripts/flatten_weather_icons.py`'s
  `CONDITION_TO_ICON` for the condition -> icon mapping)

Re-vendor: update the embedded `d` string constant(s) in the relevant `scripts/flatten_*.py` from the
upstream repo's `svg/<name>.svg` files, then re-run that script (see each script's own docstring for
the exact command).
