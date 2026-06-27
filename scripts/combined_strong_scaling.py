#!/usr/bin/env python3
"""
Plot APRIL vs LAMMPS strong scaling throughput in one IEEE-friendly figure.

Inputs:
  april_strong_scaling.csv
  lammps_strong_scaling.csv

Output:
  figures/strong_scaling/strong_scaling_mups_dt_<dt-list>.pdf
  figures/strong_scaling/strong_scaling_mups_dt_<dt-list>.png

Default comparison:
  APRIL:
    config   = native
    executor = OmpExecutor
    n        = 100
    layout   = SoA
    schedule = C08
    ordering = hilbert
    block    = 2x2x2

  LAMMPS:
    config = openmp-native
    mode   = threads
    n      = 100

The figure contains:
  - throughput in MUPS only
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


LABEL_SIZE = 9
TICK_SIZE = 8
TITLE_SIZE = 9
LEGEND_SIZE = 7


def parse_dt_list(value: str) -> list[float]:
    return [float(x.strip()) for x in value.split(",") if x.strip()]


def dt_label(dt: float) -> str:
    if dt == 0:
        return "0"
    if abs(dt) < 1e-3:
        return f"{dt:.0e}"
    return f"{dt:g}"


def safe_dt_label(dt: float) -> str:
    return dt_label(dt).replace("+", "").replace("-", "m").replace(".", "p")


def close_dt_mask(series: pd.Series, target: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return np.isclose(values, target, rtol=1e-6, atol=1e-15)


def load_april(
    path: Path,
    *,
    config: str,
    executor: str,
    n: int,
    layout: str,
    schedule: str,
    ordering: str,
    block: str,
) -> pd.DataFrame:
    df = pd.read_csv(path)

    numeric_cols = [
        "dt",
        "n",
        "threads",
        "total_cores",
        "performance_mups",
        "bx",
        "by",
        "bz",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    bx, by, bz = [int(x) for x in block.split("x")]

    mask = (
        (df["engine"] == "april")
        & (df["config"] == config)
        & (df["scaling"] == "strong")
        & (df["n"] == n)
        & (df["layout"] == layout)
        & (df["executor"] == executor)
        & (df["schedule"] == schedule)
        & (df["ordering"] == ordering)
        & (df["bx"] == bx)
        & (df["by"] == by)
        & (df["bz"] == bz)
    )

    out = df.loc[mask].copy()
    out["label"] = "APRIL"
    out["cores"] = out["total_cores"].astype(int)
    out["mups"] = out["performance_mups"].astype(float)

    return out


def load_lammps(
    path: Path,
    *,
    config: str,
    mode: str,
    n: int,
) -> pd.DataFrame:
    df = pd.read_csv(path)

    numeric_cols = [
        "dt",
        "n",
        "threads",
        "total_cores",
        "performance_mups",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    mask = (
        (df["engine"] == "lammps")
        & (df["config"] == config)
        & (df["scaling"] == "strong")
        & (df["n"] == n)
    )

    if "mode" in df.columns:
        mask &= df["mode"] == mode

    out = df.loc[mask].copy()
    out["label"] = "LAMMPS"
    out["cores"] = out["total_cores"].astype(int)
    out["mups"] = out["performance_mups"].astype(float)

    return out


def aggregate_for_dt(df: pd.DataFrame, target_dt: float) -> pd.DataFrame:
    sub = df.loc[close_dt_mask(df["dt"], target_dt)].copy()

    if sub.empty:
        return sub

    grouped = (
        sub.groupby(["label", "cores"], as_index=False)
        .agg(
            mups_mean=("mups", "mean"),
            mups_min=("mups", "min"),
            mups_max=("mups", "max"),
            mups_std=("mups", "std"),
            runs=("mups", "size"),
        )
        .sort_values(["label", "cores"])
    )

    return grouped


def plot_mups_combined(df: pd.DataFrame, dts: list[float], out_dir: Path) -> None:
    frames = []

    for dt in dts:
        agg = aggregate_for_dt(df, dt)

        if agg.empty:
            print(f"Skipping dt={dt:g}: no matching rows")
            continue

        agg["dt"] = dt
        frames.append(agg)

    if not frames:
        raise SystemExit("No matching rows for any requested dt values.")

    agg_all = pd.concat(frames, ignore_index=True)

    out_dir.mkdir(parents=True, exist_ok=True)

    # IEEE single-column friendly size.
    fig, ax = plt.subplots(
        figsize=(3.45, 2.45),
        constrained_layout=True,
    )

    markers = {
        "APRIL": "o",
        "LAMMPS": "s",
    }

    linestyles = ["-", "--", "-.", ":"]
    dt_style = {
        dt: linestyles[i % len(linestyles)]
        for i, dt in enumerate(dts)
    }

    labels = list(agg_all["label"].drop_duplicates())

    for dt in dts:
        for label in labels:
            g = agg_all.loc[
                (agg_all["dt"] == dt) & (agg_all["label"] == label)
            ].sort_values("cores")

            if g.empty:
                continue

            x = g["cores"].to_numpy()
            y = g["mups_mean"].to_numpy()

            legend_label = f"{label}, $\\Delta t={dt_label(dt)}$"

            ax.plot(
                x,
                y,
                marker=markers.get(label, "o"),
                markersize=3.5,
                linewidth=1.1,
                linestyle=dt_style[dt],
                label=legend_label,
            )

            if (g["runs"] > 1).any():
                ax.fill_between(
                    x,
                    g["mups_min"].to_numpy(),
                    g["mups_max"].to_numpy(),
                    alpha=0.12,
                    linewidth=0,
                )

    ax.set_xlabel("Threads", fontsize=LABEL_SIZE)
    ax.set_ylabel("Performance [MUPS]", fontsize=LABEL_SIZE)
    ax.tick_params(axis="both", labelsize=TICK_SIZE)
    ax.grid(True, linewidth=0.35, alpha=0.5)

    ax.legend(
        fontsize=LEGEND_SIZE,
        frameon=True,
        loc="best",
        handlelength=2.0,
    )

    stem = "strong_scaling_mups_dt_" + "_".join(
        safe_dt_label(dt) for dt in dts
    )

    pdf_path = out_dir / f"{stem}.pdf"
    png_path = out_dir / f"{stem}.png"

    fig.savefig(pdf_path)
    fig.savefig(png_path, dpi=300)
    plt.close(fig)

    print(f"Wrote {pdf_path}")
    print(f"Wrote {png_path}")

    summary = agg_all.pivot_table(
        index=["dt", "cores"],
        columns="label",
        values="mups_mean",
        aggfunc="first",
    )

    print()
    print("Combined throughput summary")
    print(summary.to_string(float_format=lambda x: f"{x:.3f}"))
    print()


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--april-csv",
        type=Path,
        default=Path("./analysis/thesis/april_strong_scaling.csv"),
    )
    parser.add_argument(
        "--lammps-csv",
        type=Path,
        default=Path("./analysis/thesis/lammps_strong_scaling.csv"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("figures/strong_scaling"),
    )

    parser.add_argument(
        "--dts",
        default="0.005,1e-7",
        help="Comma-separated timestep values to include in the combined plot.",
    )

    parser.add_argument("--n", type=int, default=100)

    parser.add_argument("--april-config", default="native")
    parser.add_argument("--april-executor", default="OmpExecutor")
    parser.add_argument("--april-layout", default="SoA")
    parser.add_argument("--april-schedule", default="C08")
    parser.add_argument("--april-ordering", default="hilbert")
    parser.add_argument("--april-block", default="2x2x2")

    parser.add_argument("--lammps-config", default="openmp-native")
    parser.add_argument("--lammps-mode", default="threads")

    args = parser.parse_args()

    if not args.april_csv.exists():
        raise SystemExit(f"Missing APRIL CSV: {args.april_csv}")

    if not args.lammps_csv.exists():
        raise SystemExit(f"Missing LAMMPS CSV: {args.lammps_csv}")

    april = load_april(
        args.april_csv,
        config=args.april_config,
        executor=args.april_executor,
        n=args.n,
        layout=args.april_layout,
        schedule=args.april_schedule,
        ordering=args.april_ordering,
        block=args.april_block,
    )

    lammps = load_lammps(
        args.lammps_csv,
        config=args.lammps_config,
        mode=args.lammps_mode,
        n=args.n,
    )

    if april.empty:
        raise SystemExit("No matching APRIL rows after filtering.")

    if lammps.empty:
        raise SystemExit("No matching LAMMPS rows after filtering.")

    combined = pd.concat([april, lammps], ignore_index=True)

    dts = parse_dt_list(args.dts)
    plot_mups_combined(combined, dts, args.out_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())