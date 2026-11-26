"""GDAL reference results for the test datasets in testdata/forest-check/.

Builds a VRT over the 10° COG tiles on R2 (same data the browser reads), assigns each feature the ID the
web tool would use, and runs tools/reference_stats.py. Output: testdata/forest-check/ref/<file>.json
"""
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "testdata/forest-check"
REF = DATA / "ref"
VRT = ROOT / "data/cog10_r2.vrt"
BASE = "https://maps.geoanalyticslab.com/gfc2020/v4/cog10/"
ID_KEYS = ["plot_id", "PLOT_ID", "plotid", "id", "ID", "name", "Name", "NAME", "ProducerName"]   # as in readers.js
ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_VERSION": "2", "GDAL_HTTP_MULTIPLEX": "YES",
       "VSI_CACHE": "TRUE", "GDAL_HTTP_MAX_RETRY": "5", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif"}


def build_vrt():
    """All tiles share the global 1/12000° grid (origin -180, 80), so the VRT is written directly
    (gdalbuildvrt would open 264 remote files just to read their headers)."""
    if VRT.exists():
        return
    m = json.load(urllib.request.urlopen(urllib.request.Request(BASE + "tiles.json", headers={"User-Agent": "curl/8"})))
    res, n = m["res"], round(m["tileDeg"] / m["res"])
    W, H = round(360 / res), round((m["originLat"] + 60) / res)
    src = []
    for t in m["tiles"]:
        lat, lon = t.split("_")
        top = int(lat[1:]) * (1 if lat[0] == "N" else -1)
        left = int(lon[1:]) * (1 if lon[0] == "E" else -1)
        x0, y0 = round((left - m["originLon"]) / res), round((m["originLat"] - top) / res)
        src.append(f"""    <ComplexSource>
      <SourceFilename relativeToVRT="0">/vsicurl/{BASE}{m['pattern'].replace('{tile}', t)}</SourceFilename>
      <SourceBand>1</SourceBand>
      <SourceProperties RasterXSize="{n}" RasterYSize="{n}" DataType="Byte" BlockXSize="1024" BlockYSize="1024"/>
      <SrcRect xOff="0" yOff="0" xSize="{n}" ySize="{n}"/>
      <DstRect xOff="{x0}" yOff="{y0}" xSize="{n}" ySize="{n}"/>
      <NODATA>255</NODATA>
    </ComplexSource>""")
    VRT.write_text(f"""<VRTDataset rasterXSize="{W}" rasterYSize="{H}">
  <SRS dataAxisToSRSAxisMapping="2,1">EPSG:4326</SRS>
  <GeoTransform>{m['originLon']}, {res!r}, 0, {m['originLat']}, 0, {-res!r}</GeoTransform>
  <VRTRasterBand dataType="Byte" band="1" blockXSize="1024" blockYSize="1024">
    <NoDataValue>255</NoDataValue>
""" + "\n".join(src) + """
  </VRTRasterBand>
</VRTDataset>
""")


def load(path):
    src = f"/vsizip/{path}" if path.suffix == ".zip" else str(path)
    frames = []
    for lname, _ in pyogrio.list_layers(src):
        g = gpd.read_file(src, layer=lname, engine="pyogrio")
        if path.suffix in (".kml", ".kmz"):
            g = g.drop(columns=["id"], errors="ignore")   # GDAL exposes the XML placemark id; the tool uses <name>
        frames.append(g.to_crs("EPSG:4326") if g.crs else g.set_crs("EPSG:4326"))
    g = pd.concat(frames, ignore_index=True)
    key = next(k for k in ID_KEYS if k in g.columns)
    g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
    g["plot_id"] = g[key].astype(str)
    return gpd.GeoDataFrame(g[["plot_id", "geometry"]], crs="EPSG:4326")


def main(names):
    import os
    os.environ.update(ENV)
    build_vrt()
    REF.mkdir(exist_ok=True)
    for f in sorted(DATA.iterdir()):
        if f.is_dir() or (names and f.name not in names):
            continue
        g = load(f)
        tmp = REF / (f.name + ".plots.geojson")
        g.to_file(tmp, driver="GeoJSON", engine="pyogrio")
        subprocess.run([sys.executable, str(ROOT / "tools/reference_stats.py"), str(VRT), str(tmp), str(REF / (f.name + ".json"))],
                       check=True)
        tmp.unlink()
        print(f.name, len(g), "plots", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
