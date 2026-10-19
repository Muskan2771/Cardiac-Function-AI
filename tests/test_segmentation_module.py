"""Contract 1 tests against the REAL DeepLabV3 code path (randomly initialised weights, no network)."""
import numpy as np
import pytest
import torch

import segmentation_module as sm
from conftest import SIZE, write_video


@pytest.fixture(scope="module")
def checkpoint(tmp_path_factory):
    path = tmp_path_factory.mktemp("ckpt") / "random.pth"
    torch.save(sm._build_model(pretrained=False).state_dict(), path)
    return path


def test_model_has_single_channel_heads():
    model = sm._build_model(pretrained=False)
    assert model.classifier[4].out_channels == 1
    assert model.aux_classifier is not None and model.aux_classifier[4].out_channels == 1


def test_load_by_path_only_and_eval_mode(checkpoint):
    model = sm.load_segmentation_model(str(checkpoint))
    assert not model.training


def test_segment_video_matches_contract_1(checkpoint, echo_video):
    model = sm.load_segmentation_model(str(checkpoint))
    frames = sm.extract_frames(str(echo_video))
    masks = sm.segment_video(str(echo_video), model)
    assert frames.shape == (30, SIZE, SIZE, 3) and frames.dtype == np.uint8
    assert masks.shape == (30, SIZE, SIZE) and masks.dtype == np.uint8
    assert set(np.unique(masks).tolist()) <= {0, 1}


def test_extract_frames_returns_rgb_not_bgr(tmp_path):
    red_bgr = (0, 0, 255)
    video = write_video(tmp_path / "red.avi", n_frames=3, color=red_bgr)
    frame = sm.extract_frames(str(video))[0]
    r, g, b = frame.reshape(-1, 3).mean(axis=0)
    assert r > 150 and g < 90 and b < 90


def test_extract_frames_resizes(tmp_path, echo_video):
    assert sm.extract_frames(str(echo_video), resize=(56, 56)).shape[1:3] == (56, 56)


def test_unreadable_video_raises_ioerror(tmp_path):
    with pytest.raises(IOError):
        sm.extract_frames(str(tmp_path / "does_not_exist.avi"))
