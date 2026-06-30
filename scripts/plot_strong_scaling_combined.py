#!/usr/bin/env python3
"""
Plot APRIL vs LAMMPS strong-scaling throughput in one IEEE-friendly figure.

Inputs produced by the extraction scripts:

  ./analysis/april_argon_block_summary.csv
  ./analysis/lammps_argon_block_summary.csv

Outputs:

  ./figures/strong_scaling/strong_scaling_mups_dt_<dt-list>.pdf
  ./figures/strong_scaling/strong_scaling_mups_dt_<dt-list>.png
  ./figures/strong_scaling/strong_scaling_mups_dt_<dt-list>_summary.csv

Default comparison:

  APRIL:
    config      = native
    executor    = OmpExecutor
    n_dim       = 100
    layout      = SoA
    cell_config = C08
    ordering    = hilbert
    block       = 2x2x2

  LAMMPS:
    config = openmp-native
    n_dim  = 100
    ranks  = 1
    bind   = close

Paper metric:
  - APRIL:  performance_mups_mean
  - LAMMPS: matom_step_per_second_mean

Both are plotted as MUPS / Matom-step/s.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


LABEL_SIZE = 9
TICK_SIZE = 8
LEGEND_SIZE = 7


def parse_dt_list(value: str) -> list[float]:
    return [float(x.strip()) for x in value.split(",") if x.strip()]


def dt_label(dt: float) -> str:
    if dt == 0:
        return "0"

    if abs(dt) < 1e-3:
        exponent = int(np.floor(np.log10(abs(dt))))
        mantissa = dt / (10 ** exponent)

        if np.isclose(mantissa, 1.0):
            return rf"10^{{{exponent}}}"

        return rf"{mantissa:g}\times 10^{{{exponent}}}"

    return f"{dt:g}"


def safe_dt_label(dt: float) -> str:
    return dt_label(dt).replace("+", "").replace("-", "m").replace(".", "p")


def close_dt_mask(series: pd.Series, target: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return np.isclose(values, target, rtol=1e-6, atol=1e-15)


def require_columns(df: pd.DataFrame, path: Path, columns: list[str]) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise SystemExit(
            f"{path} is missing required columns: {', '.join(missing)}"
        )


def load_april(
    path: Path,
    *,
    config: str,
    executor: str,
    n_dim: int,
    layout: str,
    cell_config: str,
    ordering: str,
    block: str,
) -> pd.DataFrame:
    df = pd.read_csv(path)

    require_columns(
        df,
        path,
        [
            "engine",
            "config",
            "benchmark",
            "scaling",
            "n_dim",
            "dt",
            "threads",
            "block_x",
            "block_y",
            "block_z",
            "cell_config",
            "layout",
            "executor",
            "ordering",
            "performance_mups_mean",
        ],
    )

    numeric_cols = [
        "n_dim",
        "dt",
        "threads",
        "block_x",
        "block_y",
        "block_z",
        "performance_mups_mean",
        "performance_mups_min",
        "performance_mups_max",
        "performance_mups_stddev",
        "n_reps",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    block_x, block_y, block_z = [int(x) for x in block.split("x")]

    mask = (
        (df["engine"] == "april")
        & (df["config"] == config)
        & (df["benchmark"] == "argon_block")
        & (df["scaling"] == "strong")
        & (df["n_dim"] == n_dim)
        & (df["layout"] == layout)
        & (df["executor"] == executor)
        & (df["cell_config"] == cell_config)
        & (df["ordering"] == ordering)
        & (df["block_x"] == block_x)
        & (df["block_y"] == block_y)
        & (df["block_z"] == block_z)
    )

    out = df.loc[mask].copy()

    if out.empty:
        return out

    out["label"] = "APRIL"
    out["cores"] = out["threads"].astype(int)
    out["mups_mean"] = out["performance_mups_mean"].astype(float)

    out["mups_min"] = out.get("performance_mups_min", out["mups_mean"]).astype(float)
    out["mups_max"] = out.get("performance_mups_max", out["mups_mean"]).astype(float)
    out["mups_std"] = out.get("performance_mups_stddev", np.nan).astype(float)
    out["runs"] = out.get("n_reps", 1).astype(int)

    return out


def load_lammps(
    path: Path,
    *,
    config: str,
    n_dim: int,
    ranks: int,
    bind: str,
) -> pd.DataFrame:
    df = pd.read_csv(path)

    require_columns(
        df,
        path,
        [
            "engine",
            "config",
            "benchmark",
            "scaling",
            "n_dim",
            "dt",
            "threads",
            "ranks",
            "bind",
            "matom_step_per_second_mean",
        ],
    )

    numeric_cols = [
        "n_dim",
        "dt",
        "threads",
        "ranks",
        "matom_step_per_second_mean",
        "matom_step_per_second_min",
        "matom_step_per_second_max",
        "matom_step_per_second_stddev",
        "n_reps",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    mask = (
        (df["engine"] == "lammps")
        & (df["config"] == config)
        & (df["benchmark"] == "argon_block")
        & (df["scaling"] == "strong")
        & (df["n_dim"] == n_dim)
        & (df["ranks"] == ranks)
        & (df["bind"] == bind)
    )

    out = df.loc[mask].copy()

    if out.empty:
        return out

    out["label"] = f"LAMMPS {config.replace('-native', '')}"
    out["cores"] = out["threads"].astype(int)
    out["mups_mean"] = out["matom_step_per_second_mean"].astype(float)

    out["mups_min"] = out.get(
        "matom_step_per_second_min",
        out["mups_mean"],
    ).astype(float)

    out["mups_max"] = out.get(
        "matom_step_per_second_max",
        out["mups_mean"],
    ).astype(float)

    out["mups_std"] = out.get(
        "matom_step_per_second_stddev",
        np.nan,
    ).astype(float)

    out["runs"] = out.get("n_reps", 1).astype(int)

    return out


def select_requested_dts(df: pd.DataFrame, dts: list[float]) -> pd.DataFrame:
    frames = []

    for dt in dts:
        sub = df.loc[close_dt_mask(df["dt"], dt)].copy()

        if sub.empty:
            print(f"Skipping dt={dt:g}: no matching rows")
            continue

        sub["requested_dt"] = dt
        frames.append(sub)

    if not frames:
        raise SystemExit("No matching rows for any requested dt values.")

    return pd.concat(frames, ignore_index=True)


def plot_mups_combined(
    df: pd.DataFrame,
    dts: list[float],
    out_dir: Path,
    *,
    error_bars: str,
) -> None:
    selected = select_requested_dts(df, dts)

    selected = selected.sort_values(["requested_dt", "label", "cores"])

    out_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(
        figsize=(3.45, 2.45),
        constrained_layout=True,
    )

    markers = {
        "APRIL": "o",
        "LAMMPS openmp": "s",
        "LAMMPS intel": "^",
    }

    linestyles = ["-", "--", "-.", ":"]
    dt_style = {
        dt: linestyles[i % len(linestyles)]
        for i, dt in enumerate(dts)
    }

    labels = list(selected["label"].drop_duplicates())

    for dt in dts:
        for label in labels:
            g = selected.loc[
                (selected["requested_dt"] == dt)
                & (selected["label"] == label)
            ].sort_values("cores")

            if g.empty:
                continue

            x = g["cores"].to_numpy()
            y = g["mups_mean"].to_numpy()

            legend_label = rf"{label}, $\Delta t={dt_label(dt)}$"

            yerr = None

            if error_bars != "none" and (g["runs"] > 1).any():
                if error_bars == "stddev":
                    yerr = g["mups_std"].to_numpy()
                elif error_bars == "minmax":
                    y_min = g["mups_min"].to_numpy()
                    y_max = g["mups_max"].to_numpy()

                    lower = np.maximum(y - y_min, 0.0)
                    upper = np.maximum(y_max - y, 0.0)

                    yerr = np.vstack([lower, upper])
                else:
                    raise SystemExit(f"Unknown error bar mode: {error_bars}")

            ax.errorbar(
                x,
                y,
                yerr=yerr,
                marker=markers.get(label, "o"),
                markersize=3.5,
                linewidth=1.1,
                linestyle=dt_style[dt],
                capsize=2.0,
                capthick=0.8,
                elinewidth=0.8,
                label=legend_label,
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
    csv_path = out_dir / f"{stem}_summary.csv"

    fig.savefig(pdf_path)
    fig.savefig(png_path, dpi=300)
    plt.close(fig)

    selected.to_csv(csv_path, index=False)

    print(f"Wrote {pdf_path}")
    print(f"Wrote {png_path}")
    print(f"Wrote {csv_path}")

    table = selected.pivot_table(
        index=["requested_dt", "cores"],
        columns="label",
        values="mups_mean",
        aggfunc="first",
    )

    print()
    print("Combined throughput summary")
    print(table.to_string(float_format=lambda x: f"{x:.3f}"))
    print()


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--april-csv",
        type=Path,
        default=Path("./analysis/april_argon_block_summary.csv"),
    )
    parser.add_argument(
        "--lammps-csv",
        type=Path,
        default=Path("./analysis/lammps_argon_block_summary.csv"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("./figures/strong_scaling"),
    )

    parser.add_argument(
        "--dts",
        default="0.005,1e-7",
        help="Comma-separated timestep values to include.",
    )
    parser.add_argument(
        "--error-bars",
        choices=["none", "stddev", "minmax"],
        default="minmax",
        help="Error bars to show. Default: minmax.",
    )

    parser.add_argument("--n-dim", type=int, default=100)

    parser.add_argument("--april-config", default="native")
    parser.add_argument("--april-executor", default="OmpExecutor")
    parser.add_argument("--april-layout", default="SoA")
    parser.add_argument("--april-cell-config", default="C08")
    parser.add_argument("--april-ordering", default="hilbert")
    parser.add_argument("--april-block", default="2x2x2")

    parser.add_argument("--lammps-config", default="openmp-native")
    parser.add_argument("--lammps-ranks", type=int, default=1)
    parser.add_argument("--lammps-bind", default="close")

    args = parser.parse_args()

    if not args.april_csv.exists():
        raise SystemExit(f"Missing APRIL CSV: {args.april_csv}")

    if not args.lammps_csv.exists():
        raise SystemExit(f"Missing LAMMPS CSV: {args.lammps_csv}")

    april = load_april(
        args.april_csv,
        config=args.april_config,
        executor=args.april_executor,
        n_dim=args.n_dim,
        layout=args.april_layout,
        cell_config=args.april_cell_config,
        ordering=args.april_ordering,
        block=args.april_block,
    )

    lammps = load_lammps(
        args.lammps_csv,
        config=args.lammps_config,
        n_dim=args.n_dim,
        ranks=args.lammps_ranks,
        bind=args.lammps_bind,
    )

    if april.empty:
        raise SystemExit("No matching APRIL rows after filtering.")

    if lammps.empty:
        raise SystemExit("No matching LAMMPS rows after filtering.")

    combined = pd.concat([april, lammps], ignore_index=True)

    dts = parse_dt_list(args.dts)
    plot_mups_combined(
        combined,
        dts,
        args.out_dir,
        error_bars=args.error_bars,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())