#!/usr/bin/env python3
"""
Create thesis plots from focused APRIL and LAMMPS CSVs.

Inputs:
  analysis/thesis/april_abstraction_overhead.csv
  analysis/thesis/april_force_kernel_focus.csv
  analysis/thesis/april_simd_layout.csv
  analysis/thesis/april_strong_scaling.csv
  analysis/thesis/lammps_strong_scaling.csv
  analysis/thesis/lammps_force_kernel_focus.csv
  analysis/thesis/lammps_timing_breakdown.csv

Outputs:
  analysis/plots/*.pdf
  analysis/plots/*.png
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


def numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def aggregate_scaling(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """
    Aggregate repeated runs by median. Keeps performance variation from duplicate
    runs from cluttering the plots.
    """
    metric_cols = [
        "performance_mups",
        "speedup",
        "parallel_efficiency",
        "median_step_time_s",
        "avg_step_time_s",
        "loop_time_s",
        "neighbor_list_builds",
    ]
    metric_cols = [c for c in metric_cols if c in df.columns]

    out = (
        df.groupby(group_cols, dropna=False)[metric_cols]
        .median()
        .reset_index()
        .sort_values(group_cols)
    )
    return out


def plot_april_abstraction(april_abs: pd.DataFrame, out_dir: Path) -> None:
    df = april_abs[april_abs["group"] != "Ratio"].copy()
    df = numeric(df, ["ns_per_interaction"])

    order = [
        "APRIL AoS scalar",
        "Handwritten AoS scalar",
        "APRIL SoA scalar",
        "Handwritten SoA scalar",
        "APRIL SoA SIMD",
        "APRIL AoSoA SIMD",
        "Handwritten SoA 2D SIMD",
        "Handwritten SoA 1D SIMD",
    ]
    df["label"] = pd.Categorical(df["label"], categories=order, ordered=True)
    df = df.sort_values("label")

    plt.figure(figsize=(10, 4.8))
    plt.bar(df["label"].astype(str), df["ns_per_interaction"])
    plt.ylabel("ns / interaction")
    plt.title("APRIL abstraction overhead vs handwritten kernels")
    plt.xticks(rotation=35, ha="right")
    plt.grid(axis="y", alpha=0.3)

    savefig(out_dir, "april_abstraction_overhead")


def plot_april_force_kernel(april_force: pd.DataFrame, out_dir: Path) -> None:
    df = april_force.copy()
    df = numeric(df, ["ns_per_interaction"])

    labels = [
        "APRIL LinkedCells AoSoA SIMD",
        "APRIL DirectSum AoSoA SIMD",
        "Manual Triangle SoA",
        "Manual Triangle SoA explicit SIMD",
        "Manual absolute max perf",
        "NOVEC APRIL DirectSum AoS scalar",
        "NOVEC Manual Triangle AoS",
        "NOVEC APRIL DirectSum SoA scalar",
        "NOVEC Manual Triangle SoA",
    ]
    df = df[df["label"].isin(labels)].copy()
    df["label"] = pd.Categorical(df["label"], categories=labels, ordered=True)
    df = df.sort_values("label")

    plt.figure(figsize=(10, 5.2))
    plt.bar(df["label"].astype(str), df["ns_per_interaction"])
    plt.ylabel("ns / interaction")
    plt.title("APRIL force-kernel performance against manual references")
    plt.xticks(rotation=35, ha="right")
    plt.grid(axis="y", alpha=0.3)

    savefig(out_dir, "april_force_kernel_focus")


def plot_april_simd_layout(april_simd: pd.DataFrame, out_dir: Path) -> None:
    df = april_simd.copy()
    df = numeric(df, ["ns_per_interaction"])

    containers = ["DirectSum", "LinkedCells"]
    labels_by_container = {
        "DirectSum": [
            "DirectSum AoS scalar",
            "DirectSum SoA scalar",
            "DirectSum SoA SIMD",
            "DirectSum AoSoA SIMD",
        ],
        "LinkedCells": [
            "LinkedCells AoS scalar",
            "LinkedCells SoA scalar",
            "LinkedCells SoA SIMD",
            "LinkedCells AoSoA SIMD",
        ],
    }

    for container in containers:
        part = df[df["label"].isin(labels_by_container[container])].copy()
        part["label"] = pd.Categorical(part["label"], categories=labels_by_container[container], ordered=True)
        part = part.sort_values("label")

        plt.figure(figsize=(8.5, 4.6))
        plt.bar(part["label"].astype(str), part["ns_per_interaction"])
        plt.ylabel("ns / interaction")
        plt.title(f"APRIL SIMD/layout impact: {container}")
        plt.xticks(rotation=30, ha="right")
        plt.grid(axis="y", alpha=0.3)

        savefig(out_dir, f"april_simd_layout_{container.lower()}")


def plot_april_strong_scaling(april_scaling: pd.DataFrame, out_dir: Path) -> None:
    df = april_scaling.copy()
    df = numeric(df, ["dt", "n", "threads", "performance_mups", "speedup", "parallel_efficiency"])

    # Focus on the main n=100 runs. Exclude n=160 sensitivity sweep.
    df = df[(df["n"] == 100)].copy()

    # Keep main executor lines. Omp is primary; NativeSpin is useful for dt=0.005 if present.
    df = df[df["executor"].isin(["OmpExecutor", "NativeSpinExecutor"])].copy()

    grouped = aggregate_scaling(
        df,
        ["dt", "n", "executor", "threads"],
    )

    plt.figure(figsize=(8, 5))
    for (dt, executor), part in grouped.groupby(["dt", "executor"]):
        part = part.sort_values("threads")
        label = f"dt={dt:g}, {executor}"
        plt.plot(part["threads"], part["performance_mups"], marker="o", label=label)

    plt.xlabel("Threads")
    plt.ylabel("MUPS")
    plt.title("APRIL strong scaling")
    plt.grid(alpha=0.3)
    plt.legend()

    savefig(out_dir, "april_strong_scaling_mups")

    plt.figure(figsize=(8, 5))
    for (dt, executor), part in grouped.groupby(["dt", "executor"]):
        part = part.sort_values("threads")

        # Recompute speedup after aggregation.
        base = part.loc[part["threads"] == 1, "performance_mups"]
        if base.empty:
            continue
        speedup = part["performance_mups"] / float(base.iloc[0])

        label = f"dt={dt:g}, {executor}"
        plt.plot(part["threads"], speedup, marker="o", label=label)

    max_threads = grouped["threads"].max()
    plt.plot([1, max_threads], [1, max_threads], linestyle="--", label="ideal")
    plt.xlabel("Threads")
    plt.ylabel("Speedup")
    plt.title("APRIL strong scaling speedup")
    plt.grid(alpha=0.3)
    plt.legend()

    savefig(out_dir, "april_strong_scaling_speedup")


def plot_april_vs_lammps(
    april_scaling: pd.DataFrame,
    lammps_scaling: pd.DataFrame,
    out_dir: Path,
) -> None:
    a = april_scaling.copy()
    l = lammps_scaling.copy()

    a = numeric(a, ["dt", "n", "threads", "total_cores", "performance_mups"])
    l = numeric(l, ["dt", "n", "threads", "total_cores", "performance_mups"])

    # Main comparable setup.
    a = a[
        (a["n"] == 100)
        & (a["layout"] == "SoA")
        & (a["schedule"] == "C08")
        & (a["ordering"] == "hilbert")
        & (a["executor"] == "OmpExecutor")
    ].copy()

    l = l[
        (l["n"] == 100)
        & (l["config"] == "openmp-native")
        & (l["mode"] == "threads")
    ].copy()

    a_group = aggregate_scaling(a, ["dt", "threads"])
    a_group = a_group.rename(columns={"threads": "total_cores"})
    a_group["engine_label"] = "APRIL native"

    l_group = aggregate_scaling(l, ["dt", "total_cores"])
    l_group["engine_label"] = "LAMMPS openmp-native"

    combined = pd.concat([a_group, l_group], ignore_index=True)

    for dt in sorted(combined["dt"].dropna().unique()):
        part_dt = combined[combined["dt"] == dt].copy()

        plt.figure(figsize=(8, 5))
        for engine, part in part_dt.groupby("engine_label"):
            part = part.sort_values("total_cores")
            plt.plot(part["total_cores"], part["performance_mups"], marker="o", label=engine)

        plt.xlabel("Cores / threads")
        plt.ylabel("MUPS")
        plt.title(f"APRIL vs LAMMPS strong scaling, dt={dt:g}")
        plt.grid(alpha=0.3)
        plt.legend()

        savefig(out_dir, f"april_vs_lammps_strong_scaling_dt_{dt:g}".replace(".", "p").replace("-", "m"))


def plot_lammps_timing_breakdown(lammps_timing: pd.DataFrame, out_dir: Path) -> None:
    df = lammps_timing.copy()
    df = numeric(
        df,
        [
            "dt",
            "total_cores",
            "pair_percent",
            "neigh_percent",
            "modify_percent",
            "comm_percent",
            "other_percent",
        ],
    )

    df = df[(df["config"] == "openmp-native") & (df["total_cores"].isin([1, 8, 16, 32, 56]))].copy()

    for dt in sorted(df["dt"].dropna().unique()):
        part = df[df["dt"] == dt].copy()

        # Aggregate duplicate dt=0.005 runs.
        cols = ["pair_percent", "neigh_percent", "modify_percent", "comm_percent", "other_percent"]
        part = part.groupby("total_cores", dropna=False)[cols].median().reset_index()
        part = part.sort_values("total_cores")

        x = range(len(part))
        bottom = [0.0] * len(part)

        plt.figure(figsize=(8, 5))
        for col, label in [
            ("pair_percent", "Pair"),
            ("neigh_percent", "Neighbor"),
            ("modify_percent", "Modify"),
            ("comm_percent", "Comm"),
            ("other_percent", "Other"),
        ]:
            values = part[col].fillna(0).to_numpy()
            plt.bar(x, values, bottom=bottom, label=label)
            bottom = [b + v for b, v in zip(bottom, values)]

        plt.xticks(list(x), part["total_cores"].astype(int).astype(str))
        plt.xlabel("Cores / threads")
        plt.ylabel("Share of timestep time [%]")
        plt.title(f"LAMMPS timing breakdown, dt={dt:g}")
        plt.ylim(0, 100)
        plt.legend()
        plt.grid(axis="y", alpha=0.3)

        savefig(out_dir, f"lammps_timing_breakdown_dt_{dt:g}".replace(".", "p").replace("-", "m"))


def plot_force_kernel_april_vs_lammps(
    april_force: pd.DataFrame,
    lammps_force: pd.DataFrame,
    out_dir: Path,
) -> None:
    a = april_force.copy()
    l = lammps_force.copy()

    a = numeric(a, ["ns_per_interaction"])
    l = numeric(l, ["pair_ns_per_interaction"])

    # Representative APRIL force rows.
    a_labels = [
        "APRIL LinkedCells AoSoA SIMD",
        "APRIL DirectSum AoSoA SIMD",
        "NOVEC APRIL DirectSum AoS scalar",
        "NOVEC APRIL DirectSum SoA scalar",
    ]
    a = a[a["label"].isin(a_labels)].copy()
    a = a[["label", "ns_per_interaction"]].rename(columns={"ns_per_interaction": "ns"})

    # Representative LAMMPS rows. Aggregate duplicates by median.
    l = l[l["config"].isin(["openmp-native", "intel-native"])].copy()
    l = (
        l.groupby("config", dropna=False)["pair_ns_per_interaction"]
        .median()
        .reset_index()
    )
    l["label"] = "LAMMPS " + l["config"].astype(str)
    l = l[["label", "pair_ns_per_interaction"]].rename(columns={"pair_ns_per_interaction": "ns"})

    combined = pd.concat([a, l], ignore_index=True)

    order = a_labels + ["LAMMPS openmp-native", "LAMMPS intel-native"]
    combined["label"] = pd.Categorical(combined["label"], categories=order, ordered=True)
    combined = combined.sort_values("label")

    plt.figure(figsize=(9, 4.8))
    plt.bar(combined["label"].astype(str), combined["ns"])
    plt.ylabel("ns / interaction")
    plt.title("Force-kernel reference comparison")
    plt.xticks(rotation=35, ha="right")
    plt.grid(axis="y", alpha=0.3)

    savefig(out_dir, "force_kernel_april_vs_lammps")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--thesis-dir", type=Path, default=Path("analysis/thesis"))
    parser.add_argument("--out-dir", type=Path, default=Path("analysis/plots"))
    args = parser.parse_args()

    root = args.project_root.resolve()
    thesis_dir = args.thesis_dir if args.thesis_dir.is_absolute() else root / args.thesis_dir
    out_dir = args.out_dir if args.out_dir.is_absolute() else root / args.out_dir

    april_abs = read_csv(thesis_dir / "april_abstraction_overhead.csv")
    april_force = read_csv(thesis_dir / "april_force_kernel_focus.csv")
    april_simd = read_csv(thesis_dir / "april_simd_layout.csv")
    april_scaling = read_csv(thesis_dir / "april_strong_scaling.csv")

    lammps_scaling = read_csv(thesis_dir / "lammps_strong_scaling.csv")
    lammps_force = read_csv(thesis_dir / "lammps_force_kernel_focus.csv")
    lammps_timing = read_csv(thesis_dir / "lammps_timing_breakdown.csv")

    plot_april_abstraction(april_abs, out_dir)
    plot_april_force_kernel(april_force, out_dir)
    plot_april_simd_layout(april_simd, out_dir)
    plot_april_strong_scaling(april_scaling, out_dir)
    plot_april_vs_lammps(april_scaling, lammps_scaling, out_dir)
    plot_lammps_timing_breakdown(lammps_timing, out_dir)
    plot_force_kernel_april_vs_lammps(april_force, lammps_force, out_dir)

    print(f"Wrote plots to: {out_dir}")


if __name__ == "__main__":
    raise SystemExit(main())