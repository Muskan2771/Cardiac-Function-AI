"""Shared fixtures. Adds the three source folders to sys.path (same as the backend does)."""
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
for sub in ("app/backend", "segmentation", "ef_engine"):
    sys.path.insert(0, str(ROOT / sub))

SIZE = 112


def write_video(path: Path, n_frames: int = 30, pulsing: bool = True, color=None) -> Path:
    """Write a tiny echo-like AVI: a bright ellipse whose radius pulses over one 'heartbeat'.

    Frame 0 is end-diastole (largest), frame n/2 is end-systole (smallest).
    """
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (SIZE, SIZE))
    assert writer.isOpened(), "OpenCV could not open a MJPG VideoWriter"
    for i in range(n_frames):
        frame = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
        if color is not None:
            frame[:] = color
        elif pulsing:
            radius = 14 + 6 * np.cos(2 * np.pi * i / n_frames)
            cv2.circle(frame, (SIZE // 2, SIZE // 2), int(round(radius)), (200, 200, 200), -1)
        writer.write(frame)
    writer.release()
    return path


def pulsing_masks(n_frames: int) -> np.ndarray:
    """Ground-truth masks matching ``write_video`` (stand-in for a perfect model)."""
    masks = np.zeros((n_frames, SIZE, SIZE), dtype=np.uint8)
    for i in range(n_frames):
        radius = 14 + 6 * np.cos(2 * np.pi * i / n_frames)
        cv2.circle(masks[i], (SIZE // 2, SIZE // 2), int(round(radius)), 1, -1)
    return masks


@pytest.fixture()
def echo_video(tmp_path) -> Path:
    return write_video(tmp_path / "echo.avi", n_frames=30)
