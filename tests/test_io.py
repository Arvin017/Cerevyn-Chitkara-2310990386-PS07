import io

import numpy as np
import pytest

from ndvi_monitor.io import SceneError, load_scene

from conftest import SAMPLE


def _npz_bytes(**arrays) -> bytes:
    buf = io.BytesIO()
    np.savez(buf, **arrays)
    return buf.getvalue()


def _valid_arrays(n=10):
    z = np.full((n, n), 0.5)
    m = np.ones((n, n), bool)
    return dict(red_1=z, nir_1=z, valid_1=m, red_2=z, nir_2=z, valid_2=m, farm=m)


def test_loads_sample_with_metadata():
    s = load_scene(SAMPLE)
    assert s.farm.shape == (12, 12) and s.farm.sum() == 100
    assert s.label_1 == "2026-06-01" and "synthetic" in s.origin


def test_loads_from_bytes():
    assert load_scene(_npz_bytes(**_valid_arrays())).farm.shape == (10, 10)


def test_missing_array_rejected():
    arrs = _valid_arrays(); del arrs["nir_2"]
    with pytest.raises(SceneError, match="missing arrays: nir_2"):
        load_scene(_npz_bytes(**arrs))


def test_misaligned_shapes_rejected_not_compared():
    arrs = _valid_arrays(); arrs["red_2"] = np.zeros((9, 10))
    with pytest.raises(SceneError, match="share one shape"):
        load_scene(_npz_bytes(**arrs))


def test_non_boolean_mask_rejected():
    arrs = _valid_arrays(); arrs["valid_1"] = np.full((10, 10), 0.5)
    with pytest.raises(SceneError, match="valid_1"):
        load_scene(_npz_bytes(**arrs))


def test_zero_one_integer_mask_accepted():
    arrs = _valid_arrays(); arrs["farm"] = np.ones((10, 10), dtype=np.uint8)
    assert load_scene(_npz_bytes(**arrs)).farm.dtype == bool


def test_garbage_and_pickled_files_rejected():
    with pytest.raises(SceneError):
        load_scene(b"not a zip file")
    buf = io.BytesIO()
    np.savez(buf, red_1=np.array([{"a": 1}], dtype=object))
    with pytest.raises(SceneError):
        load_scene(buf.getvalue())


def test_non_numeric_band_rejected():
    arrs = _valid_arrays(); arrs["red_1"] = np.full((10, 10), "x")
    with pytest.raises(SceneError, match="numeric"):
        load_scene(_npz_bytes(**arrs))
