# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This is a MicroPython application for the [Pimoroni Presto](https://shop.pimoroni.com/products/presto) device (a Raspberry Pi RP2350-based touchscreen display) implementing a tiled Home Assistant dashboard, visually modeled on [compresto](https://git.hack-hro.de/kmohrf/compresto), built as an app on top of [TmOS](https://github.com/themissingcow/pimoroni-presto-tmos) (a vendored, MIT-licensed page-based OS/app framework — see `VENDORING.md`).

Code in this repo runs on-device under MicroPython, not CPython — even though `pyproject.toml` declares `requires-python = ">=3.13"`, that constraint only governs the host-side tooling environment (uv-managed venv used to run `mpremote`, `pytest`, etc.), not the code that gets deployed to the Presto itself. Do not assume standard CPython stdlib/library availability when writing device code; MicroPython's stdlib is a subset, and Presto-specific modules (`presto`, `picographics`, `picovector`, `touch`) only resolve on-device or under the test stubs in `tests/conftest.py`.

The device talks to Home Assistant **only over MQTT** (to an existing EMQX broker), never directly to HA's REST/WebSocket API — Node-RED (already running inside HA) bridges HA entities to/from a fixed MQTT topic contract defined in `dashboard/topics.py`. The firmware has no HA auth token and doesn't know HA entity IDs, only MQTT topic slugs.

## Licensing

This repo is licensed **AGPL-3.0-or-later** (see `LICENSE`, and `license = "AGPL-3.0-or-later"` in `pyproject.toml`), chosen because of the compresto-derived content below — don't relicense to something more permissive (e.g. MIT) without accounting for that.

