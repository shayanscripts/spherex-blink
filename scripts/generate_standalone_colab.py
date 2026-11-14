"""Generate a paste-ready Colab script and notebook with the backend embedded."""
import argparse
import ast
import base64
import io
import json
from pathlib import Path
from textwrap import wrap
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]

BOOTSTRAP = r'''
# Paste this whole script into one Colab code cell and run it.
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import re
import secrets
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import ZipFile

MAX_EXPOSURES = 6000
FULL_FITS = False  # Native-resolution cutouts; True downloads full detector files.
root = Path("/content/spherex-colab")
previous = Path("/content/v572-movie")
OUTPUT = previous if (previous / "fits").is_dir() else Path("/content/v572-observations")
data = root / "data"
data.mkdir(parents=True, exist_ok=True)
with ZipFile(io.BytesIO(base64.b64decode(EMBEDDED_BACKEND, validate=True))) as package:
    package.extractall(root)
del EMBEDDED_BACKEND

if importlib.util.find_spec("uv") is None:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
uv = [sys.executable, "-m", "uv", "run", "--no-project", "--python", "3.13",
      "--with-requirements", str(root / "backend/requirements.txt"), "python"]
default = root / "nova-default.fits"
env = {**os.environ, "SPHEREX_DATA_DIR": str(data), "SPHEREX_FITS_PATH": str(default)}


def healthy(base):
    try:
        with urlopen(base + "/health", timeout=4) as response:
            return json.load(response).get("status") == "ok"
    except (URLError, TimeoutError, ValueError):
        return False


def wait_for_health(base, process, log):
    deadline = time.monotonic() + 120
    while process.poll() is None and time.monotonic() < deadline:
        if healthy(base):
            return
        time.sleep(1)
    raise RuntimeError(f"API unavailable. See {log} in Colab's Files sidebar.")


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


# Reuse an existing healthy tunnel from an earlier cell in this notebook.
remote = globals().get("remote")
if not (isinstance(remote, str) and healthy(remote)):
    stop(globals().get("spherex_tunnel"))
    stop(globals().get("spherex_api"))
    prefix = "/" + secrets.token_urlsafe(24)
    (root / "colab_api.py").write_text(
        "import os\nfrom starlette.applications import Starlette\n"
        "from starlette.routing import Mount\nfrom backend.main import app\n"
        "public_api = Starlette(routes=[Mount(os.environ['SPHEREX_API_PREFIX'], app=app)])\n"
    )
    api_log = root / "api.log"
    with api_log.open("w") as log:
        spherex_api = subprocess.Popen(
            [*uv, "-m", "uvicorn", "colab_api:public_api", "--host", "127.0.0.1",
             "--port", "8000", "--no-access-log"],
            cwd=root, env={**env, "SPHEREX_API_PREFIX": prefix},
            stdout=log, stderr=subprocess.STDOUT,
        )
    wait_for_health("http://127.0.0.1:8000" + prefix, spherex_api, api_log)
    arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
    if not arch:
        raise RuntimeError("Unsupported Colab CPU architecture.")
    cloudflared = root / "cloudflared"
    if not cloudflared.exists():
        temporary = cloudflared.with_suffix(".part")
        subprocess.run(["curl", "-fsSL", "--retry", "3", "-o", str(temporary),
                        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-" + arch],
                       check=True)
        temporary.chmod(0o755)
        temporary.replace(cloudflared)
    tunnel_log = root / "tunnel.log"
    with tunnel_log.open("w") as log:
        spherex_tunnel = subprocess.Popen(
            [str(cloudflared), "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8000"],
            stdout=log, stderr=subprocess.STDOUT,
        )
    match = None
    deadline = time.monotonic() + 60
    while spherex_tunnel.poll() is None and time.monotonic() < deadline:
        match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", tunnel_log.read_text())
        if match:
            break
        time.sleep(1)
    if not match:
        raise RuntimeError(f"No tunnel URL. See {tunnel_log} in Colab's Files sidebar.")
    remote = match.group() + prefix
    wait_for_health(remote, spherex_tunnel, tunnel_log)

print(f"\nBACKEND_URL={remote}\n", flush=True)
print("Copy the entire line into your local .env.local and restart Next.js. Keep the URL private.", flush=True)
print("Downloading or reusing Nova Velorum observations and registering them in the app library...", flush=True)
args = [*uv, "-u", "-m", "scripts.colab_v572_observations", str(OUTPUT),
        "--limit", str(MAX_EXPOSURES)]
if FULL_FITS:
    args.append("--full")
subprocess.run(args, cwd=root, env=env, check=True)
manifest = json.loads((OUTPUT / "manifest.json").read_text())
rows = manifest["files"]
baseline = next((row for row in rows if row["timestamp"].startswith("2025-06-17")), rows[0])
temporary = default.with_suffix(".tmp")
temporary.unlink(missing_ok=True)
temporary.symlink_to(data / (baseline["sha256"] + ".fits"))
temporary.replace(default)
with urlopen(remote + "/library", timeout=30) as response:
    registered = {row["id"] for row in json.load(response)["observations"]}
missing = {row["sha256"] for row in rows} - registered
if missing:
    raise RuntimeError(f"The running API cannot see {len(missing)} registered files. Check its data directory.")
print(f"Verified {len(rows)} observations in the web app API. Refresh and open Complex → Observation library.", flush=True)
print(f"BACKEND_URL={remote}", flush=True)
'''


def generate(output):
    files = sorted((ROOT / "backend").glob("*.py")) + [
        ROOT / "backend/dataset.json",
        ROOT / "backend/requirements.txt",
        ROOT / "scripts/colab_v572_observations.py",
    ]
    payload = io.BytesIO()
    with ZipFile(payload, "w", ZIP_DEFLATED) as package:
        for file in files:
            package.write(file, file.relative_to(ROOT))
    encoded = base64.b64encode(payload.getvalue()).decode("ascii")
    source = "# Generated by scripts/generate_standalone_colab.py.\nEMBEDDED_BACKEND = (\n"
    source += "".join(f"    {line!r}\n" for line in wrap(encoded, 100))
    source += ")\n" + BOOTSTRAP
    ast.parse(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(source)
    notebook = dict(
        cells=[
            dict(cell_type="markdown", metadata={}, source=[
                "# Nova Velorum: standalone Colab backend\n",
                "Run the code cell. No ZIP upload is needed. The cell prints the private API URL, "
                "then downloads and registers real FITS observations. No video is generated.",
            ]),
            dict(cell_type="code", metadata={}, execution_count=None, outputs=[], source=source.splitlines(keepends=True)),
        ],
        metadata=dict(kernelspec=dict(display_name="Python 3", language="python", name="python3")),
        nbformat=4, nbformat_minor=0,
    )
    output.with_suffix(".ipynb").write_text(json.dumps(notebook, indent=1) + "\n")
    print(f"Generated {output} and {output.with_suffix('.ipynb')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/spherex-colab-standalone.py")
    generate(parser.parse_args().output)
