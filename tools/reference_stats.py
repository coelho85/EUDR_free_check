"""Reference forest statistics per plot, computed with rasterio/GDAL.

Usage: reference_stats.py <raster.tif> <plots file> <out.json>

Same rule as the browser: a pixel belongs to a plot if its centre is inside
(GDAL rasterize default). Pixel area is computed per row on the authalic
sphere: A = R^2 * dlon * |sin(lat_top) - sin(lat_bottom)|.
Also reports exactextract's coverage-weighted forest area for comparison.
"""
import json
import math
import sys

import geopandas as gpd
import numpy as np
import rasterio
from exactextract import exact_extract
from rasterio.features import rasterize
from rasterio.windows import Window

R = 6371007.181
raster_path, plots_path, out_path = sys.argv[1:4]
gdf = gpd.read_file(plots_path).to_crs("EPSG:4326")
out = {}

with rasterio.open(raster_path) as src:
    T = src.transform
    dlon = math.radians(T.a)
    full = Window(0, 0, src.width, src.height)
    for _, row in gdf.iterrows():
        g, pid = row.geometry, row.plot_id
        if g.geom_type == "Point":
            r, c = src.index(g.x, g.y)
            inside = 0 <= r < src.height and 0 <= c < src.width
            v = int(src.read(1, window=Window(c, r, 1, 1))[0, 0]) if inside else None
            out[pid] = {"type": "point", "forest": v}
            continue
        minx, miny, maxx, maxy = g.bounds
        c0, c1 = math.floor((minx - T.c) / T.a) - 1, math.ceil((maxx - T.c) / T.a) + 1
        r0, r1 = math.floor((maxy - T.f) / T.e) - 1, math.ceil((miny - T.f) / T.e) + 1
        w = Window(c0, r0, c1 - c0, r1 - r0)
        try:
            w = w.intersection(full)
        except Exception:
            out[pid] = {"type": "polygon", "outside": True}
            continue
        data = src.read(1, window=w)
        wt = src.window_transform(w)
        mask = rasterize([(g, 1)], out_shape=data.shape, transform=wt, fill=0, dtype="uint8")
        rows_lat_top = wt.f + np.arange(data.shape[0]) * wt.e
        row_area = R * R * dlon * np.abs(np.sin(np.radians(rows_lat_top)) - np.sin(np.radians(rows_lat_top + wt.e)))
        inside = mask == 1
        total_m2 = float((inside.sum(axis=1) * row_area).sum())
        forest_m2 = float(((inside & (data == 1)).sum(axis=1) * row_area).sum())
        out[pid] = {"type": "polygon", "px": int(inside.sum()), "forest_px": int((inside & (data == 1)).sum()),
                    "total_ha": total_m2 / 1e4, "forest_ha": forest_m2 / 1e4}

    polys = gdf[gdf.geom_type.isin(["Polygon", "MultiPolygon"])]
    ee = exact_extract(src, polys, ["sum", "count"], include_cols=["plot_id"], output="pandas")
    for _, r in ee.iterrows():
        if r.plot_id in out and r["count"] > 0:
            out[r.plot_id]["exactextract_forest_frac"] = float(r["sum"] / r["count"])

json.dump(out, open(out_path, "w"), indent=1)
print(f"{len(out)} plots -> {out_path}")
