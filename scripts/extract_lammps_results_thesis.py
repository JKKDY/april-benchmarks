#!/usr/bin/env python3
"""
Extract thesis-relevant LAMMPS benchmark numbers from parsed LAMMPS CSV files.

Input:
  analysis/lammps/lammps_scaling.csv
  analysis/lammps/lammps_force_kernel.csv

Output:
  analysis/thesis/lammps_strong_scaling.csv
  analysis/thesis/lammps_force_kernel_focus.csv
  analysis/thesis/lammps_timing_breakdown.csv
  analysis/thesis/lammps_thesis_numbers.md

This script intentionally does not use every collected LAMMPS benchmark.
It extracts the LAMMPS numbers needed for the main thesis story:

  1. LAMMPS OpenMP strong scaling.
  2. LAMMPS force-kernel / pair-section performance.
  3. LAMMPS timestep timing breakdown: Pair, Neigh, Comm, Modify.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"Missing input CSV: {path}")
    return pd.read_csv(path)


def clean_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def require_columns(df: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise SystemExit(f"{name} is missing required columns: {missing}")


def add_speedup_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    require_columns(out, ["total_cores", "performance_mups"], "strong scaling table")

    one_core = out[out["total_cores"] == 1]
    if one_core.empty:
        out["speedup"] = math.nan
        out["parallel_efficiency"] = math.nan
        return out

    baseline = float(one_core.sort_values("run_id").iloc[0]["performance_mups"])
    out["speedup"] = out["performance_mups"] / baseline
    out["parallel_efficiency"] = out["speedup"] / out["total_cores"]

    return out


def add_timing_percentages(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    for col in ["pair_time_s", "neigh_time_s", "comm_time_s", "modify_time_s", "loop_time_s"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    if "loop_time_s" not in out.columns:
        return out

    components = {
        "pair_time_s": "pair_percent",
        "neigh_time_s": "neigh_percent",
        "comm_time_s": "comm_percent",
        "modify_time_s": "modify_percent",
    }

    for source, dest in components.items():
        if source in out.columns:
            out[dest] = 100.0 * out[source] / out["loop_time_s"]

    known = [
        col for col in ["pair_time_s", "neigh_time_s", "comm_time_s", "modify_time_s"]
        if col in out.columns
    ]

    if known:
        out["known_timing_time_s"] = out[known].sum(axis=1)
        out["known_timing_percent"] = 100.0 * out["known_timing_time_s"] / out["loop_time_s"]
        out["other_time_s"] = out["loop_time_s"] - out["known_timing_time_s"]
        out["other_percent"] = 100.0 * out["other_time_s"] / out["loop_time_s"]

    return out


def extract_openmp_strong_scaling(
    scaling: pd.DataFrame,
    *,
    preferred_config: str,
) -> pd.DataFrame:
    """
    Extract LAMMPS OpenMP strong-scaling rows.

    Main thesis comparison should usually use openmp-native because APRIL native
    is also built with native CPU flags.

    Keeps both dt=0.005 and dt=1e-7 when available.
    """
    require_columns(
        scaling,
        [
            "config",
            "benchmark",
            "scaling",
            "n",
            "particles",
            "rho",
            "dt",
            "steps",
            "mode",
            "ranks",
            "threads",
            "total_cores",
            "performance_mups",
        ],
        "lammps_scaling.csv",
    )

    df = scaling.copy()
    df = clean_numeric(
        df,
        [
            "n",
            "particles",
            "rho",
            "dt",
            "steps",
            "ranks",
            "threads",
            "total_cores",
            "performance_mups",
            "loop_time_s",
            "avg_step_time_s",
            "pair_time_s",
            "neigh_time_s",
            "comm_time_s",
            "modify_time_s",
            "neighbor_list_builds",
            "total_neighbors",
            "pair_ns_per_interaction",
            "pair_interactions_per_second",
        ],
    )

    # Prefer openmp-native, but fall back to openmp-generic if not present.
    preferred = df[
        (df["benchmark"] == "argon_block")
        & (df["kind"] == "scaling")
        & (df["scaling"] == "strong")
        & (df["config"] == preferred_config)
        & (df["mode"] == "threads")
    ].copy()

    if preferred.empty and preferred_config == "openmp-native":
        preferred = df[
            (df["benchmark"] == "argon_block")
            & (df["kind"] == "scaling")
            & (df["scaling"] == "strong")
            & (df["config"] == "openmp-generic")
            & (df["mode"] == "threads")
        ].copy()

    if preferred.empty:
        raise SystemExit(
            f"No LAMMPS OpenMP strong-scaling rows found for config={preferred_config!r} "
            "or fallback openmp-generic."
        )

    columns = [
        "engine",
        "kind",
        "config",
        "benchmark",
        "scenario",
        "run_id",
        "scaling",
        "mode",
        "n",
        "particles",
        "rho",
        "dt",
        "steps",
        "ranks",
        "threads",
        "total_cores",
        "bind",
        "loop_time_s",
        "performance_mups",
        "avg_step_time_s",
        "timesteps_per_second",
        "matom_step_per_second",
        "cpu_use_percent",
        "pair_time_s",
        "neigh_time_s",
        "comm_time_s",
        "modify_time_s",
        "total_neighbors",
        "neighbor_list_builds",
        "pair_ns_per_interaction",
        "pair_interactions_per_second",
        "wall_time_s",
        "hostname",
        "run_date",
        "pkg_openmp",
        "pkg_intel",
        "extra_cxx_flags",
        "lammps_commit",
        "benchmark_repo_commit",
        "command",
        "result_dir",
    ]
    columns = [c for c in columns if c in preferred.columns]
    preferred = preferred[columns].copy()

    group_cols = [
        c for c in ["config", "dt", "n", "rho", "steps", "mode", "bind"]
        if c in preferred.columns
    ]

    parts = []
    for _, group in preferred.groupby(group_cols, dropna=False):
        g = group.sort_values("total_cores").copy()
        g = add_speedup_columns(g)
        parts.append(g)

    out = pd.concat(parts, ignore_index=True)
    return out


def extract_force_kernel_focus(force: pd.DataFrame) -> pd.DataFrame:
    """
    Extract force-kernel LAMMPS pair-section rows.

    For LAMMPS force_kernel_bench, the most relevant metric is the Pair section:
      pair_ns_per_interaction
      pair_interactions_per_second
    """
    require_columns(
        force,
        [
            "config",
            "benchmark",
            "kind",
            "n",
            "particles",
            "steps",
            "pair_time_s",
            "neighbors_per_step",
            "pair_ns_per_interaction",
            "pair_interactions_per_second",
        ],
        "lammps_force_kernel.csv",
    )

    df = force.copy()
    df = clean_numeric(
        df,
        [
            "n",
            "particles",
            "steps",
            "ranks",
            "threads",
            "total_cores",
            "pair_time_s",
            "neighbors_per_step",
            "ns_per_interaction",
            "interactions_per_second",
            "pair_ns_per_interaction",
            "pair_interactions_per_second",
            "wall_time_s",
        ],
    )

    df = df[
        (df["benchmark"] == "force_kernel_bench")
        & (df["kind"] == "force_kernel")
    ].copy()

    if df.empty:
        raise SystemExit("No LAMMPS force-kernel rows found.")

    # Keep the main configs. If you later want Intel package comparisons,
    # this CSV already supports that.
    rows = []
    for _, row in df.sort_values(["config", "n", "steps", "run_id"]).iterrows():
        label = f"LAMMPS {row.get('config')} force kernel"

        rows.append({
            "label": label,
            "engine": row.get("engine"),
            "config": row.get("config"),
            "benchmark": row.get("benchmark"),
            "scenario": row.get("scenario"),
            "run_id": row.get("run_id"),
            "n": row.get("n"),
            "particles": row.get("particles"),
            "steps": row.get("steps"),
            "ranks": row.get("ranks"),
            "threads": row.get("threads"),
            "total_cores": row.get("total_cores"),
            "pair_time_s": row.get("pair_time_s"),
            "neighbors_per_step": row.get("neighbors_per_step"),
            "ns_per_interaction": row.get("ns_per_interaction"),
            "interactions_per_second": row.get("interactions_per_second"),
            "pair_ns_per_interaction": row.get("pair_ns_per_interaction"),
            "pair_interactions_per_second": row.get("pair_interactions_per_second"),
            "wall_time_s": row.get("wall_time_s"),
            "pkg_openmp": row.get("pkg_openmp"),
            "pkg_intel": row.get("pkg_intel"),
            "extra_cxx_flags": row.get("extra_cxx_flags"),
            "lammps_commit": row.get("lammps_commit"),
            "benchmark_repo_commit": row.get("benchmark_repo_commit"),
            "command": row.get("command"),
            "result_dir": row.get("result_dir"),
        })

    return pd.DataFrame(rows)


def extract_timing_breakdown(strong_scaling: pd.DataFrame) -> pd.DataFrame:
    """
    Extract timing breakdown rows from LAMMPS argon strong-scaling runs.
    """
    df = strong_scaling.copy()

    keep = [
        "engine",
        "config",
        "scenario",
        "run_id",
        "scaling",
        "mode",
        "n",
        "particles",
        "rho",
        "dt",
        "steps",
        "ranks",
        "threads",
        "total_cores",
        "loop_time_s",
        "pair_time_s",
        "neigh_time_s",
        "comm_time_s",
        "modify_time_s",
        "neighbor_list_builds",
        "total_neighbors",
        "pair_ns_per_interaction",
        "performance_mups",
    ]
    keep = [c for c in keep if c in df.columns]

    out = df[keep].copy()
    out = add_timing_percentages(out)

    return out


def write_markdown_summary(
    path: Path,
    scaling: pd.DataFrame,
    force: pd.DataFrame,
    timing: pd.DataFrame,
) -> None:
    lines: list[str] = []

    lines.append("# LAMMPS thesis numbers")
    lines.append("")

    lines.append("## OpenMP strong scaling")
    lines.append("")
    cols = [
        "config",
        "dt",
        "n",
        "total_cores",
        "ranks",
        "threads",
        "performance_mups",
        "speedup",
        "parallel_efficiency",
        "loop_time_s",
        "avg_step_time_s",
        "neighbor_list_builds",
    ]
    cols = [c for c in cols if c in scaling.columns]
    lines.append(
        scaling[cols]
        .sort_values([c for c in ["dt", "config", "total_cores"] if c in cols])
        .to_markdown(index=False)
    )
    lines.append("")

    lines.append("## Force-kernel pair-section performance")
    lines.append("")
    cols = [
        "label",
        "config",
        "n",
        "particles",
        "steps",
        "pair_time_s",
        "neighbors_per_step",
        "pair_ns_per_interaction",
        "pair_interactions_per_second",
    ]
    cols = [c for c in cols if c in force.columns]
    lines.append(force[cols].to_markdown(index=False))
    lines.append("")

    lines.append("## Timing breakdown")
    lines.append("")
    cols = [
        "config",
        "dt",
        "total_cores",
        "loop_time_s",
        "pair_time_s",
        "pair_percent",
        "neigh_time_s",
        "neigh_percent",
        "modify_time_s",
        "modify_percent",
        "other_time_s",
        "other_percent",
        "neighbor_list_builds",
    ]
    cols = [c for c in cols if c in timing.columns]
    lines.append(
        timing[cols]
        .sort_values([c for c in ["dt", "config", "total_cores"] if c in cols])
        .to_markdown(index=False)
    )
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--lammps-dir", type=Path, default=Path("analysis/lammps"))
    parser.add_argument("--out-dir", type=Path, default=Path("analysis/thesis"))
    parser.add_argument(
        "--preferred-openmp-config",
        default="openmp-native",
        help="Preferred LAMMPS OpenMP config for main scaling comparison.",
    )
    args = parser.parse_args()

    root = args.project_root.resolve()
    lammps_dir = args.lammps_dir if args.lammps_dir.is_absolute() else root / args.lammps_dir
    out_dir = args.out_dir if args.out_dir.is_absolute() else root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    scaling = read_csv(lammps_dir / "lammps_scaling.csv")
    force = read_csv(lammps_dir / "lammps_force_kernel.csv")

    strong_scaling = extract_openmp_strong_scaling(
        scaling,
        preferred_config=args.preferred_openmp_config,
    )
    force_focus = extract_force_kernel_focus(force)
    timing_breakdown = extract_timing_breakdown(strong_scaling)

    strong_scaling.to_csv(out_dir / "lammps_strong_scaling.csv", index=False)
    force_focus.to_csv(out_dir / "lammps_force_kernel_focus.csv", index=False)
    timing_breakdown.to_csv(out_dir / "lammps_timing_breakdown.csv", index=False)

    write_markdown_summary(
        out_dir / "lammps_thesis_numbers.md",
        strong_scaling,
        force_focus,
        timing_breakdown,
    )

    print(f"Wrote {out_dir / 'lammps_strong_scaling.csv'}")
    print(f"Wrote {out_dir / 'lammps_force_kernel_focus.csv'}")
    print(f"Wrote {out_dir / 'lammps_timing_breakdown.csv'}")
    print(f"Wrote {out_dir / 'lammps_thesis_numbers.md'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())