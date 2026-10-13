"""FastAPI service + small dashboard."""
from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from . import __version__
from .config import Config
from .core import analyze
from .io import SceneError, load_scene
from .report import FILES, write_outputs

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
SAMPLE_SCENE = Path(os.getenv("SAMPLE_SCENE", ROOT / "sample_data" / "farm_scene.npz"))
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
STATIC = Path(__file__).parent / "static"
RUN_ID_RE = re.compile(r"^[0-9a-f]{12}$")
MEDIA = {"results": "application/json", "pixels": "text/csv", "heatmap": "image/png"}

app = FastAPI(title="NDVI Vegetation Change Monitor", version=__version__)


def get_config(
    mean_decline_threshold: float = Query(0.05, gt=0, le=2),
    pixel_decline_threshold: float = Query(0.10, gt=0, le=2),
    min_usable_pct: float = Query(50.0, ge=0, le=100),
) -> Config:
    return Config(mean_decline_threshold, pixel_decline_threshold, min_usable_pct)


def _run(scene, config: Config) -> dict:
    try:
        analysis = analyze(scene, config)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    write_outputs(analysis, OUTPUT_DIR)
    base = f"/api/runs/{analysis.run_id}"
    return {
        "run_id": analysis.run_id,
        **analysis.summary,
        "downloads": {k: f"{base}/{k}" for k in FILES},
    }


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC / "index.html")


@app.post("/api/analyze/sample")
def analyze_sample(config: Config = Depends(get_config)):
    try:
        scene = load_scene(SAMPLE_SCENE)
    except SceneError as exc:
        raise HTTPException(500, f"bundled sample unavailable: {exc}") from exc
    return _run(scene, config)


@app.post("/api/analyze/upload")
async def analyze_upload(file: UploadFile = File(...), config: Config = Depends(get_config)):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file larger than 5 MB")
    if not data:
        raise HTTPException(422, "empty file")
    try:
        scene = load_scene(data)
    except SceneError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _run(scene, config)


@app.get("/api/runs/{run_id}/{kind}")
def download(run_id: str, kind: str):
    if not RUN_ID_RE.match(run_id) or kind not in FILES:
        raise HTTPException(404, "not found")
    path = OUTPUT_DIR / run_id / FILES[kind]
    if not path.is_file():
        raise HTTPException(404, "run not found - run the analysis first")
    return FileResponse(path, media_type=MEDIA[kind], filename=FILES[kind]
                        if kind != "heatmap" else None)
