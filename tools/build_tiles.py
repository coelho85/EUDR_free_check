#!/usr/bin/env python3
"""Cut the global JRC GFC2020 v4 COG (read from JRC) into 10° COG tiles and upload them to R2.

Resumable: tiles already on R2 are skipped, so just run it again after an interruption.

Usage (from the project folder, in your own Terminal):
    caffeinate -i python3 tools/build_tiles.py                 # all service tiles (264)
    python3 tools/build_tiles.py S10_W60 S20_W60               # only these tiles
    python3 tools/build_tiles.py --manifest-only               # just rebuild tiles.json

Needs: GDAL (gdal_translate) and rclone with the remote "r2" configured.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = "/vsicurl/https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/FOREST/GFC2020/LATEST/single-cog/JRC_GFC2020_V4_COG.tif"  # global COG on JRC (R2 copy deleted 2026-11-25)
# New folder: never overwrite files at an existing URL (Cloudflare would keep serving cached old bytes).
REMOTE = "r2:eudr-forest-maps/gfc2020/v4/cog10/"
MAX_MB = 480               # Cloudflare (Free/Pro) only caches files up to ~512 MB
TILE_LIST = ROOT / "data/manifests/service_tiles.txt"      # JRC tiles minus excluded_tiles.txt
EXCLUDED = ROOT / "data/manifests/excluded_tiles.txt"
MANIFEST = ROOT / "data/manifests/tiles.json"
LOG = ROOT / "data/manifests/build_tiles.log"
RES = 1 / 12000            # 0.3 arc-second
TILE_DEG = 10

GDAL_ENV = {
    "GDAL_HTTP_VERSION": "2",
    "GDAL_HTTP_MULTIPLEX": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_MAX_RETRY": "5",
    "GDAL_HTTP_RETRY_DELAY": "3",
    "CPL_VSIL_CURL_CHUNK_SIZE": str(4 * 1024 * 1024),
    "CPL_VSIL_CURL_CACHE_SIZE": str(512 * 1024 * 1024),
    "GDAL_INGESTED_BYTES_AT_OPEN": "65536",
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "VSI_CACHE": "TRUE",
    "VSI_CACHE_SIZE": str(512 * 1024 * 1024),
    "GDAL_CACHEMAX": "2048",
}


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def tile_bounds(name):
    lat_s, lon_s = name.split("_")
    top = int(lat_s[1:]) * (1 if lat_s[0] == "N" else -1)
    left = int(lon_s[1:]) * (1 if lon_s[0] == "E" else -1)
    return left, top, left + TILE_DEG, top - TILE_DEG


def fname(name):
    return f"JRC_GFC2020_V4_{name}_cog.tif"


def on_r2():
    out = subprocess.run(["rclone", "lsf", REMOTE, "--include", "*_cog.tif"],
                         capture_output=True, text=True, check=True).stdout
    return {l.strip()[len("JRC_GFC2020_V4_"):-len("_cog.tif")] for l in out.splitlines() if l.strip()}


def build(name, tmpdir):
    ulx, uly, lrx, lry = tile_bounds(name)
    out = Path(tmpdir) / fname(name)
    env = {**os.environ, **GDAL_ENV}
    subprocess.run(["gdal_translate", "-q", "-of", "COG",
                    "-co", "BLOCKSIZE=1024", "-co", "COMPRESS=DEFLATE", "-co", "NUM_THREADS=ALL_CPUS",
                    "-co", "LEVEL=9", "-co", "BIGTIFF=IF_SAFER", "-co", "OVERVIEWS=NONE",
                    "-projwin", str(ulx), str(uly), str(lrx), str(lry),
                    SOURCE, str(out)], check=True, env=env)
    # sanity check: size and origin
    info = json.loads(subprocess.run(["gdalinfo", "-json", str(out)], capture_output=True, text=True, check=True).stdout)
    w, h = info["size"]
    gt = info["geoTransform"]
    expected = round(TILE_DEG / RES)
    if (w, h) != (expected, expected) or abs(gt[0] - ulx) > RES / 2 or abs(gt[3] - uly) > RES / 2:
        raise RuntimeError(f"{name}: unexpected size/origin {w}x{h} at {gt[0]},{gt[3]}")
    mb = out.stat().st_size / 1e6
    if mb > MAX_MB:
        raise RuntimeError(f"{name}: {mb:.0f} MB is above {MAX_MB} MB and would not be cached by Cloudflare")
    return out


def upload(path):
    subprocess.run(["rclone", "copyto", str(path), REMOTE + path.name,
                    "--s3-chunk-size", "64M", "--s3-upload-concurrency", "8",
                    "--header-upload", "Cache-Control: public, max-age=31536000, immutable",
                    "--retries", "5"], check=True)


def write_manifest(tiles):
    excluded = sorted(l.strip() for l in EXCLUDED.read_text().splitlines() if l.strip())
    tiles = set(tiles) - set(excluded)   # excluding a tile later needs no deletion on R2
    m = {"name": "JRC GFC2020 v4, 10-degree COG tiles", "tileDeg": TILE_DEG, "res": RES,
         "originLon": -180, "originLat": 80, "pattern": "JRC_GFC2020_V4_{tile}_cog.tif",
         "tiles": sorted(tiles), "excluded": excluded}
    MANIFEST.write_text(json.dumps(m, indent=0))
    subprocess.run(["rclone", "copyto", str(MANIFEST), REMOTE + "tiles.json",
                    "--header-upload", "Cache-Control: public, max-age=300",
                    "--header-upload", "Content-Type: application/json"], check=True)
    log(f"manifest uploaded with {len(tiles)} tiles")


def main(args):
    all_tiles = [l.strip() for l in TILE_LIST.read_text().splitlines() if l.strip()]
    done = on_r2()
    if "--manifest-only" in args:
        write_manifest(done)
        return
    wanted = [a for a in args if not a.startswith("--")] or all_tiles
    todo = [t for t in wanted if t not in done]
    log(f"{len(wanted)} requested, {len(wanted) - len(todo)} already on R2, {len(todo)} to build")
    failed = []
    with tempfile.TemporaryDirectory(dir=ROOT / "data") as tmp:
        for i, name in enumerate(todo, 1):
            t0 = time.time()
            try:
                path = build(name, tmp)
                mb = path.stat().st_size / 1e6
                t1 = time.time()
                upload(path)
                path.unlink()
                done.add(name)
                left = (time.time() - t0) * (len(todo) - i) / 60
                log(f"[{i}/{len(todo)}] {name}: {mb:.0f} MB, build {t1 - t0:.0f} s, upload {time.time() - t1:.0f} s"
                    f"  (~{left:.0f} min left)")
                if i % 10 == 0:
                    write_manifest(done)
            except Exception as e:  # keep going; rerun later to retry failures
                failed.append(name)
                log(f"[{i}/{len(todo)}] {name}: FAILED {e}")
                for f in Path(tmp).glob("*"):
                    f.unlink()
    write_manifest(done)
    log(f"finished: {len(done)} tiles on R2, {len(failed)} failed {failed if failed else ''}")
    if failed:
        log("run the same command again to retry the failed tiles")


if __name__ == "__main__":
    main(sys.argv[1:])
