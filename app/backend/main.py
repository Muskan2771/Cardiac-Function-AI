"""FastAPI backend: echocardiogram video -> LV overlay + EF + risk flag.

Wires Contract 1 (``segmentation_module``) into Contract 2 (``ef_module``) and
exposes the result as Contract 3 (``POST /analyze``).  The model is loaded once
at start-up.  In production the same process also serves the built React
frontend, so the whole product lives behind a single URL.

Configuration (environment variables)
-------------------------------------
SEG_CKPT            path to the fine-tuned DeepLabV3 checkpoint (.pth)
MODEL_URL           optional: download the checkpoint from here if SEG_CKPT is missing
MODEL_SHA256        optional: expected sha256 of the downloaded checkpoint
MODEL_AUTH_TOKEN    optional: bearer token (e.g. a Hugging Face token for a private model repo)
MAX_UPLOAD_MB       reject uploads larger than this (default 50)
MIN_FRAMES          reject clips with fewer frames (default 10)
MAX_FRAMES          reject clips with more frames (default 600)
ALLOWED_ORIGINS     comma separated CORS origins (default: local Vite dev server)
OVERLAY_DIR         where overlay frames are written (default: system temp dir)
OVERLAY_TTL_SECONDS how long overlay frames are kept (default 1800)
FRONTEND_DIR        built frontend to serve at "/" (default: app/frontend/dist)
MAX_CONCURRENT      simultaneous analyses (default 1; the model is CPU-heavy)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import tempfile
import urllib.request
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

_BASE = Path(__file__).resolve().parent
_ROOT = _BASE.parent.parent

sys.path.insert(0, str(_BASE))
sys.path.insert(0, str(_ROOT / "segmentation"))
sys.path.insert(0, str(_ROOT / "ef_engine"))

from ef_module import compute_ef, compute_volume_curve  # noqa: E402
from overlay import FRAME_PATTERN, cleanup_old_overlays, write_overlay_frames  # noqa: E402
from segmentation_module import (  # noqa: E402
    extract_frames,
    load_segmentation_model,
    segment_video,
)

log = logging.getLogger("cardiac.api")

DISCLAIMER = (
    "Screening aid only - not a diagnosis. Results must be reviewed by a qualified clinician."
)
ALLOWED_EXTENSIONS = {".avi", ".mp4", ".mov", ".m4v", ".mkv", ".webm"}
CHUNK = 1024 * 1024


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class Settings:
    """Read once per app instance so tests can override the environment."""

    def __init__(self) -> None:
        self.checkpoint = Path(
            os.environ.get(
                "SEG_CKPT",
                str(_ROOT / "segmentation" / "checkpoints" / "deeplabv3_lv_segmentation.pth"),
            )
        )
        self.model_url = os.environ.get("MODEL_URL", "").strip()
        self.model_sha256 = os.environ.get("MODEL_SHA256", "").strip().lower()
        self.model_auth_token = os.environ.get("MODEL_AUTH_TOKEN", "").strip()
        self.max_upload_bytes = _env_int("MAX_UPLOAD_MB", 50) * 1024 * 1024
        self.min_frames = _env_int("MIN_FRAMES", 10)
        self.max_frames = _env_int("MAX_FRAMES", 600)
        self.overlay_dir = Path(
            os.environ.get("OVERLAY_DIR", str(Path(tempfile.gettempdir()) / "cardiac_overlays"))
        )
        self.overlay_ttl = _env_int("OVERLAY_TTL_SECONDS", 1800)
        self.overlay_scale = _env_int("OVERLAY_SCALE", 3)
        self.frontend_dir = Path(os.environ.get("FRONTEND_DIR", str(_ROOT / "app" / "frontend" / "dist")))
        self.max_concurrent = max(1, _env_int("MAX_CONCURRENT", 1))
        origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        self.allowed_origins = [o.strip() for o in origins.split(",") if o.strip()]


# --------------------------------------------------------------------------- model


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _download_checkpoint(url: str, dest: Path, expected_sha256: str, token: str = "") -> None:
    """Download the checkpoint (e.g. from a Hugging Face model repo) and verify it."""
    if not url.startswith("https://"):
        raise RuntimeError("MODEL_URL must be an https:// URL")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    log.info("downloading model checkpoint from %s", url)
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    with urllib.request.urlopen(request, timeout=120) as resp, open(tmp, "wb") as out:  # noqa: S310
        while True:
            block = resp.read(CHUNK)
            if not block:
                break
            out.write(block)
    if expected_sha256 and _sha256(tmp) != expected_sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("downloaded checkpoint does not match MODEL_SHA256")
    tmp.replace(dest)


def _read_model_meta(checkpoint: Path) -> dict:
    """Read ``<checkpoint>.meta.json`` - says what the model was trained/validated on."""
    meta_path = checkpoint.with_suffix(".meta.json")
    meta = {
        "name": "DeepLabV3-ResNet50 (LV segmentation)",
        "trained_on": "unknown",
        "real_data": False,
    }
    try:
        meta.update(json.loads(meta_path.read_text()))
    except (OSError, ValueError):
        pass
    meta["real_data"] = bool(meta.get("real_data", False))
    return meta


def load_model_if_available(settings: Settings):
    """Return ``(model, error)``.  Never raises - the app stays up and reports the problem."""
    try:
        if not settings.checkpoint.exists() and settings.model_url:
            _download_checkpoint(
                settings.model_url, settings.checkpoint, settings.model_sha256, settings.model_auth_token
            )
        if not settings.checkpoint.exists():
            return None, f"checkpoint not found at {settings.checkpoint}"
        return load_segmentation_model(str(settings.checkpoint)), None
    except Exception as exc:  # noqa: BLE001 - report any start-up failure via /health
        log.exception("could not load model")
        return None, f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- app


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.overlay_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.model, app.state.model_error = await run_in_threadpool(
            load_model_if_available, settings
        )
        app.state.model_meta = _read_model_meta(settings.checkpoint)
        app.state.slots = asyncio.Semaphore(settings.max_concurrent)
        yield

    app = FastAPI(
        title="Cardiac Function AI",
        description="Echocardiogram video -> left-ventricle overlay, ejection fraction and risk flag.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.model = None
    app.state.model_error = "model not loaded yet"
    app.state.model_meta = {}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        loaded = app.state.model is not None
        return {
            "status": "ok" if loaded else "model_unavailable",
            "model_loaded": loaded,
            "model_error": app.state.model_error,
            "model": app.state.model_meta,
        }

    @app.post("/analyze")
    async def analyze(file: Annotated[UploadFile, File()]):
        if app.state.model is None:
            raise HTTPException(503, "The segmentation model is not available on this server.")

        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                415, f"Unsupported file type '{suffix or 'unknown'}'. Upload an .avi or .mp4 echo video."
            )

        request_id = uuid.uuid4().hex
        with tempfile.TemporaryDirectory(prefix="echo_") as tmp_dir:
            video_path = Path(tmp_dir) / f"upload{suffix}"
            await _save_upload(file, video_path, settings.max_upload_bytes)
            async with app.state.slots:
                payload = await run_in_threadpool(
                    _analyze_video,
                    video_path,
                    file.filename or video_path.name,
                    request_id,
                    app.state.model,
                    app.state.model_meta,
                    settings,
                )
        return payload

    app.mount("/static/overlays", StaticFiles(directory=settings.overlay_dir), name="overlays")

    if settings.frontend_dir.is_dir():
        # Mounted last so it never shadows the API routes above.
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    else:

        @app.get("/")
        def root():
            return JSONResponse({"service": "Cardiac Function AI", "docs": "/docs", "health": "/health"})

    return app


async def _save_upload(file: UploadFile, dest: Path, max_bytes: int) -> None:
    written = 0
    with open(dest, "wb") as out:
        while True:
            block = await file.read(CHUNK)
            if not block:
                break
            written += len(block)
            if written > max_bytes:
                raise HTTPException(
                    413, f"File is too large (limit {max_bytes // (1024 * 1024)} MB)."
                )
            out.write(block)
    if written == 0:
        raise HTTPException(400, "The uploaded file is empty.")


def _analyze_video(
    video_path: Path,
    original_name: str,
    request_id: str,
    model,
    model_meta: dict,
    settings: Settings,
) -> dict:
    """Blocking part of the request: decode -> segment -> EF -> overlay frames."""
    try:
        frames = extract_frames(str(video_path))
    except (IOError, cv2.error) as exc:
        raise HTTPException(422, "This file could not be read as a video.") from exc

    n_frames = int(frames.shape[0])
    if n_frames < settings.min_frames:
        raise HTTPException(
            422,
            f"Video is too short ({n_frames} frames). At least {settings.min_frames} frames "
            "covering one heartbeat are needed.",
        )
    if n_frames > settings.max_frames:
        raise HTTPException(
            422, f"Video is too long ({n_frames} frames; limit {settings.max_frames})."
        )

    masks = segment_video(str(video_path), model)
    try:
        result = compute_ef(masks)
    except ValueError as exc:
        raise HTTPException(
            422,
            "No left ventricle was detected in this video, so ejection fraction cannot be "
            "computed. Check that it is an apical four-chamber echo clip.",
        ) from exc

    curve = compute_volume_curve(masks)
    empty_frames = np.where(masks.sum(axis=(1, 2)) == 0)[0].tolist()
    warnings = []
    if empty_frames:
        warnings.append(
            f"{len(empty_frames)} of {n_frames} frames had no detected left ventricle; "
            "the EF estimate may be unreliable."
        )
    if result["ed_frame"] == result["es_frame"]:
        warnings.append("No change in ventricular volume was detected across the clip.")

    fps = _read_fps(video_path)

    cleanup_old_overlays(settings.overlay_dir, settings.overlay_ttl)
    write_overlay_frames(
        frames, masks, settings.overlay_dir / request_id, scale=settings.overlay_scale
    )

    return {
        "request_id": request_id,
        "video": original_name,
        "ef_percent": round(result["ef_percent"], 2),
        "edv": round(result["edv"], 2),
        "esv": round(result["esv"], 2),
        "risk_flag": result["risk_flag"],
        "ed_frame": int(result["ed_frame"]),
        "es_frame": int(result["es_frame"]),
        "overlay_frames_url": f"/static/overlays/{request_id}/",
        # ---- additive fields (Contract 3 is extended, never changed) ----
        "frame_pattern": FRAME_PATTERN,
        "n_frames": n_frames,
        "fps": fps,
        "volume_curve": [round(float(v), 2) for v in curve],
        "volume_units": "relative (pixel^3), not millilitres",
        "warnings": warnings,
        "model": model_meta,
        "disclaimer": DISCLAIMER,
    }


def _read_fps(video_path: Path) -> float:
    cap = cv2.VideoCapture(str(video_path))
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    finally:
        cap.release()
    return round(fps, 2) if 1.0 <= fps <= 240.0 else 30.0


app = create_app()
