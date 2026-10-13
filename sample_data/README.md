# Sample data

`farm_scene.npz` is **synthetic** (12x12 pixels, deterministic, no random numbers, not real imagery).
Regenerate with `python sample_data/generate_sample_data.py`.

| Feature | Where | Purpose |
|---|---|---|
| Farm mask | rows 1-10, cols 1-10 (100 px) | pixels outside must never affect results |
| Healthy crop | red 0.1, nir 0.9 -> NDVI 0.8 | baseline on both dates |
| Cloud, date 1 | rows 1-2, cols 1-2 (4 px) | mask exclusion |
| Zero denominator, date 1 | pixel (3,3): red = nir = 0, marked valid | must be excluded, not assigned a value |
| Cloud, date 2 | rows 1-3, cols 8-9 (6 px) | *different* mask from date 1 |
| Declined patch, date 2 | rows 6-10, cols 6-10 (25 px): red 0.2, nir 0.6 -> NDVI 0.5 | change of -0.3 |
| Outside-farm trap, date 2 | all non-farm pixels red = nir = 0.3 (NDVI 0) | would be a huge drop if wrongly included |

## Hand derivation of `expected_results.json`

* Date 1 unusable on the farm: 4 cloud + 1 zero-denominator = 5, so usable 95.
* Date 2 unusable on the farm: 6 cloud, so usable 94.
* The unusable sets do not overlap, so common usable = 100 - 5 - 6 = **89** (89 %).
* Over the common pixels: 64 are unchanged (0.8 -> 0.8) and 25 changed by -0.3.
  Mean date 1 = 0.8; mean date 2 = (64 x 0.8 + 25 x 0.5) / 89 = 0.715730;
  mean change = 25 x (-0.3) / 89 = **-0.084270**; declined pixels (change <= -0.10) = 25 = 28.0899 %.
* Date 2's *own* mean (all 94 usable pixels, including 5 pixels that are cloudy on date 1)
  is (69 x 0.8 + 25 x 0.5) / 94 = 0.720213. This differs from the common-pixel mean on purpose.
* Default mean-decline threshold 0.05: |-0.0843| >= 0.05, so `decline_flagged`.
  With a threshold of 0.10 the same data is `no_significant_decline`.

## Scene file format (`.npz`, no pickles)

Required arrays, all 2-D with identical shape (aligned images): `red_1`, `nir_1`, `valid_1`, `red_2`,
`nir_2`, `valid_2`, `farm`. Bands are numeric reflectance. `valid_*` and `farm` are boolean (or 0/1);
`True` means usable / inside the farm. Optional text values: `label_1`, `label_2`, `origin`.
