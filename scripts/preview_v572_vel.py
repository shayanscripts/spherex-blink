"""Display original IRSA FITS crops at the documented nova position."""
import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from astropy import log

from backend import archive, main, processing

RA, DEC = 156.3079167, -53.5220278
URLS = (
    "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W25_1B/l2b-v27-2026-213/2/level2_2025W25_1B_0292_3D2_spx_l2b-v27-2026-213.fits",
    "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W25_2A/l2b-v27-2026-213/4/level2_2025W25_2A_0289_3D4_spx_l2b-v27-2026-213.fits",
    "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W25_2A/l2b-v27-2026-213/1/level2_2025W25_2A_0496_1D1_spx_l2b-v27-2026-213.fits",
)


def download(url):
    for attempt in range(3):
        try:
            return archive.download(url, main.DATA_DIR / "v572-vel", RA, DEC, .075)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def preview(output):
    log.setLevel("ERROR")
    panels = []
    for url in URLS:
        path, cutout_url = download(url)
        filename = Path(urlsplit(url).path).name
        meta = main.register(path, filename)
        file_id = meta["id"]
        obs = main.load(file_id)
        pos = obs.locate(RA, DEC)
        pixel = obs.pixel("IMAGE", **pos)
        sidecar = main.DATA_DIR / f"{file_id}.json"
        record = json.loads(sidecar.read_text())
        record["archive"] = dict(url=cutout_url, original_url=url, release="DR1")
        meta.update(source_url=cutout_url, provenance="Official NASA/IPAC IRSA native-resolution cutout.",
                    center_wavelength_um=pixel["wavelength_um"], center_bandwidth_um=pixel["bandwidth_um"])
        record["metadata"] = meta
        sidecar.write_text(json.dumps(record))
        panels.append((processing.calibrated_brightness(obs), pos, pixel, processing.timestamp(obs)))
        print(f"{processing.timestamp(obs)} · {pixel['wavelength_um']:.3f} µm · target FLAGS {pixel['flags']}", flush=True)

    # Set display limits from the pre-outburst field so the nova cannot wash out
    # the surrounding sky. Use the same limits for every panel.
    baseline = panels[0][0]
    lo, hi = np.nanpercentile(baseline, [5, 99.5])
    canvas = Image.new("RGB", (1080, 453), "#12171e")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default
    draw.text((24, 16), "V572 Velorum | documented nova outburst", fill="white", font=font(size=25))
    for i, (image, pos, pixel, utc) in enumerate(panels):
        left, top, size = 24 + i * 348, 88, 336
        tile = Image.open(BytesIO(processing.png(image, limits=(lo, hi)))).resize((size, size), Image.Resampling.NEAREST)
        canvas.paste(tile, (left, top), tile)
        h, w = image.shape
        cx = left + (pos["x"] + .5) * size / w
        cy = top + (h - pos["y"] - .5) * size / h
        radius = 4.5 * size / w
        draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), outline="#ffbc59", width=3)
        flagged = int(pixel["flags"]) & ~processing.INFORMATIONAL_FLAGS
        draw.text((left, 52), f"{utc[:10]} | {pixel['wavelength_um']:.3f} um", fill="white", font=font(size=17))
        draw.text((left, 71), "Target flagged" if flagged else "No rejecting flag at target",
                  fill="#ffbc59" if flagged else "#a5b1be", font=font(size=13))
    draw.text((24, 433), "Same sky position and display stretch. Different bands; visual comparison only. Bright pixels clip.",
              fill="#a5b1be", font=font(size=15))
    canvas.save(output)



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    preview(parser.parse_args().output)
