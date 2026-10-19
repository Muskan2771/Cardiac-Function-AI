"""API tests. The segmentation model is replaced by a stand-in so these run in seconds."""
import os

import numpy as np
import pytest
from conftest import SIZE, pulsing_masks, write_video
from fastapi.testclient import TestClient

CONTRACT_KEYS = {
    "ef_percent", "edv", "esv", "risk_flag", "ed_frame", "es_frame", "overlay_frames_url",
}


@pytest.fixture()
def make_client(tmp_path, monkeypatch):
    """Factory: build an app with a fake model, optionally overriding settings."""

    def _make(model_present: bool = True, masks_fn=None, **env):
        import main

        ckpt = tmp_path / "model.pth"
        if model_present:
            ckpt.write_bytes(b"fake")
            (tmp_path / "model.meta.json").write_text(
                '{"trained_on": "unit-test data", "real_data": false}'
            )
        monkeypatch.setenv("SEG_CKPT", str(ckpt))
        monkeypatch.setenv("OVERLAY_DIR", str(tmp_path / "overlays"))
        monkeypatch.setenv("FRONTEND_DIR", str(tmp_path / "no-frontend"))
        for key, value in env.items():
            monkeypatch.setenv(key, str(value))
        monkeypatch.setattr(main, "load_segmentation_model", lambda path: "fake-model")
        monkeypatch.setattr(
            main, "segment_video",
            masks_fn or (lambda path, model: pulsing_masks(main.extract_frames(path).shape[0])),
        )
        return TestClient(main.create_app(main.Settings()))

    return _make


def post_video(client, path, name=None):
    with open(path, "rb") as fh:
        return client.post("/analyze", files={"file": (name or path.name, fh, "video/x-msvideo")})


def test_health_reports_model_and_provenance(make_client):
    with make_client() as client:
        body = client.get("/health").json()
    assert body["model_loaded"] is True
    assert body["model"]["trained_on"] == "unit-test data"
    assert body["model"]["real_data"] is False


def test_health_when_model_missing_still_200(make_client):
    with make_client(model_present=False) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["model_loaded"] is False


def test_analyze_returns_contract_3(make_client, echo_video):
    with make_client() as client:
        response = post_video(client, echo_video)
        assert response.status_code == 200, response.text
        body = response.json()
        assert CONTRACT_KEYS <= set(body)
        assert body["ed_frame"] == 0
        # integer-rounded radii give a flat minimum around frame 15, so allow +/-1
        assert abs(body["es_frame"] - 15) <= 1
        expected_ef = (1 - (8 / 20) ** 3) * 100  # radius 20 -> 8, volume ~ r^3
        assert abs(body["ef_percent"] - expected_ef) < 6
        assert body["risk_flag"] == "Normal"
        assert body["n_frames"] == 30 and len(body["volume_curve"]) == 30
        assert body["overlay_frames_url"] == f"/static/overlays/{body['request_id']}/"
        assert "diagnosis" in body["disclaimer"].lower()

        # overlay frames are actually served
        first = client.get(body["overlay_frames_url"] + "frame_0000.jpg")
        last = client.get(body["overlay_frames_url"] + "frame_0029.jpg")
        assert first.status_code == 200 and first.headers["content-type"] == "image/jpeg"
        assert last.status_code == 200


def test_requests_do_not_share_files(make_client, echo_video):
    with make_client() as client:
        a = post_video(client, echo_video).json()
        b = post_video(client, echo_video).json()
    assert a["request_id"] != b["request_id"]


def test_missing_file_is_422_not_500(make_client):
    with make_client() as client:
        assert client.post("/analyze").status_code == 422


def test_wrong_extension_is_415(make_client, tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with make_client() as client:
        assert post_video(client, bad).status_code == 415


def test_empty_file_is_400(make_client, tmp_path):
    empty = tmp_path / "empty.avi"
    empty.write_bytes(b"")
    with make_client() as client:
        assert post_video(client, empty).status_code == 400


def test_corrupt_video_is_422_with_clear_message(make_client, tmp_path):
    corrupt = tmp_path / "corrupt.avi"
    corrupt.write_bytes(os.urandom(4096))
    with make_client() as client:
        response = post_video(client, corrupt)
    assert response.status_code == 422
    assert "could not be read" in response.json()["detail"]


def test_too_short_video_is_422(make_client, tmp_path):
    short = write_video(tmp_path / "short.avi", n_frames=5)
    with make_client() as client:
        response = post_video(client, short)
    assert response.status_code == 422
    assert "too short" in response.json()["detail"]


def test_oversized_upload_is_413(make_client, tmp_path):
    big = tmp_path / "big.avi"
    big.write_bytes(b"\0" * (2 * 1024 * 1024))
    with make_client(MAX_UPLOAD_MB=1) as client:
        assert post_video(client, big).status_code == 413


def test_model_unavailable_is_503(make_client, echo_video):
    with make_client(model_present=False) as client:
        assert post_video(client, echo_video).status_code == 503


def test_no_ventricle_detected_is_422(make_client, echo_video):
    empty_masks = lambda path, model: np.zeros((30, SIZE, SIZE), dtype=np.uint8)  # noqa: E731
    with make_client(masks_fn=empty_masks) as client:
        response = post_video(client, echo_video)
    assert response.status_code == 422
    assert "No left ventricle" in response.json()["detail"]


def test_partial_empty_masks_produce_a_warning(make_client, echo_video):
    def masks_with_gaps(path, model):
        masks = pulsing_masks(30)
        masks[3] = 0
        return masks

    with make_client(masks_fn=masks_with_gaps) as client:
        body = post_video(client, echo_video).json()
    assert any("no detected left ventricle" in w for w in body["warnings"])


def test_old_overlays_are_cleaned_up(tmp_path):
    import time

    from overlay import cleanup_old_overlays

    old, fresh = tmp_path / "old", tmp_path / "fresh"
    old.mkdir()
    fresh.mkdir()
    long_ago = time.time() - 10_000
    os.utime(old, (long_ago, long_ago))
    assert cleanup_old_overlays(tmp_path, ttl_seconds=60) == 1
    assert not old.exists() and fresh.exists()
