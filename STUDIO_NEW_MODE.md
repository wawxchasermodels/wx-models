# Adding a Studio mode (frames always match Map)
1. Every mode draws into the same two canvases: `#cv` (9:16, 1080x1920 backing, or a 2x multiple) and `#ch` (16:9, 1920x1080 or 2x). Never create new frame canvases or size them yourself.
2. Sizing lives only in `fitFrames()` in tools/fast/site/studio.js. A mode is a body class named `<name>mode` (e.g. `obsmode`, `passmode`, `wafcmode`). fitFrames takes every `*mode` class off while it measures the Map layout, then pads or caps the mode panel (`#mgp`) and keeps the frame headers at Map's height, so the frames land on Map's exact box. Map's real layout is also remembered per window size (localStorage `studio:mapfit:WxH`).
3. Add the mode to the `#smode` switch and to `MODES_OK` in studio.js; `setMode()` must call `fitFrames()` after the class change, and `saveMode()` puts it in the address (`?smode=`) so a refresh keeps it.
4. Controls the mode hides: hide them with CSS under `body.<name>mode`; do not change frame sizes.
5. Guards (run automatically by deploy_prod_src.sh with PV=<preview>, on the preview and on production, auto-rollback on production failure):
   - /workspace/studio_refresh_qa/layout_test.py: walks every `#smode` option, every Observations layer chip and every model in the Runs menu, and fails if either frame differs from Map by more than 1 px (also after a refresh straight into the mode).
   - /workspace/studio_refresh_qa/refresh_test.py: a refresh restores the same mode / product / layers.
   If the new mode has its own state (picker, layer), add a refresh case for it to refresh_test.py.
