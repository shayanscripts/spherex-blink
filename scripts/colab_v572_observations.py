"""Colab worker: download and catalog actual SPHEREx exposures of one sky location."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit
import time

from astropy import log
import numpy as np
from reproject import reproject_interp

from backend import archive, processing
from backend.science import Observation

RA, DEC = 156.3079167, -53.5220278
COLLECTIONS = ("spherex_dr1", "spherex_qr3")


def discover(limit):
    unique = {}
    for collection in COLLECTIONS:
        for attempt in range(3):
            try:
                result = archive.search(RA, DEC, .001, collection, 10000)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
        if result["capped"]:
            raise RuntimeError(f"{collection} query was capped; cannot report a complete inventory.")
        for row in result["results"]:
            if row["timestamp"] and row["obs_id"]:
                unique.setdefault((row["obs_id"], row["detector"]), row)
        print(collection, len(result["results"]), "archive rows", flush=True)
    rows = sorted(unique.values(), key=lambda row: (row["timestamp"], row["detector"]))
    print(f"{len(rows)} unique dated exposures across both releases; downloading up to {limit}.", flush=True)
    return rows[:limit], len(rows)


def register_for_app(obs, path, digest, row, download_url, pixel, directory):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{digest}.fits"
    if not target.exists():
        try:
            target.hardlink_to(path)
        except OSError:
            temporary = target.with_suffix(".fits.tmp")
            shutil.copyfile(path, temporary)
            temporary.replace(target)
    url = row["url"]
    filename = Path(urlsplit(url).path).name
    release = urlsplit(url).path.split("/")[4].upper()
    meta = obs.metadata(digest, filename)
    meta.update(source_url=download_url, provenance="Downloaded from the official NASA/IPAC IRSA SPHEREx archive.",
                center_wavelength_um=pixel["wavelength_um"], center_bandwidth_um=pixel["bandwidth_um"])
    if meta["release"] is None:
        meta["release"] = dict(key="Archive path", value=release, extension="IRSA")
    sidecar = directory / f"{digest}.json"
    temporary = sidecar.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(dict(filename=filename, metadata=meta,
        archive=dict(url=download_url, original_url=url, release=release)), allow_nan=False))
    temporary.replace(sidecar)


def run(args):
    log.setLevel("ERROR")
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    library = Path(os.environ.get("SPHEREX_DATA_DIR", "/content/spherex-colab/data"))
    rows, available = discover(args.limit)
    grid = processing.sky_grid(RA, DEC, 96, 6.15)

    def fetch(row):
        for attempt in range(4):
            try:
                coords = (None, None) if args.full else (RA, DEC)
                return archive.download(row["url"], root / "fits", *coords, .20)
            except Exception as exc:
                if attempt == 3:
                    return exc
                time.sleep(2**attempt)

    successful, failed = [], []
    # Bound the in-flight downloads; FITS reading and WCS calls stay serial.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row, result in zip(rows, pool.map(fetch, rows)):
            try:
                if isinstance(result, Exception):
                    raise result
                path, download_url = result
                obs = Observation.read(path)
                position = obs.locate(RA, DEC)
                pixel = obs.pixel("IMAGE", **position)
                utc = processing.timestamp(obs)
                if not utc or pixel["wavelength_um"] is None:
                    raise ValueError("No FITS timestamp or wavelength at target.")
                image, footprint = reproject_interp(
                    (processing.calibrated_brightness(obs), obs.spatial),
                    grid, shape_out=(96, 96), order="nearest-neighbor",
                )
                valid = (footprint > 0) & np.isfinite(image)
                if not valid.any():
                    raise ValueError("No finite display coverage.")
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                # Keep raw FITS and separate display grids so the display stretch
                # can be chosen once, using a pre-outburst image.
                cache = root / "grids"
                cache.mkdir(exist_ok=True)
                grid_path = cache / f"{digest}.npz"
                np.savez_compressed(grid_path, image=image, valid=valid)
                register_for_app(obs, path, digest, row, download_url, pixel, library)
                successful.append(dict(timestamp=utc, detector=row["detector"], wavelength_um=pixel["wavelength_um"],
                    flags=pixel["flags"], fits=str(path), sha256=digest, url=row["url"],
                    download_url=download_url, grid=str(grid_path)))
            except Exception as exc:
                failed.append(dict(url=row["url"], error=str(exc)))
            total = len(successful) + len(failed)
            if total % 10 == 0 or total == len(rows):
                print(f"{total}/{len(rows)} checked · {len(successful)} readable frames · {len(failed)} failures", flush=True)
    successful.sort(key=lambda row: (row["timestamp"], row["detector"]))
    (root / "manifest.json").write_text(json.dumps(dict(available=available, requested=args.limit,
        files=successful, failures=failed), indent=2, allow_nan=False))
    if not successful:
        raise RuntimeError("No usable frames. See manifest.json; rerun to retry downloads.")

    print(f"Ready: {len(successful)} FITS exposures registered in the web app library: {library}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int, default=6000, choices=range(1, 6001), metavar="1–6000")
    parser.add_argument("--full", action="store_true", help="Download full FITS instead of native-resolution cutouts.")
    args = parser.parse_args()
    run(args)
