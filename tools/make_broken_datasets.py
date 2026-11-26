"""Deliberately broken or awkward files to test how the forest check handles bad input.
Writes testdata/forest-check-broken/.
"""
import json
import math
import random
import shutil
import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "testdata/forest-check-broken"
GOOD = ROOT / "testdata/forest-check"
M = 111_320.0
rng = random.Random(7)


def blob(lon, lat, ha, n=12):
    r = math.sqrt(ha * 1e4 / math.pi)
    return [[round(lon + r * (1 + rng.uniform(-.3, .3)) * math.cos(2 * math.pi * i / n) / (M * math.cos(math.radians(lat))), 7),
             round(lat + r * (1 + rng.uniform(-.3, .3)) * math.sin(2 * math.pi * i / n) / M, 7)] for i in range(n)]


def ring(lon, lat, ha, n=12):
    r = blob(lon, lat, ha, n)
    return r + [r[0]]


def fc(features):
    return {"type": "FeatureCollection", "features": features}


def feat(pid, geom):
    return {"type": "Feature", "properties": {"plot_id": pid}, "geometry": geom}


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    good = (GOOD / "01_cocoa_west_africa.geojson").read_text()

    # 1-3: damaged files
    (OUT / "b01_truncated.geojson").write_text(good[: len(good) // 2])
    (OUT / "b02_not_geojson.json").write_text(json.dumps({"supplier": "ACME", "plots": 12}))
    (OUT / "b03_damaged.gpkg").write_bytes((GOOD / "02_soy_brazil_utm21s.gpkg").read_bytes()[:3000])
    z = (GOOD / "06_cattle_chaco_shp.zip").read_bytes()
    (OUT / "b04_truncated_shapefile.zip").write_bytes(z[: len(z) // 2])

    # 5: shapefile without .dbf
    with zipfile.ZipFile(GOOD / "06_cattle_chaco_shp.zip") as src, zipfile.ZipFile(OUT / "b05_shapefile_missing_dbf.zip", "w") as dst:
        for n in src.namelist():
            if not n.endswith(".dbf"):
                dst.writestr(n, src.read(n))

    # 6-7: projected coordinates without coordinate system information
    g = gpd.read_file(GOOD / "02_soy_brazil_utm21s.gpkg").head(40)            # EPSG:31981 metres
    tmp = OUT / "_shp"; tmp.mkdir()
    g.to_file(tmp / "farms.shp")
    with zipfile.ZipFile(OUT / "b06_shapefile_utm_no_prj.zip", "w") as dst:
        for f in tmp.iterdir():
            if f.suffix != ".prj":
                dst.write(f, f.name)
    shutil.rmtree(tmp)
    gj = json.loads(g.to_json())
    gj.pop("crs", None)
    (OUT / "b07_utm_metres_no_crs.geojson").write_text(json.dumps(gj))

    # 8: latitude and longitude swapped (Côte d'Ivoire plots end up in the Gulf of Guinea)
    d = json.loads(good)
    sw = lambda c: [c[1], c[0]] if isinstance(c[0], (int, float)) else [sw(x) for x in c]
    for f in d["features"][:60]:
        f["geometry"]["coordinates"] = sw(f["geometry"]["coordinates"])
    d["features"] = d["features"][:60]
    (OUT / "b08_lat_lon_swapped.geojson").write_text(json.dumps(d))

    # 9: invalid XML
    k = (GOOD / "04_coffee_colombia_peru.kml").read_text()
    (OUT / "b09_broken.kml").write_text(k[: len(k) // 3])

    # 10: one file with every kind of bad geometry, plus normal plots
    outer = ring(-55.6, -12.2, 300, 20)
    far_hole = ring(-55.5, -12.2, 20, 8)                         # hole drawn outside its plot
    feats = [
        feat("OK-1", {"type": "Polygon", "coordinates": [ring(-55.62, -12.05, 80)]}),
        feat("OK-2", {"type": "Point", "coordinates": [-55.7, -12.1]}),
        feat("BOWTIE", {"type": "Polygon", "coordinates": [[[-55.0, -12.0], [-54.99, -12.01], [-54.99, -12.0], [-55.0, -12.01], [-55.0, -12.0]]]}),
        feat("HOLE-OUTSIDE", {"type": "Polygon", "coordinates": [outer, far_hole]}),
        feat("TINY-0.001ha", {"type": "Polygon", "coordinates": [ring(-55.3, -12.3, 0.001, 6)]}),
        feat("TWO-POINTS", {"type": "Polygon", "coordinates": [[[-55.1, -12.1], [-55.2, -12.2], [-55.1, -12.1]]]}),
        feat("UNCLOSED-RING", {"type": "Polygon", "coordinates": [blob(-55.4, -12.4, 50)]}),
        feat("LINE", {"type": "LineString", "coordinates": [[-55.1, -12.1], [-55.0, -12.0]]}),
        feat("NO-GEOMETRY", None),
        feat("NAN-POINT", {"type": "Point", "coordinates": ["abc", None]}),
        feat("MULTIPOINT-3", {"type": "MultiPoint", "coordinates": [[-55.5, -12.5], [-55.51, -12.5], [-55.52, -12.5]]}),
        feat("HUGE-STATE", {"type": "Polygon", "coordinates": [ring(-55.0, -13.0, 900_000, 24)]}),
        feat("EUROPE-DE", {"type": "Polygon", "coordinates": [ring(10.4, 51.2, 40)]}),
    ]
    (OUT / "b10_bad_geometries.geojson").write_text(json.dumps(fc(feats)))

    # 11: total area beyond the browser limit (60 x 95,000 ha)
    feats = [feat(f"BIG-{i}", {"type": "Polygon", "coordinates": [ring(-60 + (i % 10) * 0.6, -10 - (i // 10) * 0.6, 95_000, 16)]})
             for i in range(60)]
    (OUT / "b11_total_area_too_large.geojson").write_text(json.dumps(fc(feats)))

    # 12-13: empty file and a wrong file type
    (OUT / "b12_empty.geojson").write_bytes(b"")
    (OUT / "b13_plots.csv").write_text("plot_id,lat,lon\nA,6.1,-5.2\n")

    for f in sorted(OUT.iterdir()):
        print(f"{f.name:36s} {f.stat().st_size / 1024:7.1f} KB")


if __name__ == "__main__":
    main()
