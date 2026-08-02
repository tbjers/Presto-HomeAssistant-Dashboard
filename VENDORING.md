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
- `dashboard/icons.py` (mdi-home-assistant, mdi-power)
- `dashboard/weather_icons.py` (mdi-weather-\*, see `scripts/flatten_weather_icons.py`'s
  `CONDITION_TO_ICON` for the condition -> icon mapping)

Re-vendor: update the embedded `d` string constant(s) in the relevant `scripts/flatten_*.py` from the
upstream repo's `svg/<name>.svg` files, then re-run that script (see each script's own docstring for
the exact command).

## Fonts (dashboard/assets/*.af)

Source: [Atkinson Hyperlegible](https://github.com/google/fonts/tree/main/ofl/atkinsonhyperlegible)
(Copyright 2020 Braille Institute of America, Inc.) and
[Inter](https://github.com/google/fonts/tree/main/ofl/inter) (Copyright 2020 The Inter Project
Authors), both licensed under the SIL Open Font License 1.1 — license text bundled alongside each
`.af` as `dashboard/assets/OFL-<name>.txt`, per the OFL's redistribution requirement.

Not verbatim copies — PicoVector can't load `.ttf`/`.otf` directly, only Pimoroni's own binary `.af`
("Alright Fonts") vector-font format, so each source TTF is converted host-side with the `afinate`
tool from [lowfatcode/alright-fonts](https://github.com/lowfatcode/alright-fonts) (MIT-licensed;
requires `freetype-py`, not itself vendored into or a runtime dependency of this repo — see
dashboard/theme.py's module docstring for how CompressoTheme loads the resulting files).

Files:
- `dashboard/assets/atkinson-hyperlegible.af`, converted from
  `ofl/atkinsonhyperlegible/AtkinsonHyperlegible-Regular.ttf`
- `dashboard/assets/inter.af`, converted from `ofl/inter/Inter[opsz,wght].ttf` (a variable font —
  afinate/FreeType extract outlines at its default instance, i.e. Inter Regular, wght=400)

Re-vendor:
```
uv run --with freetype-py python afinate --font <path-to.ttf> --quality medium --format af <out.af>
```
(`afinate` and its `python_alright_fonts` package are fetched from the alright-fonts repo above —
not present in this repo — since they're only ever needed for this one-off regeneration.)
