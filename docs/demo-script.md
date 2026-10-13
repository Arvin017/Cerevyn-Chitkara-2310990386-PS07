# 3-5 minute demo script

Record the screen with voice-over (Win+G or OBS). Start the app first:
`uvicorn ndvi_monitor.api:app --app-dir src` and open http://127.0.0.1:8000.

1. **0:00** Show the repo tree and the README header (problem ID, name, roll number).
2. **0:20** Run `python -m pytest` and show the passing result.
3. **0:50** Dashboard, *Run on bundled sample*. Point out usable coverage per date (95 % / 94 %), the 89 common pixels,
   mean NDVI 0.8 to 0.716, mean change -0.084, `DECLINE FLAGGED`, and the interpretation note.
4. **1:40** Heatmap: slate = outside farm, red = cloud / zero-denominator pixels, grey in the change panel = not compared.
   Explain why the two cloud masks differ and why only the intersection is compared.
5. **2:20** Set *Mean decline threshold* to 0.10 and run again: `NO SIGNIFICANT DECLINE`. The run id changes because the
   configuration is part of it.
6. **2:50** Show `tests/test_core.py`: NIR 0.6 / Red 0.2 = 0.5, zero denominator, fully masked area (`insufficient_data`),
   different cloud masks between dates.
7. **3:30** Upload a mismatched-size `.npz` (README, "Try a bad input"): clear 422 error, nothing compared.
8. **4:00** Open `pixels.csv` and `results.json`, then `docs/azure-plan.md` and the green GitHub Actions run.
9. **4:30** State the limitations: synthetic data, NDVI only, no georeferencing or reprojection, Azure is a plan not a deployment.
