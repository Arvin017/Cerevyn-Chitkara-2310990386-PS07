# Cerevyn-Chitkara-2310990386-PS07: Satellite Vegetation Change Monitor

| | |
|---|---|
| **Problem ID** | PS07, Satellite Vegetation Change Monitor |
| **Candidate** | Arvin |
| **Roll number** | 2310990386 |
| **Branch** | Computer Science Engineering (Chitkara University), batch of 2027 |
| **Role applied** | Software Development Trainee |
| **Evaluated commit / tag** | `v1.0` |
| **CI run** | https://github.com/Arvin017/Cerevyn-Chitkara-2310990386-PS07/actions/runs/38450985147 |
| **Demo recording** | https://drive.google.com/file/d/1nXRcse7-RGKECmNVzyEJ_6w_pMQ8CEUf/view?usp=sharing |

## Problem

Compare vegetation indices for a farm area across two image dates. Calculate NDVI correctly, exclude invalid pixels,
compare only a consistent area, flag a decline with a documented configurable threshold, show a heatmap, export results,
and state clearly that an NDVI decline is not by itself evidence of disease, cause or yield loss.

## Approach

`NDVI = (NIR - Red) / (NIR + Red)`, computed per pixel (`src/ndvi_monitor/core.py`).

1. **Per-pixel checks.** A pixel gets an NDVI value only if it passes every check. Otherwise it is `NaN` with a reason code
   (`masked`, `non_finite`, `zero_denominator`, `out_of_range`). Nothing is zero-filled or interpolated.
2. **Per-date coverage.** For each date: farm pixels, usable pixels, usable % of farm, mean NDVI over its usable farm pixels,
   and a count of excluded pixels per reason.
3. **Same area on both dates.** The comparison uses only **farm pixels usable on both dates** (the intersection of the two
   validity masks). Date means, per-pixel change and percentages are all computed on that set, so a cloud on one date
   cannot bias the comparison.
4. **Decision rule (configurable).** `decline_flagged` if `mean_change <= -mean_decline_threshold` (default 0.05).
   Per-pixel declines use `pixel_decline_threshold` (default 0.10). If fewer than `min_usable_pct` (default 50 %) of the farm
   is usable on both dates, the status is `insufficient_data` and **no numbers are reported**.
5. **Outputs.** `results.json`, `pixels.csv` (per-pixel NDVI, reason codes, change) and `heatmap.png`.
   The run folder is named by a `run_id`, a SHA-256 of the input arrays plus the configuration, so a run is reproducible and verifiable.

The interpretation note is in every result and on the dashboard:
> A lower NDVI means less red/near-infrared contrast in the image. It does not by itself establish crop disease, stress, its cause,
> or yield loss. Harvest, irrigation, growth stage, shadows, haze, sensor differences and residual cloud can all change NDVI.

## Setup, run, test

Tested with Python 3.12 (CI is configured for 3.11 and 3.12). Pinned dependencies are in `requirements.txt`
(numpy 2.4.4, matplotlib 3.10.8, fastapi 0.143.0, uvicorn 0.54.0, python-multipart 0.0.32) and `requirements-dev.txt` (pytest 9.1.1, httpx 0.28.1).

```bash
git clone <this repo> && cd <this repo>
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python -m pytest                                          # 36 tests (pytest adds src/ to the path itself)

export PYTHONPATH=src                                     # Windows cmd: set PYTHONPATH=src   PowerShell: $env:PYTHONPATH="src"
python -m ndvi_monitor.cli --sample --out output          # CLI run on the bundled scene
uvicorn ndvi_monitor.api:app                              # dashboard at http://127.0.0.1:8000, API docs at /docs
```

Docker:

```bash
docker build -t ndvi-monitor .
docker run --rm -p 8000:8000 ndvi-monitor                 # http://127.0.0.1:8000
```

Configuration (all optional, see `.env.example`): `OUTPUT_DIR`, `MEAN_DECLINE_THRESHOLD`, `PIXEL_DECLINE_THRESHOLD`, `MIN_USABLE_PCT`.
The dashboard and the API (`?mean_decline_threshold=...`) can override the thresholds per run.

### API

| Method and path | Purpose |
|---|---|
| `GET /health` | liveness |
| `POST /api/analyze/sample` | analyse the bundled synthetic scene |
| `POST /api/analyze/upload` | analyse an uploaded `.npz` scene (multipart field `file`, max 5 MB) |
| `GET /api/runs/{run_id}/{results\|pixels\|heatmap}` | download JSON / CSV / PNG |

