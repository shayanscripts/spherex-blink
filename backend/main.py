"""Local FastAPI service. Bind to loopback; uploaded files stay in the local cache."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from backend.science import Observation, header_cards

app = FastAPI(title="SPHEREx Single Observation API", version="1.0.0")
DATA_DIR = Path(os.environ.get("SPHEREX_DATA_DIR", Path(__file__).parent / "data"))
REFERENCE_MANIFEST = Path(__file__).parent / "dataset.json"
MAX_BYTES = 256 * 1024 * 1024
Layer = Literal["IMAGE", "VARIANCE", "FLAGS", "ZODI"]


@lru_cache(maxsize=2)
def load(file_id: str) -> Observation:
    if not re.fullmatch(r"[0-9a-f]{64}", file_id):
        raise HTTPException(404, "Observation not found.")
    path = DATA_DIR / f"{file_id}.fits"
    if not path.is_file():
        raise HTTPException(404, "Observation is no longer cached. Please upload it again.")
    try:
        return Observation.read(path)
    except Exception as exc:
        raise HTTPException(422, f"Cannot read observation: {exc}") from exc


@lru_cache(maxsize=8)
def metadata(file_id: str) -> dict:
    record = json.loads((DATA_DIR / f"{file_id}.json").read_text())
    result = load(file_id).metadata(file_id, record["filename"])
    if record.get("archive"):
        origin = record["archive"]
        result["source_url"] = origin["url"]
        result["provenance"] = "Downloaded from the official NASA/IPAC IRSA SPHEREx archive; cutout transformations are provided by IRSA."
        result["notices"] = [n for n in result["notices"] if not n.startswith("SPHEREx provenance")]
        result["release"] = result["release"] or dict(key="Archive path", value=origin["release"], extension="IRSA")
    if REFERENCE_MANIFEST.exists():
        reference = json.loads(REFERENCE_MANIFEST.read_text())
        if file_id == reference.get("sha256"):
            result["source_url"] = reference["url"]
            result["filename"] = reference["filename"]
            result["provenance"] = "SHA-256 matches the reference observation downloaded from NASA/IPAC IRSA."
            result["notices"] = [n for n in result["notices"] if not n.startswith("SPHEREx provenance")]
            if result["release"] is None:
                result["release"] = dict(key="Verified archive path", value="QR2", extension="IRSA")
    return result


def register(path: Path, filename: str) -> dict:
    # Validate before admitting a file to the cache.
    Observation.read(path)
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = DATA_DIR / f"{digest}.fits"
    if not target.exists():
        shutil.copyfile(path, target)
    record = DATA_DIR / f"{digest}.json"
    if not record.exists():
        record.write_text(json.dumps(dict(filename=filename)))
    return metadata(digest)


def require_layer(obs: Observation, layer: str):
    if layer not in obs.arrays:
        raise HTTPException(404, f"{layer} is not present in this observation.")


@app.get("/health")
def health():
    return dict(status="ok", phase=5)


@app.get("/observations/default")
def default_observation():
    configured = os.environ.get("SPHEREX_FITS_PATH")
    path = Path(configured) if configured else (Path("/content/spherex_full.fits") if Path("/content/spherex_full.fits").is_file() else DATA_DIR / "spherex_full.fits")
    if not path.is_file():
        return dict(observation=None, message="No server FITS file is available. Upload your observation to begin.")
    if path.stat().st_size > MAX_BYTES:
        raise HTTPException(413, "Configured observation exceeds 256 MiB.")
    try:
        return dict(observation=register(path, path.name))
    except Exception as exc:
        raise HTTPException(422, f"Configured FITS file could not be read: {exc}") from exc


@app.post("/observations")
async def upload_observation(file: Annotated[UploadFile, File()]):
    filename = Path((file.filename or "observation.fits").replace("\\", "/")).name
    if not filename.lower().endswith((".fits", ".fit", ".fts")):
        await file.close()
        raise HTTPException(415, "Choose an uncompressed .fits, .fit, or .fts file.")
    temporary = None
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=DATA_DIR, suffix=".upload", delete=False) as stream:
            temporary = Path(stream.name)
            size = 0
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "File exceeds the 256 MiB upload limit.")
                stream.write(chunk)
        try:
            return await run_in_threadpool(register, temporary, filename)
        except (ValueError, OSError, KeyError, TypeError, MemoryError) as exc:
            raise HTTPException(422, f"Cannot load this FITS observation: {exc}") from exc
    finally:
        await file.close()
        if temporary:
            temporary.unlink(missing_ok=True)


@app.get("/observations/{file_id}")
def get_observation(file_id: str):
    load(file_id)
    return metadata(file_id)


@app.get("/observations/{file_id}/headers")
def headers(file_id: str, extension: str = "PRIMARY"):
    try:
        return header_cards(load(file_id), extension)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/observations/{file_id}/pixel")
def pixel(file_id: str, x: Annotated[int, Query(ge=0)], y: Annotated[int, Query(ge=0)], layer: Layer = "IMAGE"):
    obs = load(file_id)
    require_layer(obs, layer)
    try:
        return obs.pixel(layer, x, y)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# Imported after service functions are defined to keep the router's cache access explicit.
from backend.workspace import router as workspace_router
app.include_router(workspace_router)


@app.get("/observations/{file_id}/locate")
def locate(file_id: str, ra: Annotated[float, Query(ge=0, lt=360)], dec: Annotated[float, Query(ge=-90, le=90)]):
    try:
        return load(file_id).locate(ra, dec)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/observations/{file_id}/image")
def image(file_id: str, layer: Layer = "IMAGE", stretch: Literal["linear", "asinh", "log"] = "asinh",
          palette: Literal["gray", "amber", "ice"] = "gray", mask: bool = False,
          low: Annotated[float | None, Query(allow_inf_nan=False)] = None,
          high: Annotated[float | None, Query(allow_inf_nan=False)] = None):
    obs = load(file_id)
    require_layer(obs, layer)
    try:
        return Response(obs.render(layer, stretch, palette, mask, low, high), media_type="image/png",
                        headers={"Cache-Control": "private, max-age=3600"})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
