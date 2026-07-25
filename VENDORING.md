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