[compresto](https://git.hack-hro.de/kmohrf/compresto) (Copyright (C) Konrad Mohrfeldt) is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0), not MIT like TmOS. No compresto source file has been vendored/copied into this repo (see `VENDORING.md`, which only lists TmOS and `umqtt.simple`), but several `dashboard/` modules port or adapt its design — exact color values, tile-grid sizing math, and the pub/sub state pattern — closely enough to be derivative work under AGPL-3.0. Each affected file carries a header comment pointing back here:

- `dashboard/grid.py` — tile-grid sizing math
- `dashboard/palette.py` — color constants, ported verbatim
- `dashboard/state_store.py` — `on_update`/`_dispatch_event` pub/sub pattern
- `dashboard/tiles.py` — `ValueTile`/`DateTimeTile` behavior

`tmos*.py` and `umqtt/simple.py` are vendored from separately MIT-licensed upstreams (per `VENDORING.md`) and are NOT covered by this repo's own `LICENSE` — their original MIT terms still apply to those files.

## Tooling and commands

- Host dependencies (`mpremote`, `pytest`) are managed with `uv`:
  - `uv sync` — install/update the host-side dev environment
  - `uv run pytest` — run the host-side test suite (see "Testing" below)
- `mpremote` is the only supported way to talk to the physical device over USB/serial:
  - `mpremote connect list` — list connected serial devices
  - `mpremote cp <file> :<file>` / `mpremote cp -r <dir> :` — copy file(s) to the device
  - `mpremote run <file>.py` — execute a script on-device without persisting it to flash (fast iteration; does not overwrite `main.py`)
  - `mpremote reset` — soft-reset the device (re-runs whatever `main.py` is currently on flash)
  - `mpremote exec "..."` — run a one-off expression on-device
  - When multiple devices might be connected, target explicitly: `mpremote connect <PORT> ...`
- **`rshell` is deliberately not a dependency.** It pulls in an abandoned `pyreadline` 2.1 on Windows that hard-crashes on import under Python 3.13 (`collections.Callable` was removed), which in turn breaks `pytest` itself (its readline workaround only catches `ImportError`, not this `AttributeError`). Don't re-add it without fixing that first.
- **The device already has its own `secrets.py`** (WiFi credentials from prior experimentation) that is intentionally *not* mirrored in this repo (gitignored, and no local copy exists — see `secrets.example.py` for the expected shape). Do not `mpremote cp` a placeholder over the device's real `secrets.py`; MQTT credentials need adding to the existing on-device file directly, not generated fresh.

## Testing

- `uv run pytest` runs the full host-side suite (`tests/`) under desktop CPython — no device needed. **Always run it via `uv run pytest`, not bare `pytest`**, and note `testpaths = ["tests"]` in `pyproject.toml` deliberately scopes discovery — without it, path-less invocations walk the whole rootdir including `.venv/` and hang.
- `tests/conftest.py` stubs `presto`/`picographics`/`picovector`/`touch`/`ntptime` into `sys.modules` (adapted from TmOS's own `tests/conftest.py`) so `tmos.py`/`tmos_ui.py` and everything in `dashboard/` can be imported and exercised on desktop Python. Use the `mock_presto_module`/`mock_touch_factory` fixtures it provides rather than re-stubbing hardware yourself.
- Pure-logic modules (`dashboard/grid.py`, `palette.py`, `state_store.py`, `topics.py`) are fully unit-testable this way. Anything doing real socket I/O (MQTT) or real PicoGraphics rendering is not — those need on-device verification via `mpremote run`.
- **Passing host tests are not evidence the code runs on MicroPython** — they only prove the logic is correct against CPython + stubs. Before trusting a new module, `mpremote cp` it to the device and confirm it actually imports/executes there (see `scripts/device_smoke_test.py` for the pattern: import the module, print/exercise something from it, catch import errors early). This project has already caught real MicroPython-vs-CPython/TmOS-API gaps (wrong `full_res` default producing a 240x240 not 480x480 display, `Theme`'s automatic dpi-scaling silently doubling naively-set pixel values) that no amount of host-side testing alone would have surfaced.

## Architecture

- `tmos.py`, `tmos_ui.py`, `tmos_apps.py`, `tmos_themes.py` — vendored TmOS, unmodified. Do not hand-edit; re-vendor per `VENDORING.md` instead so diffs stay reviewable.
- `umqtt/simple.py` — vendored `umqtt.simple` (deliberately not `umqtt.robust` — its blocking `reconnect()` retry loop would stall TmOS's single-threaded cooperative asyncio run loop).
- `dashboard/` — this project's own app code, layered on top of TmOS:
  - `grid.py` — tile-grid math. **16-column base grid**, not compresto's original 4 — a `STANDARD_SPAN`-cell (4) tile reproduces compresto's original 114px visual tile size, but the finer base grid lets the systray occupy a properly slim, grid-aligned row instead of being forced to be a full tile tall. See the "Grid granularity" section of the project plan for the reasoning.
  - `palette.py` — compresto's exact color constants (ported verbatim) plus `PenCache` (lazy `display.create_pen()` memoization) and `color_for_thresholds()`.
  - `theme.py` — `CompressoTheme(DefaultTheme)`, giving TmOS's own native chrome (systray) a look consistent with the tile grid. Overrides `setup()` to pin `padding`/`systray_height` to explicit final pixel values *after* calling `super().setup()`, rather than setting raw class attributes — those two properties are in `Theme._dpi_scaled_sizes` and get silently multiplied by `dpi_scale_factor` (2, given this app's forced `full_res=True`) otherwise.
  - `state_store.py` — keyed pub/sub (`DashboardState`), adapted from compresto's `on_update`/`_dispatch_event` pattern. Keys are `"{domain}/{slug}"`, matching the MQTT topic contract's addressing.
  - `topics.py` — the MQTT topic/payload contract. Single source of truth for topic strings and payload shapes; `mqtt_client.py` and tile code both import from here rather than hand-building either.
  - `icons.py` — flattened vector icon path data (currently just the mdiHomeAssistant glyph). `picovector.Polygon.path()` on-device only accepts straight-line points, not SVG path syntax, so curved icons are pre-flattened host-side by `scripts/flatten_icon.py` and checked in as point lists here.
  - `splash.py` — the boot splash screen (icon + label), drawn directly to `os.display` by `main.py` right after `OS()` construction and before `os.boot()`'s blocking wifi/NTP connect, so something shows immediately instead of a blank screen. Needs no explicit teardown — `DashboardPage`'s first tick fully repaints over it.
  - (in progress) `modal.py`, `tiles.py`, `page.py`, `app.py`, `mqtt_client.py` — see the project plan for their designs before implementing against them.
- `config.py` (not yet created) — declarative tile/entity registry; addresses tiles using `dashboard.grid`'s 16-column coordinate system (a "standard" tile is `colspan=4, rowspan=4`).
- This app always boots with `full_res=True` (`OS(layers=1, full_res=True)`) — every `dashboard.grid` constant is tuned for a 480px-wide display; the TmOS default (`full_res=False`, 240x240) would make `GAP=8` dominate a ~7.5px base cell.
