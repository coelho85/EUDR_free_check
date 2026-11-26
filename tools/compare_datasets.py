"""Compare browser results for the test datasets with the GDAL reference.

Browser results: spike/testdata/out/<file>__cftiles__<tag>.json   Reference: testdata/forest-check/ref/<file>.json
Usage: tools/compare_datasets.py [tag]   (default tag: ds)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tag = sys.argv[1] if len(sys.argv) > 1 else "ds"
print(f"{'dataset':40s} {'plots':>5s} {'same px':>7s} {'same forest px':>14s} {'max Δ forest ha':>15s} "
      f"{'points ok':>9s} {'status ok':>9s} {'other':>5s}  notes")
total = [0, 0, 0, 0, 0]
for ref_path in sorted((ROOT / "testdata/forest-check/ref").glob("*.json")):
    name = ref_path.name[:-5]
    out = ROOT / f"spike/testdata/out/{name}__cftiles__{tag}.json"
    if not out.exists():
        print(f"{name:40s} (no browser result)"); continue
    ref, b = json.load(open(ref_path)), json.load(open(out))
    if "error" in b:
        print(f"{name:40s} ERROR {b['error'][:200]}"); continue
    n = px = fpx = pts = pts_ok = st_ok = other = 0
    dha, notes = 0.0, []
    for r in b["results"]:
        g = ref.get(r["id"])
        status = r.get("status", "")
        if g is None:
            other += 1; notes.append(f"{r['id']}: {status}"); continue
        if g["type"] == "point":
            pts += 1; ok = (r.get("forest") or 0) == (g["forest"] or 0); pts_ok += ok
            st_ok += ok; continue
        n += 1
        if status == "outside service coverage":
            other += 1; notes.append(f"{r['id']}: outside coverage (reference forest px {g.get('forest_px')})"); continue
        px += r["px"] == g["px"]; fpx += r["forestPx"] == g["forest_px"]
        dha = max(dha, abs(r["forestHa"] - g["forest_ha"]))
        expect = "forest" if g["forest_px"] > 0 else "no forest"
        st_ok += status == expect or (expect == "no forest" and status.startswith("no forest"))
        if r["forestPx"] != g["forest_px"]:
            notes.append(f"{r['id']}: forest px {r['forestPx']} vs {g['forest_px']}")
    print(f"{name:40s} {n:5d} {px:7d} {fpx:14d} {dha:15.4f} {pts_ok:>4d}/{pts:<4d} {st_ok:>4d}/{n + pts - other:<4d} {other:5d}  "
          + "; ".join(notes[:4]))
    for i, v in enumerate((n, fpx, pts, pts_ok, other)):
        total[i] += v
print(f"\nTotal: {total[0]} polygons ({total[1]} identical forest pixel counts), {total[2]} points ({total[3]} identical), "
      f"{total[4]} not compared (skipped/outside coverage)")
