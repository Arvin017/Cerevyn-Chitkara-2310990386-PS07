"""Write downloadable results: JSON summary, per-pixel CSV and a heatmap PNG."""
from __future__ import annotations

import csv
import json
import platform
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import __version__  # noqa: E402
from .core import REASON_NAMES, Analysis  # noqa: E402

FILES = {"results": "results.json", "pixels": "pixels.csv", "heatmap": "heatmap.png"}


def _nan_to_blank(x: float) -> str:
    return "" if np.isnan(x) else f"{x:.6f}"


def write_json(analysis: Analysis, path: Path) -> None:
    payload = dict(analysis.summary)
    payload["provenance"] = {
        "run_id": analysis.run_id,
        "tool_version": __version__,
        "python": platform.python_version(),
        "numpy": np.__version__,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_csv(analysis: Analysis, path: Path) -> None:
    a = analysis
    rows, cols = a.farm.shape
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["row", "col", "in_farm", "ndvi_1", "reason_1", "ndvi_2", "reason_2",
                    "used_in_comparison", "change"])
        for r in range(rows):
            for c in range(cols):
                w.writerow([
                    r, c, int(a.farm[r, c]),
                    _nan_to_blank(a.date_1.ndvi[r, c]), REASON_NAMES[int(a.date_1.reason[r, c])],
                    _nan_to_blank(a.date_2.ndvi[r, c]), REASON_NAMES[int(a.date_2.reason[r, c])],
                    int(a.common[r, c]), _nan_to_blank(a.change[r, c]),
                ])


def write_heatmap(analysis: Analysis, path: Path) -> None:
    from matplotlib.colors import ListedColormap

    a = analysis
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.8), constrained_layout=True)
    gray = plt.get_cmap("gray")
    div = plt.get_cmap("RdBu").copy()
    # overlay categories: 1 = outside farm (slate), 2 = farm pixel excluded (red)
    overlay_cmap = ListedColormap(["#4a5a78", "#d9534f"])

    def overlay(excluded):
        cat = np.full(a.farm.shape, np.nan)
        cat[~a.farm] = 0
        cat[excluded] = 1
        return np.ma.masked_invalid(cat)

    for ax, res in zip(axes[:2], (a.date_1, a.date_2)):
        im = ax.imshow(np.ma.masked_invalid(res.ndvi), cmap=gray, vmin=-1, vmax=1)
        ax.imshow(overlay(a.farm & ~res.usable), cmap=overlay_cmap, vmin=0, vmax=1)
        ax.set_title(f"NDVI - {res.label}\nusable {res.stats['usable_pct_of_farm']}% of farm", fontsize=10)
        fig.colorbar(im, ax=ax, shrink=0.8)

    lim = max(0.1, float(np.nanmax(np.abs(a.change)))) if a.common.any() else 1.0
    im = axes[2].imshow(np.ma.masked_invalid(a.change), cmap=div, vmin=-lim, vmax=lim)
    axes[2].imshow(overlay(a.farm & ~a.common), cmap=ListedColormap(["#4a5a78", "#9a9a9a"]), vmin=0, vmax=1)
    axes[2].set_title(f"Change ({a.date_2.label} - {a.date_1.label})\ncommon usable farm pixels only", fontsize=10)
    fig.colorbar(im, ax=axes[2], shrink=0.8)
    for ax in axes:
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("Slate = outside farm. Red = farm pixel excluded (cloud / invalid / zero denominator). "
                 "Grey (right) = farm pixel not usable on both dates, so not compared.", fontsize=8.5)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def write_outputs(analysis: Analysis, out_dir) -> dict:
    out = Path(out_dir) / analysis.run_id
    out.mkdir(parents=True, exist_ok=True)
    write_json(analysis, out / FILES["results"])
    write_csv(analysis, out / FILES["pixels"])
    write_heatmap(analysis, out / FILES["heatmap"])
    return {k: out / v for k, v in FILES.items()}
