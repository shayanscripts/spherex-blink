# Paste this whole cell into Google Colab, or open docs/spherex-colab.ipynb.
# Upload spherex-colab-backend.zip when prompted.
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import ZipFile

from IPython import get_ipython
from IPython.display import Image, display

root = Path("/content/spherex-colab")
root.mkdir(exist_ok=True)
bundle = Path("/content/spherex-colab-backend.zip")
if not bundle.exists():
    if getattr(get_ipython(), 'kernel', None) is None:
        raise SystemExit(
            f'Upload {bundle.name} to /content using Colab’s Files sidebar, then rerun. '
            'Or run this code directly in a notebook cell (not with !python) to use the upload picker.'
        )
    from google.colab import files
    uploaded = files.upload()
    if bundle.name not in uploaded:
        raise ValueError(f"Upload {bundle.name} from the project.")
    bundle.write_bytes(uploaded[bundle.name])
    del uploaded
with ZipFile(bundle) as archive:
    archive.extractall(root)

# Use the project's Python version without changing the Colab kernel.
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
uv = [sys.executable, "-m", "uv", "run", "--no-project", "--python", "3.13",
      "--with-requirements", str(root / "backend/requirements.txt"), "python"]
env = {**os.environ, "SPHEREX_DATA_DIR": str(root / "data"),
       "SPHEREX_FITS_PATH": str(root / "reference.fits")}

# Three full Level 2 exposures of the same field from NASA/IPAC IRSA.
seed = """
import hashlib, json
from pathlib import Path
from urllib.parse import urlsplit
from astropy import log
from backend import archive, main

log.setLevel('ERROR')
ra,dec=304.52129078,39.07848168
urls=[
    'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W18_1B/l2b-v27-2026-196/4/level2_2025W18_1B_0023_2D4_spx_l2b-v27-2026-196.fits',
    'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W18_2B/l2b-v27-2026-197/4/level2_2025W18_2B_0097_3D4_spx_l2b-v27-2026-197.fits',
    'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W19_1B/l2b-v27-2026-197/4/level2_2025W19_1B_0197_3D4_spx_l2b-v27-2026-197.fits',
]
ids=[]
for url in urls:
    path,_=archive.download(url,main.DATA_DIR,None,None,.2)
    with path.open('rb') as stream:
        key=hashlib.file_digest(stream,'sha256').hexdigest()
    canonical=main.DATA_DIR/f'{key}.fits'
    if not canonical.exists():canonical.hardlink_to(path)
    sidecar=main.DATA_DIR/f'{key}.json'
    record=dict(filename=Path(urlsplit(url).path).name,archive=dict(url=url,original_url=url,release='DR1'))
    sidecar.write_text(json.dumps(record))
    metadata=main.metadata(key)
    obs=main.load(key)
    pos=obs.locate(ra,dec);pixel=obs.pixel('IMAGE',pos['x'],pos['y'])
    metadata['center_wavelength_um']=pixel['wavelength_um']
    metadata['center_bandwidth_um']=pixel['bandwidth_um']
    record['metadata']=metadata
    sidecar.write_text(json.dumps(record))
    ids.append(key)
    print('Ready:', record['filename'], flush=True)
    if len(ids)==1:
        default=Path('reference.fits')
        default.unlink(missing_ok=True)
        default.hardlink_to(canonical)
Path('seed-ids.json').write_text(json.dumps(ids))
"""
subprocess.run([*uv, "-u", "-c", seed], cwd=root, env=env, check=True)

# A random URL prefix gates the temporary API. Keep the printed URL private.
# Rerunning this cell stops the previous processes started in this notebook.
for process in (globals().get("spherex_tunnel"), globals().get("spherex_api")):
    if process is not None and process.poll() is None:
        process.terminate()
        process.wait(timeout=15)
prefix = "/" + secrets.token_urlsafe(24)
(root / "colab_api.py").write_text(
    "import os\nfrom starlette.applications import Starlette\n"
    "from starlette.routing import Mount\nfrom backend.main import app\n"
    "public_api = Starlette(routes=[Mount(os.environ['SPHEREX_API_PREFIX'], app=app)])\n"
)
with (root / "api.log").open("w") as log:
    spherex_api = subprocess.Popen(
        [*uv, "-m", "uvicorn", "colab_api:public_api", "--host", "127.0.0.1", "--port", "8000"],
        cwd=root, env={**env, "SPHEREX_API_PREFIX": prefix}, stdout=log, stderr=subprocess.STDOUT,
    )

def wait_for_health(base, process, logfile, timeout=60):
    for _ in range(timeout):
        if process.poll() is not None:
            break
        try:
            with urlopen(base + "/health", timeout=3) as response:
                if json.load(response).get("status") == "ok":
                    return
        except (URLError, TimeoutError, ValueError):
            time.sleep(1)
    raise RuntimeError(logfile.read_text()[-2500:])

local = "http://127.0.0.1:8000" + prefix
wait_for_health(local, spherex_api, root / "api.log")

# Preview the real difference in Colab. Higher grid size here covers more sky
# at the same angular sampling; it does not sharpen the instrument.
import requests
def post(path, payload):
    response = requests.post(local + path, json=payload, timeout=120)
    if not response.ok:
        raise RuntimeError(response.text)
    return response.json()

session = post("/workspace/sessions", dict(
    ids=json.loads((root / "seed-ids.json").read_text()),
    ra=304.52129078, dec=39.07848168, size=160, scale=6.15, subtract_zodi=True,
))
pair = session["recommended_pair"]
if pair:
    result = post("/analysis", dict(session=session["id"], reference=pair["reference"], new=pair["new"]))
    image = requests.get(local + f"/analysis/{result['id']}/image?kind=difference", timeout=30)
    image.raise_for_status()
    print("Measured B − A:", result["reference_timestamp"], "→", result["new_timestamp"])
    print("Residuals may include artifacts; this field is not a verified astrophysical change.")
    preview = root / 'difference.png'
    preview.write_bytes(image.content)
    if getattr(get_ipython(), 'kernel', None) is not None:
        display(Image(data=image.content, width=560))
    else:
        print(f'Difference preview saved to {preview}')
else:
    print("No compatible pair on the preview grid. The FITS files remain available in the API.")

# Start a temporary Cloudflare tunnel. This does not publish the project code.
cloudflared = root / "cloudflared"
if not cloudflared.exists():
    subprocess.run(["curl", "-fsSL", "--retry", "3", "-o", str(cloudflared),
                    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"], check=True)
    cloudflared.chmod(0o755)
tunnel_log = root / "tunnel.log"
with tunnel_log.open("w") as log:
    spherex_tunnel = subprocess.Popen(
        [str(cloudflared), "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8000"],
        stdout=log, stderr=subprocess.STDOUT,
    )
for _ in range(60):
    match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", tunnel_log.read_text())
    if match:
        break
    if spherex_tunnel.poll() is not None:
        break
    time.sleep(1)
else:
    match = None
if not match:
    raise RuntimeError(tunnel_log.read_text()[-2500:])
remote = match.group() + prefix
wait_for_health(remote, spherex_tunnel, tunnel_log)
print("\nAdd this to .env.local on your computer, then restart Next.js:")
print(f"BACKEND_URL={remote}")
print("Keep this runtime connected and keep the URL private. Remove BACKEND_URL to return to localhost.")