Errors are explicit: 422 for invalid thresholds or an invalid / misaligned scene, 413 for oversize uploads, 404 for unknown runs.

## Sample data

`sample_data/farm_scene.npz` is **synthetic** (12x12, deterministic, no real imagery). `sample_data/README.md` lists what each region
tests and derives `sample_data/expected_results.json` by hand; the tests compare program output with those hand-derived values.
Scene file format: seven same-shape 2-D arrays (`red_1 nir_1 valid_1 red_2 nir_2 valid_2 farm`), optional text `label_1 label_2 origin`.

### Example output (default thresholds)

```
2026-06-01    : usable 95/100 (95.0%), mean NDVI 0.8
2026-07-15    : usable 94/100 (94.0%), mean NDVI 0.720213
common pixels : 89 (89.0% of farm)
mean change   : -0.08427   declined pixels: 25
decision      : decline_flagged - Mean NDVI fell by 0.084 over 89 common farm pixels (threshold 0.05).
                25 pixels (28.1%) fell by at least 0.1.
```

Date 2's own mean (0.720) differs from the common-pixel mean (0.716) on purpose: the first uses all of that date's usable pixels,
the second only the pixels that are also usable on date 1.

### Try a bad input

```bash
python -c "import numpy as np; m=np.ones((10,10),bool); z=np.full((10,10),.5); np.savez('bad.npz',red_1=z,nir_1=z,valid_1=m,red_2=np.zeros((9,9)),nir_2=z,valid_2=m,farm=m)"
python -m ndvi_monitor.cli --input bad.npz       # error: ... arrays must all share one shape ...
```

## Tests (36 automated scenarios)

* **Formula and pixel handling** (`tests/test_core.py`): NIR 0.6 / Red 0.2 = 0.5; zero denominator is `NaN` with a reason, not 0;
  masked, non-finite and out-of-range pixels get no value; mask beats other reasons.
* **Consistent comparison area:** different cloud masks per date use the intersection (81 = 100 - 10 - 10 + 1); pixels outside the farm
  never affect results even when they change hugely; entirely masked area gives `insufficient_data` and `None` values; coverage gate.
* **Decision rule:** configurable thresholds, inclusive boundary, increases not flagged, invalid configuration rejected.
* **Sample scene vs hand-derived expectations,** reproducibility (`run_id`), scene validation (`tests/test_io.py`: missing arrays, misaligned
  shapes, non-boolean masks, pickled or garbage files, non-numeric bands).
* **API and outputs** (`tests/test_api_and_report.py`): endpoints, bad uploads, invalid thresholds, path-traversal ids, CSV contents
  (excluded pixels have no value), PNG output.

## Design decisions (and limitations)

* **Why intersect the masks?** Comparing date 1 over all its valid pixels with date 2 over a different set mixes spatial change with coverage change.
* **Why not fill bad pixels?** The brief forbids silently assigning a vegetation value; they are excluded and counted instead.
* **Why `out_of_range`?** With corrected reflectance, negative or inconsistent bands can push |NDVI| above 1, which is not a valid vegetation value.
* **Limitations:** synthetic data only; NDVI only (no EVI/SAVI); the scene must already be co-registered (no reprojection, resampling or georeferencing);
  validity masks are supplied, not derived from a cloud algorithm; no seasonal normalisation, so a lower NDVI may be normal phenology;
  at most 1 M pixels per scene; results are stored on local disk (Azure Blob in the plan); the API has no authentication.
* **Verification status:** the 36 tests pass locally and in GitHub Actions (Python 3.11 and 3.12), and the Docker image builds and passes its health check in CI (run linked above).
* **Azure:** `docs/azure-plan.md` is a design only; nothing is deployed.

## Repository layout

```
src/ndvi_monitor/   core.py (NDVI + comparison)  io.py (scene validation)  report.py (JSON/CSV/PNG)
                    api.py (FastAPI)  cli.py  config.py  static/index.html (dashboard)
sample_data/        farm_scene.npz  generate_sample_data.py  expected_results.json  README.md
tests/              test_core.py  test_io.py  test_api_and_report.py  conftest.py
docs/               azure-plan.md  demo-script.md
.github/workflows/  ci.yml        Dockerfile  requirements*.txt  .env.example
```

## Contributions and AI assistance

Individual submission. The design, code, tests and documentation were produced with AI assistance (Claude, by Anthropic) and then reviewed,
run and adapted by me. Third-party libraries: NumPy, Matplotlib, FastAPI, Uvicorn, python-multipart, pytest, httpx. No code was copied from other repositories.
I can explain every module and make changes during the follow-up discussion.