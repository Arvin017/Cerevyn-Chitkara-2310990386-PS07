import numpy as np
import pytest

from ndvi_monitor.config import Config
from ndvi_monitor.core import (MASKED, NON_FINITE, OK, OUT_OF_RANGE, ZERO_DENOM, analyze,
                               compute_ndvi, fingerprint)
from ndvi_monitor.io import load_scene

from conftest import SAMPLE, make_scene


# ---- NDVI formula -------------------------------------------------------------------
def test_ndvi_nir_06_red_02_is_05():
    ndvi, reason = compute_ndvi(np.array([[0.2]]), np.array([[0.6]]))
    assert ndvi[0, 0] == pytest.approx(0.5)
    assert reason[0, 0] == OK


def test_zero_denominator_is_nan_and_labelled_not_zero_filled():
    red = np.array([[0.0, 0.2]])
    nir = np.array([[0.0, 0.6]])
    ndvi, reason = compute_ndvi(red, nir)
    assert np.isnan(ndvi[0, 0]) and reason[0, 0] == ZERO_DENOM
    assert ndvi[0, 1] == pytest.approx(0.5)


def test_masked_nonfinite_and_out_of_range_pixels_get_no_value():
    red = np.array([[0.2, np.nan, -0.5, 0.2]])
    nir = np.array([[0.6, 0.6, 0.1, 0.6]])
    valid = np.array([[False, True, True, True]])
    ndvi, reason = compute_ndvi(red, nir, valid)
    assert list(reason[0]) == [MASKED, NON_FINITE, OUT_OF_RANGE, OK]
    assert np.isnan(ndvi[0, :3]).all() and ndvi[0, 3] == pytest.approx(0.5)


def test_masked_pixel_with_zero_denominator_reports_masked():
    _, reason = compute_ndvi(np.array([[0.0]]), np.array([[0.0]]), np.array([[False]]))
    assert reason[0, 0] == MASKED


# ---- comparison area -----------------------------------------------------------------
def test_different_cloud_masks_use_intersection_only():
    v1 = np.ones((10, 10), bool); v1[0, :] = False       # 10 px cloudy on date 1
    v2 = np.ones((10, 10), bool); v2[:, 0] = False       # 10 px cloudy on date 2 (1 overlap)
    a = analyze(make_scene(valid_1=v1, valid_2=v2))
    assert a.summary["date_1"]["usable_pixels"] == 90
    assert a.summary["date_2"]["usable_pixels"] == 90
    assert a.summary["comparison"]["common_pixels"] == 81     # 100 - 10 - 10 + 1
    assert a.common.sum() == 81 and np.isnan(a.change[0, :]).all() and np.isnan(a.change[:, 0]).all()


def test_pixels_outside_farm_are_ignored_even_if_they_change_a_lot():
    farm = np.zeros((10, 10), bool); farm[2:8, 2:8] = True
    scene = make_scene(farm=farm)
    scene.red_2[~farm], scene.nir_2[~farm] = 0.3, 0.3          # NDVI collapses outside the farm
    a = analyze(scene)
    assert a.summary["comparison"]["common_pixels"] == 36
    assert a.summary["comparison"]["mean_change"] == pytest.approx(0.0)
    assert a.summary["decision"]["status"] == "no_significant_decline"


def test_entirely_masked_area_reports_no_numbers():
    a = analyze(make_scene(valid_2=np.zeros((10, 10), bool)))
    c = a.summary["comparison"]
    assert a.summary["decision"]["status"] == "insufficient_data"
    assert c["common_pixels"] == 0
    assert c["mean_change"] is None and c["mean_ndvi_date_2"] is None
    assert a.summary["date_2"]["mean_ndvi_on_usable"] is None
    assert a.summary["date_2"]["usable_pct_of_farm"] == 0.0


def test_min_usable_pct_gate():
    v2 = np.ones((10, 10), bool); v2[:6, :] = False            # only 40 % usable on date 2
    a = analyze(make_scene(valid_2=v2), Config(min_usable_pct=50))
    assert a.summary["decision"]["status"] == "insufficient_data"
    b = analyze(make_scene(valid_2=v2), Config(min_usable_pct=30))
    assert b.summary["decision"]["status"] != "insufficient_data"


# ---- decision rule -------------------------------------------------------------------
def test_decline_flag_respects_configurable_threshold():
    scene = make_scene(red_2=0.3, nir_2=0.5)                   # NDVI 0.5 -> 0.25 (change -0.25)
    assert analyze(scene, Config(mean_decline_threshold=0.2)).summary["decision"]["status"] == "decline_flagged"
    assert analyze(scene, Config(mean_decline_threshold=0.3)).summary["decision"]["status"] == "no_significant_decline"


def test_threshold_boundary_is_inclusive():
    scene = make_scene(red_2=0.3, nir_2=0.5)                   # change is exactly -0.25
    assert analyze(scene, Config(mean_decline_threshold=0.25)).summary["decision"]["status"] == "decline_flagged"


def test_increase_is_not_flagged():
    a = analyze(make_scene(red=0.3, nir=0.5, red_2=0.1, nir_2=0.9))
    assert a.summary["comparison"]["mean_change"] > 0
    assert a.summary["decision"]["status"] == "no_significant_decline"


def test_invalid_config_rejected():
    for bad in (Config(mean_decline_threshold=0), Config(pixel_decline_threshold=3), Config(min_usable_pct=101)):
        with pytest.raises(ValueError):
            bad.validate()


def test_empty_farm_and_shape_mismatch_rejected():
    with pytest.raises(ValueError, match="no pixels"):
        analyze(make_scene(farm=np.zeros((10, 10), bool)))
    scene = make_scene()
    scene.red_2 = np.zeros((9, 10))
    with pytest.raises(ValueError, match="share one shape"):
        analyze(scene)


# ---- sample scene vs hand-derived expectations ---------------------------------------
def _approx_dict(actual, exp):
    for k, v in exp.items():
        if isinstance(v, dict):
            _approx_dict(actual[k], v)
        else:
            assert actual[k] == pytest.approx(v, abs=1e-5), k


def test_sample_scene_matches_hand_derived_expected_results(expected):
    a = analyze(load_scene(SAMPLE))
    s = a.summary
    assert s["scene"]["farm_pixels"] == expected["farm_pixels"]
    for key in ("date_1", "date_2", "comparison"):
        _approx_dict(s[key], expected[key])
    assert s["decision"]["status"] == expected["decision_status_default_config"]


def test_sample_scene_not_flagged_at_higher_threshold():
    a = analyze(load_scene(SAMPLE), Config(mean_decline_threshold=0.10))
    assert a.summary["decision"]["status"] == "no_significant_decline"


# ---- reproducibility -----------------------------------------------------------------
def test_same_inputs_give_same_run_id_and_result():
    s, c = load_scene(SAMPLE), Config()
    assert analyze(s, c).run_id == analyze(load_scene(SAMPLE), c).run_id
    assert analyze(s, c).summary == analyze(load_scene(SAMPLE), c).summary


def test_run_id_changes_with_config_or_data():
    s = load_scene(SAMPLE)
    base = fingerprint(s, Config())
    assert fingerprint(s, Config(mean_decline_threshold=0.2)) != base
    s.nir_2 = s.nir_2.copy(); s.nir_2[0, 0] += 0.01
    assert fingerprint(s, Config()) != base
