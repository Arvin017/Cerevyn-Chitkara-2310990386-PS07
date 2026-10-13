"""Command line entry point.

    python -m ndvi_monitor.cli --sample
    python -m ndvi_monitor.cli --input my_scene.npz --out output --mean-threshold 0.08
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config
from .core import analyze
from .io import SceneError, load_scene
from .report import write_outputs

DEFAULT_SAMPLE = Path(__file__).resolve().parents[2] / "sample_data" / "farm_scene.npz"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="NDVI vegetation change monitor")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--sample", action="store_true", help="use sample_data/farm_scene.npz")
    src.add_argument("--input", type=Path, help="path to a scene .npz file")
    p.add_argument("--out", type=Path, default=Path("output"))
    d = Config()
    p.add_argument("--mean-threshold", type=float, default=d.mean_decline_threshold)
    p.add_argument("--pixel-threshold", type=float, default=d.pixel_decline_threshold)
    p.add_argument("--min-usable-pct", type=float, default=d.min_usable_pct)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = Config(args.mean_threshold, args.pixel_threshold, args.min_usable_pct).validate()
        scene = load_scene(DEFAULT_SAMPLE if args.sample else args.input)
        analysis = analyze(scene, cfg)
    except (SceneError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    paths = write_outputs(analysis, args.out)
    s = analysis.summary
    print(f"run id        : {analysis.run_id}")
    print(f"scene origin  : {s['scene']['origin']}")
    for key in ("date_1", "date_2"):
        d = s[key]
        print(f"{d['label']:<14}: usable {d['usable_pixels']}/{s['scene']['farm_pixels']} "
              f"({d['usable_pct_of_farm']}%), mean NDVI {d['mean_ndvi_on_usable']}")
    c = s["comparison"]
    print(f"common pixels : {c['common_pixels']} ({c['common_pct_of_farm']}% of farm)")
    print(f"mean change   : {c['mean_change']}   declined pixels: {c['declined_pixels']}")
    print(f"decision      : {s['decision']['status']} - {s['decision']['message']}")
    print(f"note          : {s['interpretation_note']}")
    for name, p in paths.items():
        print(f"wrote {name:<8}: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
