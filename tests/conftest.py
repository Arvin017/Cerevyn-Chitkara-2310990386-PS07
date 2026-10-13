import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample_data" / "farm_scene.npz"
EXPECTED = ROOT / "sample_data" / "expected_results.json"


@pytest.fixture
def expected():
    return json.loads(EXPECTED.read_text())


def make_scene(shape=(10, 10), farm=None, red=0.2, nir=0.6, valid_1=None, valid_2=None, red_2=None, nir_2=None):
    """Small helper: uniform scene, optionally with custom masks / second-date bands."""
    from ndvi_monitor.core import Scene

    ones = np.ones(shape, dtype=bool)
    f = ones.copy() if farm is None else farm
    return Scene(
        red_1=np.full(shape, red), nir_1=np.full(shape, nir), valid_1=ones.copy() if valid_1 is None else valid_1,
        red_2=np.full(shape, red if red_2 is None else red_2),
        nir_2=np.full(shape, nir if nir_2 is None else nir_2),
        valid_2=ones.copy() if valid_2 is None else valid_2, farm=f, origin="test",
    )
