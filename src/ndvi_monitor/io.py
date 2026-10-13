"""Loading and validating scene files (.npz)."""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np

from .core import Scene

MAX_PIXELS = 1_000_000
BAND_KEYS = ("red_1", "nir_1", "red_2", "nir_2")
MASK_KEYS = ("valid_1", "valid_2", "farm")
REQUIRED_KEYS = BAND_KEYS + MASK_KEYS


class SceneError(ValueError):
    """The scene file is missing, malformed or internally inconsistent."""


def _to_mask(name: str, arr: np.ndarray) -> np.ndarray:
    if arr.dtype == bool:
        return arr
    if arr.dtype.kind in "iu" and set(np.unique(arr)).issubset({0, 1}):
        return arr.astype(bool)
    raise SceneError(f"'{name}' must be a boolean (or 0/1) array")


def _text(npz, key: str, default: str) -> str:
    if key not in npz.files:
        return default
    arr = npz[key]
    if arr.dtype.kind not in "US" or arr.size != 1:
        raise SceneError(f"'{key}' must be a single text value")
    return str(arr.reshape(-1)[0])


def load_scene(source) -> Scene:
    """`source` is a path or raw bytes of an .npz file. Pickled data is refused."""
    try:
        fh = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else Path(source)
        npz = np.load(fh, allow_pickle=False)
        files = set(npz.files)
    except Exception as exc:  # BadZipFile, ValueError (pickle), OSError ...
        raise SceneError(f"not a valid .npz scene file: {exc}") from exc

    missing = [k for k in REQUIRED_KEYS if k not in files]
    if missing:
        raise SceneError(f"missing arrays: {', '.join(missing)}")

    arrays = {k: npz[k] for k in REQUIRED_KEYS}
    shapes = {k: a.shape for k, a in arrays.items()}
    if len(set(shapes.values())) != 1:
        raise SceneError(f"arrays must all share one shape (aligned images); got {shapes}")
    shape = next(iter(shapes.values()))
    if len(shape) != 2 or min(shape) < 2:
        raise SceneError(f"arrays must be 2-D with at least 2x2 pixels, got shape {shape}")
    if shape[0] * shape[1] > MAX_PIXELS:
        raise SceneError(f"scene too large: {shape[0] * shape[1]} pixels > {MAX_PIXELS}")
    for k in BAND_KEYS:
        if arrays[k].dtype.kind not in "fiu":
            raise SceneError(f"'{k}' must be numeric, got dtype {arrays[k].dtype}")
    for k in MASK_KEYS:
        arrays[k] = _to_mask(k, arrays[k])

    return Scene(
        red_1=arrays["red_1"], nir_1=arrays["nir_1"], valid_1=arrays["valid_1"],
        red_2=arrays["red_2"], nir_2=arrays["nir_2"], valid_2=arrays["valid_2"],
        farm=arrays["farm"],
        label_1=_text(npz, "label_1", "Date 1"),
        label_2=_text(npz, "label_2", "Date 2"),
        origin=_text(npz, "origin", "unspecified"),
    )
