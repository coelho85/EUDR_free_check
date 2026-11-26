"""Ten synthetic EUDR plot datasets for testing the forest check, globally distributed,
in GeoJSON, GeoPackage, zipped Shapefile and KML. Writes to testdata/forest-check/.

Each dataset is a "sourcing portfolio" for a commodity and region, with realistic plot sizes,
a mix of polygons and points, and some of the awkward cases real files contain
(holes, multi-part plots, projected coordinates, several layers, odd ID field names,
plots outside the service coverage, a self-intersecting polygon, an empty geometry).
"""
import math
import random
import shutil
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Point, Polygon

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "testdata/forest-check"
M = 111_320.0


def blob(lon, lat, area_ha, rng, n=None, jitter=0.3):
    """Irregular polygon of roughly area_ha around lon/lat."""
    n = n or rng.randint(7, 18)
    r = math.sqrt(area_ha * 10_000 / math.pi)
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r * (1 + rng.uniform(-jitter, jitter))
        pts.append((lon + rr * math.cos(a) / (M * math.cos(math.radians(lat))), lat + rr * math.sin(a) / M))
    return Polygon(pts)


def with_hole(lon, lat, area_ha, rng):
    outer = blob(lon, lat, area_ha, rng, n=20, jitter=0.1)
    inner = blob(lon, lat, area_ha * rng.uniform(0.05, 0.2), rng, n=10, jitter=0.1)
    return Polygon(outer.exterior.coords, [inner.exterior.coords])


def multipart(lon, lat, area_ha, rng):
    k = rng.randint(2, 3)
    return MultiPolygon([blob(lon + j * rng.uniform(0.004, 0.02), lat + rng.uniform(-0.01, 0.01), area_ha / k, rng)
                         for j in range(k)])


def portfolio(name, regions, n_poly, n_pt, area, rng, holes=0.05, multis=0.05):
    """regions: list of (label, country, lon, lat, spread_deg). area: (min_ha, max_ha), log-uniform."""
    rows = []
    for i in range(n_poly):
        label, country, cx, cy, sd = rng.choice(regions)
        lon, lat = cx + rng.gauss(0, sd), cy + rng.gauss(0, sd)
        a = math.exp(rng.uniform(math.log(area[0]), math.log(area[1])))
        u = rng.random()
        g = with_hole(lon, lat, a, rng) if u < holes else multipart(lon, lat, a, rng) if u < holes + multis else blob(lon, lat, a, rng)
        rows.append({"plot_id": f"{name}-{i + 1:04d}", "producer": f"Producer {rng.randint(100, 999)}",
                     "country": country, "region": label, "declared_ha": round(a, 2), "geometry": g})
    for i in range(n_pt):   # EUDR allows a single point for plots under 4 ha
        label, country, cx, cy, sd = rng.choice(regions)
        rows.append({"plot_id": f"{name}-P{i + 1:03d}", "producer": f"Producer {rng.randint(100, 999)}",
                     "country": country, "region": label, "declared_ha": round(rng.uniform(0.3, 3.9), 2),
                     "geometry": Point(cx + rng.gauss(0, sd), cy + rng.gauss(0, sd))})
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


def shp_zip(layers, path):
    """layers: {layer_name: GeoDataFrame}. One shapefile per geometry type, all in one zip."""
    tmp = path.with_suffix("")
    tmp.mkdir(exist_ok=True)
    for lname, gdf in layers.items():
        gdf.to_file(tmp / f"{lname}.shp", engine="pyogrio")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(tmp.iterdir()):
            z.write(f, f.name)
    shutil.rmtree(tmp)


