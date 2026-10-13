"""NDVI calculation and two-date comparison.

Design rules (see README "Design decisions"):
* NDVI = (NIR - Red) / (NIR + Red), computed only for pixels that pass every check.
* A pixel that fails a check gets NaN and a *reason code* - it is never given a
  vegetation value (no zero-filling, no interpolation).
* Date means, changes and percentages use only farm pixels usable on BOTH dates,
  so the two dates are always compared over the same area.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import numpy as np

from .config import Config

DENOM_EPS = 1e-12      # |NIR + Red| <= eps is treated as a zero denominator
RANGE_TOL = 1e-9       # NDVI must lie within [-1, 1] (+ tolerance)
DECISION_TOL = 1e-9    # float tolerance for threshold comparisons

OK, MASKED, NON_FINITE, ZERO_DENOM, OUT_OF_RANGE = 0, 1, 2, 3, 4
REASON_NAMES = {
    OK: "ok",
    MASKED: "masked",
    NON_FINITE: "non_finite",
    ZERO_DENOM: "zero_denominator",
    OUT_OF_RANGE: "out_of_range",
}

INTERPRETATION_NOTE = (
    "A lower NDVI means less red/near-infrared contrast in the image. It does not by "
    "itself establish crop disease, stress, its cause, or yield loss: harvest, "
    "irrigation, seasonal growth stage, shadows, haze, sensor differences and residual "
    "cloud can all change NDVI. Treat a flag as a prompt to inspect the field, not a diagnosis."
)


@dataclass
class Scene:
    """Two aligned observations of the same area plus a farm-area mask."""
    red_1: np.ndarray
    nir_1: np.ndarray
    valid_1: np.ndarray   # True = usable pixel (not cloud / bad data)
    red_2: np.ndarray
    nir_2: np.ndarray
    valid_2: np.ndarray
    farm: np.ndarray      # True = pixel belongs to the farm area
    label_1: str = "Date 1"
    label_2: str = "Date 2"
    origin: str = "unspecified"


@dataclass
class DateResult:
    label: str
    ndvi: np.ndarray
    reason: np.ndarray
    usable: np.ndarray    # farm & reason == OK
    stats: dict


@dataclass
class Analysis:
    summary: dict
    date_1: DateResult
    date_2: DateResult
    farm: np.ndarray
    common: np.ndarray    # farm pixels usable on both dates
    change: np.ndarray    # NDVI_2 - NDVI_1 on common pixels, NaN elsewhere
    run_id: str = ""
    extra: dict = field(default_factory=dict)


def compute_ndvi(red, nir, valid_mask=None, eps: float = DENOM_EPS):
    """Return (ndvi, reason). ndvi is NaN wherever reason != OK."""
    red = np.asarray(red, dtype=float)
    nir = np.asarray(nir, dtype=float)
    if red.shape != nir.shape:
        raise ValueError(f"red and nir shapes differ: {red.shape} vs {nir.shape}")
    if valid_mask is None:
        valid = np.ones(red.shape, dtype=bool)
    else:
        valid = np.asarray(valid_mask, dtype=bool)
        if valid.shape != red.shape:
            raise ValueError(f"valid mask shape {valid.shape} != band shape {red.shape}")

    finite = np.isfinite(red) & np.isfinite(nir)
    with np.errstate(invalid="ignore", over="ignore"):
        denom = nir + red
    reason = np.zeros(red.shape, dtype=np.int8)
    # Priority when several apply: masked > non_finite > zero_denominator > out_of_range
    reason[valid & finite & (np.abs(denom) <= eps)] = ZERO_DENOM
    reason[valid & ~finite] = NON_FINITE
    reason[~valid] = MASKED

    ndvi = np.full(red.shape, np.nan)
    ok = reason == OK
    ndvi[ok] = (nir[ok] - red[ok]) / denom[ok]

    bad_range = ok & (np.abs(ndvi) > 1 + RANGE_TOL)
    reason[bad_range] = OUT_OF_RANGE
    ndvi[bad_range] = np.nan
    return ndvi, reason


def _round(x, nd=6):
    return None if x is None else round(float(x), nd)


def analyze_date(label, red, nir, valid, farm) -> DateResult:
    ndvi, reason = compute_ndvi(red, nir, valid)
    farm = np.asarray(farm, dtype=bool)
    usable = farm & (reason == OK)
    farm_n = int(farm.sum())
    usable_n = int(usable.sum())
    excluded = {
        REASON_NAMES[c]: int((farm & (reason == c)).sum())
        for c in (MASKED, NON_FINITE, ZERO_DENOM, OUT_OF_RANGE)
    }
    stats = {
        "label": label,
        "usable_pixels": usable_n,
        "usable_pct_of_farm": _round(100.0 * usable_n / farm_n) if farm_n else None,
        "mean_ndvi_on_usable": _round(ndvi[usable].mean()) if usable_n else None,
        "excluded_farm_pixels": excluded,
    }
    return DateResult(label, ndvi, reason, usable, stats)


def fingerprint(scene: Scene, config: Config) -> str:
    """Deterministic id of (inputs + configuration) so a run can be reproduced/verified."""
    h = hashlib.sha256()
    for name in ("red_1", "nir_1", "valid_1", "red_2", "nir_2", "valid_2", "farm"):
        arr = np.ascontiguousarray(getattr(scene, name))
        h.update(name.encode())
        h.update(str(arr.shape).encode())
        h.update(str(arr.dtype).encode())
        h.update(arr.tobytes())
    h.update(json.dumps(config.as_dict(), sort_keys=True).encode())
    return h.hexdigest()[:12]


def analyze(scene: Scene, config: Config | None = None) -> Analysis:
    config = (config or Config()).validate()
    shapes = {np.shape(getattr(scene, n)) for n in
              ("red_1", "nir_1", "valid_1", "red_2", "nir_2", "valid_2", "farm")}
    if len(shapes) != 1:
        raise ValueError(f"all arrays must share one shape, got {sorted(shapes)}")
    farm = np.asarray(scene.farm, dtype=bool)
    farm_n = int(farm.sum())
    if farm_n == 0:
        raise ValueError("farm mask contains no pixels")

    d1 = analyze_date(scene.label_1, scene.red_1, scene.nir_1, scene.valid_1, farm)
    d2 = analyze_date(scene.label_2, scene.red_2, scene.nir_2, scene.valid_2, farm)

    common = d1.usable & d2.usable
    n = int(common.sum())
    common_pct = 100.0 * n / farm_n
    change = np.full(farm.shape, np.nan)
    change[common] = d2.ndvi[common] - d1.ndvi[common]

    comparison = {
        "common_pixels": n,
        "common_pct_of_farm": _round(common_pct),
        "mean_ndvi_date_1": None, "mean_ndvi_date_2": None, "mean_change": None,
        "declined_pixels": None, "declined_pct_of_common": None,
        "improved_pixels": None, "unchanged_pixels": None,
        "min_change": None, "max_change": None,
    }

    if n == 0 or common_pct < config.min_usable_pct:
        status = "insufficient_data"
        message = (
            f"Only {n} of {farm_n} farm pixels ({common_pct:.1f}%) are usable on both dates; "
            f"at least {config.min_usable_pct:g}% are required. No comparison is reported."
        )
    else:
        c = change[common]
        mean_change = float(c.mean())
        thr = config.pixel_decline_threshold - DECISION_TOL
        declined = int((c <= -thr).sum())
        improved = int((c >= thr).sum())
        comparison.update({
            "mean_ndvi_date_1": _round(d1.ndvi[common].mean()),
            "mean_ndvi_date_2": _round(d2.ndvi[common].mean()),
            "mean_change": _round(mean_change),
            "declined_pixels": declined,
            "declined_pct_of_common": _round(100.0 * declined / n),
            "improved_pixels": improved,
            "unchanged_pixels": n - declined - improved,
            "min_change": _round(c.min()),
            "max_change": _round(c.max()),
        })
        if mean_change <= -(config.mean_decline_threshold - DECISION_TOL):
            status = "decline_flagged"
            message = (
                f"Mean NDVI fell by {abs(mean_change):.3f} over {n} common farm pixels "
                f"(threshold {config.mean_decline_threshold:g}). {declined} pixels "
                f"({100.0 * declined / n:.1f}%) fell by at least {config.pixel_decline_threshold:g}."
            )
        else:
            status = "no_significant_decline"
            message = (
                f"Mean NDVI change is {mean_change:+.3f} over {n} common farm pixels, "
                f"which does not reach the decline threshold of {config.mean_decline_threshold:g}."
            )

    summary = {
        "schema_version": 1,
        "scene": {
            "origin": scene.origin,
            "shape": list(farm.shape),
            "farm_pixels": farm_n,
        },
        "config": config.as_dict(),
        "date_1": d1.stats,
        "date_2": d2.stats,
        "comparison": comparison,
        "decision": {
            "status": status,
            "message": message,
            "rule": "decline_flagged if mean_change <= -mean_decline_threshold, evaluated "
                    "only when common usable farm pixels >= min_usable_pct of the farm",
        },
        "interpretation_note": INTERPRETATION_NOTE,
    }
    run_id = fingerprint(scene, config)
    return Analysis(summary, d1, d2, farm, common, change, run_id)
