"""Configuration for the comparison. All thresholds are documented and validated."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Config:
    # Flag a decline when the mean NDVI change over the common usable farm pixels
    # is at or below -mean_decline_threshold (NDVI units, 0..2).
    mean_decline_threshold: float = 0.05
    # A single pixel counts as "declined" when its change is at or below
    # -pixel_decline_threshold.
    pixel_decline_threshold: float = 0.10
    # If fewer than this percentage of farm pixels are usable on BOTH dates, no
    # comparison result is reported (status "insufficient_data").
    min_usable_pct: float = 50.0

    def validate(self) -> "Config":
        if not 0 < self.mean_decline_threshold <= 2:
            raise ValueError("mean_decline_threshold must be in (0, 2]")
        if not 0 < self.pixel_decline_threshold <= 2:
            raise ValueError("pixel_decline_threshold must be in (0, 2]")
        if not 0 <= self.min_usable_pct <= 100:
            raise ValueError("min_usable_pct must be in [0, 100]")
        return self

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            mean_decline_threshold=float(os.getenv("MEAN_DECLINE_THRESHOLD", 0.05)),
            pixel_decline_threshold=float(os.getenv("PIXEL_DECLINE_THRESHOLD", 0.10)),
            min_usable_pct=float(os.getenv("MIN_USABLE_PCT", 50)),
        ).validate()
