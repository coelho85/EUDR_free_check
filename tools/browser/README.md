# Browser tests

Uses your installed Google Chrome (macOS path in the scripts; edit `executablePath` elsewhere).

```bash
cd tools/browser && npm install
# serve the page first: (cd ../../web && python3 -m http.server 8765)
PAGE=/ node drop.mjs ../../testdata/forest-check-broken          # every file in a folder
PAGE=/ ROWS=1 node drop.mjs ../../testdata/forest-check 01_cocoa_west_africa.geojson   # per-plot lines
```

`BASE` (default `http://localhost:8765`) and `PAGE` (default `/forest-check/`) set the address; `OUTJSON=file.json` saves the results.
