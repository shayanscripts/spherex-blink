# Paste into Colab. Upload the updated spherex-colab-backend.zip when prompted.
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile
import json
import ipywidgets as widgets
from IPython.display import Image, display
import io
import numpy as np
from PIL import Image as PILImage

MAX_EXPOSURES = 6000
FULL_FITS = False  # True downloads whole detector files, not finer pixels.
# Reuse FITS already downloaded by the previous cell, if present.
previous = Path("/content/v572-movie")
OUTPUT = previous if (previous / "fits").is_dir() else Path("/content/v572-observations")

root = Path("/content/spherex-colab")
bundle = Path("/content/spherex-colab-backend.zip")
if not bundle.is_file():
    from google.colab import files
    uploaded = files.upload()
    if bundle.name not in uploaded:
        raise ValueError(f"Upload {bundle.name}")
    bundle.write_bytes(uploaded[bundle.name])
    del uploaded
with ZipFile(bundle) as package:
    if "scripts/colab_v572_observations.py" not in package.namelist():
        raise ValueError("Replace the old ZIP in /content with the updated backend ZIP.")
    package.extractall(root)

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
args = [sys.executable, "-m", "uv", "run", "--no-project", "--python", "3.13",
        "--with-requirements", str(root / "backend/requirements.txt"),
        "python", "-u", "-m", "scripts.colab_v572_observations", str(OUTPUT),
        "--limit", str(MAX_EXPOSURES)]
if FULL_FITS:
    args.append("--full")
subprocess.run(args, cwd=root, env={**os.environ, "SPHEREX_DATA_DIR": str(root / "data")}, check=True)
print("Web app: refresh the page with BACKEND_URL pointing to this Colab backend. Choose a nova file in Complex → Observation library.")
# Browse observations individually. Hold the display stretch fixed so
# dragging the slider does not independently brighten each exposure.
manifest = json.loads((OUTPUT / "manifest.json").read_text())
rows = manifest["files"]
detectors = sorted({row["detector"] for row in rows})
band = widgets.Dropdown(options=[("All detectors", "all")] + [(f"D{d}", d) for d in detectors],
                        description="Detector")
slider = widgets.IntSlider(min=0, max=len(rows)-1, description="Observation", continuous_update=False)
output = widgets.Output()
baseline = next((row for row in rows if row["timestamp"].startswith("2025-06-17")), rows[0])
with np.load(baseline["grid"]) as data:
    lo, hi = np.percentile(data["image"][data["valid"]], [5, 99.5])


def show(_=None):
    subset = [row for row in rows if band.value == "all" or row["detector"] == band.value]
    slider.max = len(subset) - 1
    row = subset[slider.value]
    with np.load(row["grid"]) as data:
        values = np.where(data["valid"], data["image"], lo)
        scaled = np.clip((values - lo) / max(hi - lo, 1e-12), 0, 1)
        pixels = (255 * np.arcsinh(10 * scaled) / np.arcsinh(10)).astype(np.uint8)
    image = PILImage.fromarray(pixels).resize((576, 576), PILImage.Resampling.NEAREST).convert("RGB")
    from PIL import ImageDraw
    ImageDraw.Draw(image).ellipse((261, 261, 315, 315), outline="#ffbc59", width=2)
    with output:
        output.clear_output(wait=True)
        print(f"{row['timestamp']} UTC | D{row['detector']} | {row['wavelength_um']:.3f} µm")
        print(f"Target FLAGS: {row['flags']} | visual context; flagged pixels are shown")
        print(row["fits"])
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        display(Image(data=buffer.getvalue()))


slider.observe(show, names="value")
band.observe(show, names="value")
display(band, slider, output)
show()
