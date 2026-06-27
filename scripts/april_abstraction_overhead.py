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
        default=Path("figures/"),
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

    groups = [
        (
            "AoS scalar",
            [
                "APRIL AoS scalar",
                "Handwritten AoS scalar",
            ],
        ),
        (
            "SoA scalar",
            [
                "APRIL SoA scalar",
                "Handwritten SoA scalar",
            ],
        ),
        (
            "SIMD",
            [
                "APRIL SoA SIMD",
                "APRIL AoSoA SIMD",
                "Handwritten SoA 2D SIMD",
            ],
        ),
    ]

    display_labels = {
        "APRIL AoS scalar": "APRIL",
        "Handwritten AoS scalar": "Handwritten",
        "APRIL SoA scalar": "APRIL",
        "Handwritten SoA scalar": "Handwritten",
        "APRIL SoA SIMD": "APRIL\nSoA",
        "APRIL AoSoA SIMD": "APRIL\nAoSoA",
        "Handwritten SoA 2D SIMD": "Handwritten\nSoA",
    }

    wanted_labels = [label for _, labels in groups for label in labels]
    df = df[df["label"].isin(wanted_labels)].copy()

    if df.empty:
        raise SystemExit("No matching handcoded benchmark rows found.")

    values_by_label = {
        str(row["label"]): float(row["real_time"])
        for _, row in df.iterrows()
    }

    x_positions: list[float] = []
    x_labels: list[str] = []
    y_values: list[float] = []
    group_centers: list[float] = []
    group_labels: list[str] = []

    x = 0.0
    inner_gap = 1.0
    group_gap = 0.9

    for group_name, labels in groups:
        group_start = x

        for label in labels:
            if label not in values_by_label:
                continue

            x_positions.append(x)
            x_labels.append(display_labels[label])
            y_values.append(values_by_label[label])
            x += inner_gap

        group_end = x - inner_gap
        if group_end >= group_start:
            group_centers.append((group_start + group_end) / 2.0)
            group_labels.append(group_name)

        x += group_gap

    plt.figure(figsize=(8.8, 4.8))
    ax = plt.gca()

    bars = ax.bar(x_positions, y_values, width=0.72)

    ax.set_ylabel("Total time [ms]", fontsize=12)
    ax.set_title("APRIL direct-sum benchmark vs handwritten kernels", fontsize=13)
    ax.grid(axis="y", alpha=0.3)

    ax.set_xticks(x_positions)
    ax.set_xticklabels(x_labels, fontsize=10)

    # Group labels below the x tick labels.
    for center, group_name in zip(group_centers, group_labels):
        ax.text(
            center,
            -0.16,
            group_name,
            ha="center",
            va="top",
            transform=ax.get_xaxis_transform(),
            fontsize=11,
        )

    # Subtle separators between groups.
    for i in range(len(group_centers) - 1):
        boundary = (group_centers[i] + group_centers[i + 1]) / 2.0
        ax.axvline(boundary, color="black", linewidth=0.6, alpha=0.15)

    # Annotate bars with rounded times.
    for bar, value in zip(bars, y_values):
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height(),
            f"{value:.0f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    # Leave room for group labels below the axis.
    plt.subplots_adjust(bottom=0.24)

    savefig(out_dir, "april_handcoded_total_time")

    print(f"Wrote {out_dir / 'april_handcoded_total_time.pdf'}")
    print(f"Wrote {out_dir / 'april_handcoded_total_time.png'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())