def to_kml(gdf, path, name_col):
    g = gdf.copy()
    g["Name"] = g[name_col]
    g = g[["Name"] + [c for c in g.columns if c not in ("Name", "geometry")] + ["geometry"]]
    g.to_file(path, driver="KML", engine="pyogrio")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    rng = random.Random(2026)
    made = []

    # 01 West African cocoa, smallholders: GeoJSON, WGS84
    d = portfolio("CIV-GHA", [("Soubré", "CIV", -6.6, 5.8, 0.35), ("Daloa", "CIV", -6.45, 6.9, 0.35),
                              ("San-Pédro", "CIV", -6.9, 5.1, 0.25), ("Western North", "GHA", -2.6, 6.3, 0.3),
                              ("Ashanti", "GHA", -1.7, 6.7, 0.3)], 170, 90, (0.8, 9), rng)
    d.to_file(OUT / "01_cocoa_west_africa.geojson", driver="GeoJSON", COORDINATE_PRECISION=7, engine="pyogrio")
    made.append(("01_cocoa_west_africa.geojson", d))

    # 02 Brazilian soy, large farms: GeoPackage in SIRGAS 2000 / UTM 21S (projected)
    d = portfolio("BR-SOY", [("Sorriso MT", "BRA", -55.7, -12.5, 0.6), ("Querência MT", "BRA", -52.2, -12.6, 0.5),
                             ("Paragominas PA", "BRA", -47.5, -3.0, 0.4), ("Santarém PA", "BRA", -54.6, -2.7, 0.3),
                             ("Balsas MA", "BRA", -46.1, -7.6, 0.5)], 210, 30, (40, 2500), rng, holes=0.08, multis=0.1)
    d.to_crs("EPSG:31981").to_file(OUT / "02_soy_brazil_utm21s.gpkg", layer="farms", driver="GPKG", engine="pyogrio")
    made.append(("02_soy_brazil_utm21s.gpkg", d))

    # 03 Oil palm in Sumatra and Borneo: Shapefile zip, UTM 48S, polygons and points as two shapefiles
    d = portfolio("ID-PALM", [("Riau", "IDN", 101.6, 0.5, 0.5), ("Jambi", "IDN", 103.2, -1.7, 0.4),
                              ("West Kalimantan", "IDN", 110.0, 0.2, 0.5), ("Central Kalimantan", "IDN", 113.4, -2.2, 0.5),
                              ("Sabah", "MYS", 117.8, 5.3, 0.4)], 200, 50, (2, 400), rng, holes=0.03, multis=0.07)
    d = d.rename(columns={"plot_id": "PLOT_ID", "producer": "GROWER", "declared_ha": "AREA_HA"})
    utm = d.to_crs("EPSG:32748")
    shp_zip({"palm_plots": utm[utm.geom_type != "Point"], "palm_smallholders": utm[utm.geom_type == "Point"]},
            OUT / "03_palm_indonesia_shp.zip")
    made.append(("03_palm_indonesia_shp.zip", d.rename(columns={"PLOT_ID": "plot_id"})))

    # 04 Andean coffee: KML, names in <name>, attributes as ExtendedData
    d = portfolio("CO-PE-COF", [("Huila", "COL", -75.9, 2.2, 0.35), ("Cauca", "COL", -76.5, 2.4, 0.3),
                                ("Antioquia", "COL", -75.8, 5.9, 0.3), ("Cajamarca", "PER", -78.8, -5.7, 0.35),
                                ("Junín", "PER", -75.0, -11.1, 0.3)], 130, 110, (0.4, 7), rng)
    to_kml(d, OUT / "04_coffee_colombia_peru.kml", "plot_id")
    made.append(("04_coffee_colombia_peru.kml", d))

    # 05 Vietnamese coffee and rubber: GeoJSON, ID field "id"
    d = portfolio("VN", [("Đắk Lắk", "VNM", 108.1, 12.75, 0.35), ("Lâm Đồng", "VNM", 108.0, 11.7, 0.3),
                         ("Gia Lai", "VNM", 108.0, 13.9, 0.3), ("Bình Phước rubber", "VNM", 106.9, 11.8, 0.3)],
                  180, 70, (0.5, 45), rng)
    d = d.rename(columns={"plot_id": "id"})
    d.to_file(OUT / "05_coffee_rubber_vietnam.geojson", driver="GeoJSON", COORDINATE_PRECISION=7, engine="pyogrio")
    made.append(("05_coffee_rubber_vietnam.geojson", d.rename(columns={"id": "plot_id"})))

    # 06 Cattle ranches in the Gran Chaco: Shapefile zip, WGS84, big multi-part ranches
    d = portfolio("CHACO", [("Boquerón", "PRY", -60.6, -22.3, 0.6), ("Alto Paraguay", "PRY", -59.8, -20.4, 0.5),
                            ("Salta", "ARG", -63.4, -24.2, 0.5), ("Santiago del Estero", "ARG", -62.6, -26.6, 0.5),
                            ("Santa Cruz", "BOL", -61.8, -17.6, 0.6)], 190, 0, (150, 6000), rng, holes=0.1, multis=0.15)
    shp_zip({"ranches": d}, OUT / "06_cattle_chaco_shp.zip")
    made.append(("06_cattle_chaco_shp.zip", d))

    # 07 East African coffee, mostly points (smallholders under 4 ha): KML
    d = portfolio("EA-COF", [("Sidama", "ETH", 38.45, 6.75, 0.25), ("Jimma", "ETH", 36.8, 7.7, 0.3),
                             ("Mt Elgon", "UGA", 34.45, 1.2, 0.2), ("Nyeri", "KEN", 36.95, -0.42, 0.15),
                             ("Kilimanjaro", "TZA", 37.4, -3.25, 0.15)], 60, 200, (0.3, 3.5), rng)
    to_kml(d, OUT / "07_coffee_east_africa.kml", "plot_id")
    made.append(("07_coffee_east_africa.kml", d))

    # 08 Central/West African cocoa: GeoPackage with two layers (plots, points), ID field "ProducerName"
    d = portfolio("CM-NG-LR", [("Centre", "CMR", 11.6, 4.1, 0.4), ("South-West", "CMR", 9.4, 4.6, 0.3),
                               ("Ondo", "NGA", 5.0, 7.1, 0.3), ("Cross River", "NGA", 8.6, 5.8, 0.3),
                               ("Nimba", "LBR", -8.7, 7.0, 0.3)], 160, 80, (0.8, 12), rng)
    d["ProducerName"] = [f"{p} / {i}" for p, i in zip(d["producer"], d["plot_id"])]
    d = d.drop(columns=["plot_id"])
    gp = OUT / "08_cocoa_central_africa_2layers.gpkg"
    d[d.geom_type != "Point"].to_file(gp, layer="cocoa_plots", driver="GPKG", engine="pyogrio")
    d[d.geom_type == "Point"].to_file(gp, layer="cocoa_points", driver="GPKG", engine="pyogrio", append=True)
    made.append(("08_cocoa_central_africa_2layers.gpkg", d.rename(columns={"ProducerName": "plot_id"})))

    # 09 Global mixed portfolio with edge cases: GeoJSON
    regs = [("Mato Grosso", "BRA", -55.5, -12.0, 1.0), ("Côte d'Ivoire", "CIV", -6.0, 6.5, 0.8),
            ("Sumatra", "IDN", 102.0, 0.0, 0.8), ("Vietnam", "VNM", 108.0, 12.5, 0.5),
            ("Colombia", "COL", -75.5, 4.0, 0.6), ("Chaco", "PRY", -60.5, -22.0, 0.8),
            ("Ethiopia", "ETH", 37.5, 7.5, 0.6), ("PNG", "PNG", 145.5, -6.3, 0.3),
            ("British Columbia", "CAN", -122.5, 53.5, 1.0), ("Georgia US", "USA", -83.5, 32.5, 0.8)]
    d = portfolio("GLOBAL", regs, 190, 50, (1, 900), rng, holes=0.06, multis=0.06)
    extra = []
    for k, (x, y) in enumerate([(-50, 0), (110, 0), (-10, 10), (100, 10), (-60, -10), (30, 0)]):   # 4 tiles meet here
        extra.append({"plot_id": f"GLOBAL-EDGE{k + 1}", "country": "", "region": "tile corner",
                      "geometry": blob(x + 0.002, y - 0.002, rng.uniform(300, 2500), rng, n=22)})
    for k, (x, y, c) in enumerate([(10.4, 51.2, "DEU"), (25.5, 62.0, "FIN"), (-3.7, 40.4, "ESP"), (20.0, 65.0, "SWE")]):
        extra.append({"plot_id": f"GLOBAL-EU{k + 1}", "country": c, "region": "Europe", "geometry": blob(x, y, 50, rng)})
    extra.append({"plot_id": "GLOBAL-OCEAN", "country": "", "region": "Atlantic", "geometry": Point(-30.0, -20.0)})
    extra.append({"plot_id": "GLOBAL-BOWTIE", "country": "BRA", "region": "invalid",
                  "geometry": Polygon([(-55.0, -12.0), (-54.99, -12.01), (-54.99, -12.0), (-55.0, -12.01)])})
    extra.append({"plot_id": "GLOBAL-EMPTY", "country": "BRA", "region": "no geometry", "geometry": None})
    d = pd.concat([d, gpd.GeoDataFrame(extra, crs="EPSG:4326")], ignore_index=True)
    d.to_file(OUT / "09_global_portfolio_edge_cases.geojson", driver="GeoJSON", COORDINATE_PRECISION=7, engine="pyogrio")
    made.append(("09_global_portfolio_edge_cases.geojson", d))

    # 10 Rubber, cocoa and coffee across Asia-Pacific and Central/South America: KML with holes and MultiGeometry,
    #    attribute "farm_code" only (not a recognised ID field, so the tool numbers the plots)
    d = portfolio("APLA", [("Surat Thani", "THA", 99.2, 9.0, 0.4), ("Songkhla", "THA", 100.5, 7.0, 0.25),
                           ("Morobe", "PNG", 146.6, -6.6, 0.3), ("Copán", "HND", -88.9, 14.8, 0.25),
                           ("Huehuetenango", "GTM", -91.4, 15.4, 0.25), ("Manabí", "ECU", -80.0, -1.0, 0.3),
                           ("San Martín", "PER", -76.6, -6.8, 0.3)], 170, 60, (0.5, 60), rng, holes=0.12, multis=0.12)
    d = d.rename(columns={"plot_id": "farm_code"})
    to_kml(d, OUT / "10_rubber_cocoa_coffee_tropics.kml", "farm_code")
    made.append(("10_rubber_cocoa_coffee_tropics.kml", d.rename(columns={"farm_code": "plot_id"})))

    print(f"{'file':42s} {'polygons':>8s} {'points':>6s} {'other':>5s}  size")
    for fn, g in made:
        t = g.geom_type.fillna("none")
        print(f"{fn:42s} {(t.isin(['Polygon', 'MultiPolygon'])).sum():8d} {(t == 'Point').sum():6d} "
              f"{(~t.isin(['Polygon', 'MultiPolygon', 'Point'])).sum():5d}  {(OUT / fn).stat().st_size / 1024:6.0f} KB")


if __name__ == "__main__":
    main()
