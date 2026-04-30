#!/usr/bin/env python3
"""
Plot APRIL handcoded benchmark using total wall-clock time.

Input:
  analysis/thesis/april_abstraction_overhead.csv

Output:
  analysis/plots/april_handcoded_total_time.pdf
  analysis/plots/april_handcoded_total_time.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"Missing input CSV: {path}")
    return pd.read_csv(path)


def savefig(out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_dir / f"{name}.pdf")
    plt.savefig(out_dir / f"{name}.png", dpi=220)
    plt.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("analysis/thesis/april_abstraction_overhead.csv"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("analysis/plots"),
    )
    args = parser.parse_args()

    root = args.project_root.resolve()
    input_path = args.input if args.input.is_absolute() else root / args.input
    out_dir = args.out_dir if args.out_dir.is_absolute() else root / args.out_dir

    df = read_csv(input_path)

    # Keep only actual benchmark rows, not ratio summary rows.
    df = df[df["group"] != "Ratio"].copy()

    # Use total Google Benchmark wall-clock time.
    df["real_time"] = pd.to_numeric(df["real_time"], errors="coerce")

    order = [
        "APRIL AoS scalar",
        "Handwritten AoS scalar",
        "APRIL SoA scalar",
        "Handwritten SoA scalar",
        "APRIL SoA SIMD",
        "APRIL AoSoA SIMD",
        "Handwritten SoA 2D SIMD",
    ]

    df = df[df["label"].isin(order)].copy()
    df["label"] = pd.Categorical(df["label"], categories=order, ordered=True)
    df = df.sort_values("label")

    if df.empty:
        raise SystemExit("No matching handcoded benchmark rows found.")

    display_labels = {
        "APRIL AoS scalar": "APRIL\nAoS scalar",
        "Handwritten AoS scalar": "Handwritten\nAoS scalar",
        "APRIL SoA scalar": "APRIL\nSoA scalar",
        "Handwritten SoA scalar": "Handwritten\nSoA scalar",
        "APRIL SoA SIMD": "APRIL\nSoA SIMD",
        "APRIL AoSoA SIMD": "APRIL\nAoSoA SIMD",
        "Handwritten SoA 2D SIMD": "Handwritten\nSoA SIMD",
    }

    x_labels = [display_labels[str(label)] for label in df["label"]]

    plt.figure(figsize=(8.8, 4.6))
    bars = plt.bar(x_labels, df["real_time"])

    plt.ylabel("Total time [ms]")
    plt.title("APRIL direct-sum benchmark vs handwritten kernels")
    plt.grid(axis="y", alpha=0.3)

    # Annotate bars with rounded times.
    for bar, value in zip(bars, df["real_time"]):
        plt.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height(),
            f"{value:.0f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    savefig(out_dir, "april_handcoded_total_time")

    print(f"Wrote {out_dir / 'april_handcoded_total_time.pdf'}")
    print(f"Wrote {out_dir / 'april_handcoded_total_time.png'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())