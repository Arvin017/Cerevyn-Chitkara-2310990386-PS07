import csv
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

from ndvi_monitor import api
from ndvi_monitor.core import analyze
from ndvi_monitor.io import load_scene
from ndvi_monitor.report import write_outputs

from conftest import SAMPLE


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "OUTPUT_DIR", tmp_path)
    return TestClient(api.app)


def test_health_and_dashboard(client):
    assert client.get("/health").json()["status"] == "ok"
    assert "NDVI Vegetation Change Monitor" in client.get("/").text


def test_analyze_sample_returns_expected_numbers(client, expected):
    r = client.post("/api/analyze/sample")
    assert r.status_code == 200
    body = r.json()
    assert body["comparison"]["common_pixels"] == expected["comparison"]["common_pixels"]
    assert body["comparison"]["mean_change"] == pytest.approx(expected["comparison"]["mean_change"], abs=1e-5)
    assert body["decision"]["status"] == "decline_flagged"
    assert "does not by itself establish" in body["interpretation_note"]


def test_threshold_query_param_changes_decision(client):
    r = client.post("/api/analyze/sample", params={"mean_decline_threshold": 0.10})
    assert r.json()["decision"]["status"] == "no_significant_decline"


@pytest.mark.parametrize("params", [{"mean_decline_threshold": 0}, {"pixel_decline_threshold": 5}, {"min_usable_pct": 150}])
def test_invalid_thresholds_rejected(client, params):
    assert client.post("/api/analyze/sample", params=params).status_code == 422


def test_upload_valid_file_and_download_all_outputs(client):
    r = client.post("/api/analyze/upload", files={"file": ("scene.npz", SAMPLE.read_bytes())})
    assert r.status_code == 200
    for name, url in r.json()["downloads"].items():
        d = client.get(url)
        assert d.status_code == 200 and len(d.content) > 0, name
    assert client.get(r.json()["downloads"]["heatmap"]).content[:8] == b"\x89PNG\r\n\x1a\n"


def test_same_upload_gives_same_run_id(client):
    files = lambda: {"file": ("s.npz", SAMPLE.read_bytes())}
    assert client.post("/api/analyze/upload", files=files()).json()["run_id"] == \
           client.post("/api/analyze/upload", files=files()).json()["run_id"]


def test_upload_bad_inputs_rejected(client):
    assert client.post("/api/analyze/upload", files={"file": ("x.npz", b"junk")}).status_code == 422
    assert client.post("/api/analyze/upload", files={"file": ("x.npz", b"")}).status_code == 422
    buf = io.BytesIO()
    m = np.ones((10, 10), bool); z = np.full((10, 10), 0.5)
    np.savez(buf, red_1=z, nir_1=z, valid_1=m, red_2=np.zeros((9, 9)), nir_2=z, valid_2=m, farm=m)
    r = client.post("/api/analyze/upload", files={"file": ("x.npz", buf.getvalue())})
    assert r.status_code == 422 and "share one shape" in r.json()["detail"]


def test_download_rejects_unknown_and_path_traversal_ids(client):
    assert client.get("/api/runs/abcdef012345/results").status_code == 404
    assert client.get("/api/runs/..%2f..%2fetc/results").status_code == 404
    assert client.get("/api/runs/abcdef012345/secrets").status_code == 404


def test_csv_has_one_row_per_pixel_and_no_value_for_excluded_pixels(tmp_path):
    a = analyze(load_scene(SAMPLE))
    paths = write_outputs(a, tmp_path)
    rows = list(csv.DictReader(paths["pixels"].open()))
    assert len(rows) == 144
    zero_den = next(r for r in rows if r["row"] == "3" and r["col"] == "3")
    assert zero_den["ndvi_1"] == "" and zero_den["reason_1"] == "zero_denominator"
    assert zero_den["used_in_comparison"] == "0" and zero_den["change"] == ""
    assert sum(int(r["used_in_comparison"]) for r in rows) == 89
    declined = next(r for r in rows if r["row"] == "8" and r["col"] == "8")
    assert float(declined["change"]) == pytest.approx(-0.3)
