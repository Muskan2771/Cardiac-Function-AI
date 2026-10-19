"""Overlay rendering and housekeeping for the /analyze endpoint.

Each analysis writes one JPEG per video frame (the frame with the predicted
left-ventricle mask tinted on top) into ``<overlay_root>/<request_id>/``.  The
frontend plays those frames back on a canvas.  Old request folders are deleted
so the server never accumulates patient videos.
"""
from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("cardiac.overlay")

FRAME_PATTERN = "frame_{:04d}.jpg"
_TINT_BGR = (60, 60, 235)  # red-ish in BGR
_CONTOUR_BGR = (80, 220, 255)  # amber outline


def render_overlay(frame_rgb: np.ndarray, mask: np.ndarray, scale: int) -> np.ndarray:
    """Return a BGR image: ``frame_rgb`` upscaled by ``scale`` with the mask drawn on top."""
    h, w = frame_rgb.shape[:2]
    size = (w * scale, h * scale)
    base = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    base = cv2.resize(base, size, interpolation=cv2.INTER_CUBIC)
    big_mask = cv2.resize(mask.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST)

    tinted = base.copy()
    tinted[big_mask > 0] = _TINT_BGR
    out = cv2.addWeighted(tinted, 0.40, base, 0.60, 0.0)

    contours, _ = cv2.findContours(big_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(out, contours, -1, _CONTOUR_BGR, 1, lineType=cv2.LINE_AA)
    return out


def write_overlay_frames(
    frames_rgb: np.ndarray,
    masks: np.ndarray,
    out_dir: Path,
    scale: int = 3,
    quality: int = 85,
) -> int:
    """Write one overlay JPEG per frame.  Returns the number of frames written."""
    if frames_rgb.shape[0] != masks.shape[0]:
        raise ValueError(
            f"frame/mask count mismatch: {frames_rgb.shape[0]} vs {masks.shape[0]}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    for i in range(frames_rgb.shape[0]):
        img = render_overlay(frames_rgb[i], masks[i], scale)
        ok = cv2.imwrite(
            str(out_dir / FRAME_PATTERN.format(i)),
            img,
            [int(cv2.IMWRITE_JPEG_QUALITY), quality],
        )
        if not ok:
            raise IOError(f"could not write overlay frame {i} to {out_dir}")
    return int(frames_rgb.shape[0])


def cleanup_old_overlays(root: Path, ttl_seconds: int, keep_last: int = 50) -> int:
    """Delete request folders older than ``ttl_seconds`` (and any beyond ``keep_last``).

    Returns the number of folders removed.  Never raises: cleanup problems are
    logged and must not break a user's request.
    """
    removed = 0
    try:
        dirs = [d for d in root.iterdir() if d.is_dir()]
        dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        now = time.time()
        for rank, d in enumerate(dirs):
            too_old = now - d.stat().st_mtime > ttl_seconds
            too_many = rank >= keep_last
            if too_old or too_many:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
    except OSError as exc:  # pragma: no cover - defensive
        log.warning("overlay cleanup failed: %s", exc)
    return removed
