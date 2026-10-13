"""Generate the synthetic 12x12 scene used for the demo and the tests.

ORIGIN: fully synthetic and deterministic (no random numbers, no real imagery).
Values are chosen so every expected result can be derived by hand
(see sample_data/README.md).

Run:  python sample_data/generate_sample_data.py
"""
from pathlib import Path

import numpy as np

N = 12
OUT = Path(__file__).with_name("farm_scene.npz")


def build() -> dict:
    farm = np.zeros((N, N), dtype=bool)
    farm[1:11, 1:11] = True                      # 10x10 = 100 farm pixels

    # Date 1: healthy crop on the farm (NDVI 0.8); outside the farm NDVI 0.8 too
    red_1 = np.full((N, N), 0.1)
    nir_1 = np.full((N, N), 0.9)
    valid_1 = np.ones((N, N), dtype=bool)
    valid_1[1:3, 1:3] = False                    # cloud: 4 farm pixels
    red_1[3, 3] = 0.0                            # zero denominator (red = nir = 0)
    nir_1[3, 3] = 0.0                            # ...flagged valid by the mask, must still be excluded

    # Date 2: same, except a declined patch (NDVI 0.5) in the south-east of the farm
    red_2 = np.full((N, N), 0.1)
    nir_2 = np.full((N, N), 0.9)
    red_2[6:11, 6:11], nir_2[6:11, 6:11] = 0.2, 0.6   # 25 declined pixels, NDVI 0.5
    valid_2 = np.ones((N, N), dtype=bool)
    valid_2[1:4, 8:10] = False                   # a DIFFERENT cloud: 6 farm pixels

    # Outside the farm, date 2 collapses to NDVI 0 - must NOT influence any result
    outside = ~farm
    red_2[outside], nir_2[outside] = 0.3, 0.3

    return dict(
        red_1=red_1, nir_1=nir_1, valid_1=valid_1,
        red_2=red_2, nir_2=nir_2, valid_2=valid_2, farm=farm,
        label_1=np.array("2026-06-01"), label_2=np.array("2026-07-15"),
        origin=np.array("synthetic, deterministic 12x12 test scene (not real imagery)"),
    )


if __name__ == "__main__":
    np.savez_compressed(OUT, **build())
    print(f"wrote {OUT}")
