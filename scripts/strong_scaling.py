#!/usr/bin/env python3
"""
Plot APRIL vs LAMMPS strong scaling.

Inputs:
  april_strong_scaling.csv
  lammps_strong_scaling.csv

Outputs:
  figures/strong_scaling/strong_scaling_dt_<dt>.pdf
  figures/strong_scaling/strong_scaling_dt_<dt>.png

Default comparison:
  APRIL:
    config   = native
    executor = OmpExecutor
    n        = 100

  LAMMPS:
    config = openmp-native
    mode   = threads
    n      = 100

Each figure contains:
  - throughput in MUPS
  - speedup relative to the 1-thread mean
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


LABEL_SIZE = 13
TICK_SIZE = 11
TITLE_SIZE = 13
LEGEND_SIZE = 11


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

    for col in ["dt", "n", "threads", "total_cores", "performance_mups"]:
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

    for col in ["dt", "n", "threads", "total_cores", "performance_mups"]:
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

    speedups = []
    for label, group in grouped.groupby("label"):
        base_rows = group.loc[group["cores"] == 1]
        base = np.nan if base_rows.empty else float(base_rows["mups_mean"].iloc[0])

        g = group.copy()
        g["speedup"] = g["mups_mean"] / base
        g["speedup_min"] = g["mups_min"] / base
        g["speedup_max"] = g["mups_max"] / base
        speedups.append(g)

    return pd.concat(speedups, ignore_index=True)


def plot_dt(df: pd.DataFrame, target_dt: float, out_dir: Path) -> None:
    agg = aggregate_for_dt(df, target_dt)

    if agg.empty:
        print(f"Skipping dt={target_dt:g}: no matching rows")
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.2), constrained_layout=True)

    ax_perf, ax_speedup = axes
    labels = list(agg["label"].drop_duplicates())

    for label in labels:
        g = agg.loc[agg["label"] == label].sort_values("cores")

        x = g["cores"].to_numpy()
        y = g["mups_mean"].to_numpy()
        ymin = g["mups_min"].to_numpy()
        ymax = g["mups_max"].to_numpy()

        ax_perf.plot(x, y, marker="o", label=label)

        if (g["runs"] > 1).any():
            ax_perf.fill_between(x, ymin, ymax, alpha=0.15)

        ys = g["speedup"].to_numpy()
        ys_min = g["speedup_min"].to_numpy()
        ys_max = g["speedup_max"].to_numpy()

        ax_speedup.plot(x, ys, marker="o", label=label)

        if (g["runs"] > 1).any():
            ax_speedup.fill_between(x, ys_min, ys_max, alpha=0.15)

    max_core = int(agg["cores"].max())
    ideal_x = np.array(sorted(agg["cores"].unique()))
    ax_speedup.plot(ideal_x, ideal_x, linestyle="--", linewidth=1.0, label="ideal")

    ax_perf.set_title(f"Throughput, $\\Delta t = {dt_label(target_dt)}$", fontsize=TITLE_SIZE)
    ax_perf.set_xlabel("Threads", fontsize=LABEL_SIZE)
    ax_perf.set_ylabel("Performance [MUPS]", fontsize=LABEL_SIZE)
    ax_perf.tick_params(axis="both", labelsize=TICK_SIZE)
    ax_perf.grid(True, linewidth=0.4, alpha=0.5)
    ax_perf.legend(fontsize=LEGEND_SIZE)

    ax_speedup.set_title(f"Strong scaling, $\\Delta t = {dt_label(target_dt)}$", fontsize=TITLE_SIZE)
    ax_speedup.set_xlabel("Threads", fontsize=LABEL_SIZE)
    ax_speedup.set_ylabel("Speedup", fontsize=LABEL_SIZE)
    ax_speedup.tick_params(axis="both", labelsize=TICK_SIZE)
    ax_speedup.set_xlim(left=1, right=max_core)
    ax_speedup.set_ylim(bottom=0)
    ax_speedup.grid(True, linewidth=0.4, alpha=0.5)
    ax_speedup.legend(fontsize=LEGEND_SIZE)

    stem = f"strong_scaling_dt_{safe_dt_label(target_dt)}"
    pdf_path = out_dir / f"{stem}.pdf"
    png_path = out_dir / f"{stem}.png"

    fig.savefig(pdf_path)
    fig.savefig(png_path, dpi=300)
    plt.close(fig)

    print(f"Wrote {pdf_path}")
    print(f"Wrote {png_path}")

    summary = agg.pivot_table(
        index="cores",
        columns="label",
        values="mups_mean",
        aggfunc="first",
    )
    print()
    print(f"dt = {target_dt:g}")
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
        help="Comma-separated timestep values to plot.",
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

    for dt in parse_dt_list(args.dts):
        plot_dt(combined, dt, args.out_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())