#!/usr/bin/env python3
"""
Extract thesis-relevant APRIL benchmark numbers from parsed APRIL CSV files.

Input:
  analysis/april/april_microbench.csv
  analysis/april/april_argon_scaling.csv

Output:
  analysis/thesis/april_abstraction_overhead.csv
  analysis/thesis/april_force_kernel_focus.csv
  analysis/thesis/april_simd_layout.csv
  analysis/thesis/april_strong_scaling.csv
  analysis/thesis/april_thesis_numbers.md

This script intentionally does not use every collected benchmark.
It extracts the APRIL numbers needed for the main thesis story:

  1. APRIL vs handwritten loops.
  2. APRIL force-kernel performance.
  3. SIMD/layout impact.
  4. APRIL strong scaling.
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


def select_first(df: pd.DataFrame, description: str) -> pd.Series:
    if df.empty:
        raise SystemExit(f"No row found for: {description}")
    if len(df) > 1:
        # Keep deterministic behavior. The input usually contains one row per benchmark case/config.
        df = df.sort_values([c for c in ["run_id", "benchmark_case"] if c in df.columns])
    return df.iloc[0]


def add_speedup_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    require_columns(out, ["threads", "performance_mups"], "strong scaling table")

    one_thread = out[out["threads"] == 1]
    if one_thread.empty:
        out["speedup"] = math.nan
        out["parallel_efficiency"] = math.nan
        return out

    baseline = float(one_thread.sort_values("run_id").iloc[0]["performance_mups"])
    out["speedup"] = out["performance_mups"] / baseline
    out["parallel_efficiency"] = out["speedup"] / out["threads"]

    return out


def extract_abstraction_overhead(micro: pd.DataFrame) -> pd.DataFrame:
    """
    Main abstraction-overhead table from april_vs_hardcoded.

    Uses native config only.
    """
    df = micro[
        (micro["config"] == "native")
        & (micro["benchmark"] == "april_vs_hardcoded")
    ].copy()

    cases = [
        {
            "label": "APRIL AoS scalar",
            "match": "BM_April_DirectSum<Layout::AoS, VectorPolicy::Scalar>",
            "group": "APRIL",
            "comparison_group": "AoS scalar",
            "note": "APRIL scalar AoS accessor path.",
        },
        {
            "label": "Handwritten AoS scalar",
            "match": "BM_Baseline_Handcoded_AoS_Scalar",
            "group": "Handwritten",
            "comparison_group": "AoS scalar",
            "note": "Comparable scalar AoS handwritten loop.",
        },
        {
            "label": "APRIL SoA scalar",
            "match": "BM_April_DirectSum<Layout::SoA, VectorPolicy::Scalar>",
            "group": "APRIL",
            "comparison_group": "SoA scalar",
            "note": "APRIL scalar SoA accessor path.",
        },
        {
            "label": "Handwritten SoA scalar",
            "match": "BM_Baseline_Handcoded_SoA_Scalar",
            "group": "Handwritten",
            "comparison_group": "SoA scalar",
            "note": "Uses local accumulators; not a perfectly equal baseline.",
        },
        {
            "label": "APRIL SoA SIMD",
            "match": "BM_April_DirectSum<Layout::SoA, VectorPolicy::Auto>",
            "group": "APRIL",
            "comparison_group": "SIMD",
            "note": "APRIL vectorized SoA direct-sum path.",
        },
        {
            "label": "APRIL AoSoA SIMD",
            "match": "BM_April_DirectSum<Layout::AoSoA<>, VectorPolicy::Auto>",
            "group": "APRIL",
            "comparison_group": "SIMD",
            "note": "APRIL vectorized AoSoA direct-sum path.",
        },
        {
            "label": "Handwritten SoA 2D SIMD",
            "match": "BM_Baseline_Handcoded_SoA_2D_SIMD",
            "group": "Handwritten",
            "comparison_group": "SIMD",
            "note": "Explicit 2D SIMD rotation-sweep reference.",
        },
        {
            "label": "Handwritten SoA 1D SIMD",
            "match": "BM_Baseline_Handcoded_SoA_1D_SIMD",
            "group": "Handwritten",
            "comparison_group": "SIMD secondary",
            "note": "Broadcast-reduce SIMD reference.",
        },
    ]

    rows = []
    for case in cases:
        row = select_first(
            df[df["benchmark_case"].astype(str).str.startswith(case["match"], na=False)],
            case["label"],
        )

        rows.append({
            "label": case["label"],
            "group": case["group"],
            "comparison_group": case["comparison_group"],
            "config": row.get("config"),
            "benchmark_case": row.get("benchmark_case"),
            "ns_per_interaction": row.get("ns_per_interaction"),
            "interactions_per_second": row.get("interactions_per_second"),
            "real_time": row.get("real_time"),
            "cpu_time": row.get("cpu_time"),
            "time_unit": row.get("time_unit"),
            "run_id": row.get("run_id"),
            "note": case["note"],
        })

    out = pd.DataFrame(rows)

    # Relative ratios inside meaningful comparison groups.
    def ratio_to(label: str, baseline_label: str) -> float:
        value = float(out.loc[out["label"] == label, "ns_per_interaction"].iloc[0])
        base = float(out.loc[out["label"] == baseline_label, "ns_per_interaction"].iloc[0])
        return value / base

    ratios = {
        "APRIL AoS scalar / handwritten AoS scalar":
            ratio_to("APRIL AoS scalar", "Handwritten AoS scalar"),
        "APRIL SoA scalar / handwritten SoA scalar":
            ratio_to("APRIL SoA scalar", "Handwritten SoA scalar"),
        "APRIL SoA SIMD / handwritten SoA 2D SIMD":
            ratio_to("APRIL SoA SIMD", "Handwritten SoA 2D SIMD"),
        "APRIL AoSoA SIMD / handwritten SoA 2D SIMD":
            ratio_to("APRIL AoSoA SIMD", "Handwritten SoA 2D SIMD"),
    }

    out["ratio_context"] = ""
    out["ratio_value"] = math.nan

    for ratio_name, ratio_value in ratios.items():
        out.loc[len(out)] = {
            "label": ratio_name,
            "group": "Ratio",
            "comparison_group": "summary",
            "config": "native",
            "benchmark_case": "",
            "ns_per_interaction": math.nan,
            "interactions_per_second": math.nan,
            "real_time": math.nan,
            "cpu_time": math.nan,
            "time_unit": "",
            "run_id": "",
            "note": "Ratio < 1 means APRIL is faster; ratio > 1 means APRIL is slower.",
            "ratio_context": ratio_name,
            "ratio_value": ratio_value,
        }

    return out


def extract_force_kernel_focus(micro: pd.DataFrame) -> pd.DataFrame:
    """
    Focused force-kernel table.

    Includes native SIMD-relevant rows and native-novec scalar rows when available.
    """
    wanted = [
        # Native vectorized / realistic force traversal.
        {
            "config": "native",
            "label": "APRIL LinkedCells AoS scalar",
            "match": "BM_LinkedCells_UpdateForcesOnly<Layout::AoS, VectorPolicy::Scalar>",
            "category": "linked_cells_scalar",
        },
        {
            "config": "native",
            "label": "APRIL LinkedCells SoA scalar",
            "match": "BM_LinkedCells_UpdateForcesOnly<Layout::SoA, VectorPolicy::Scalar>",
            "category": "linked_cells_scalar",
        },
        {
            "config": "native",
            "label": "APRIL LinkedCells SoA SIMD",
            "match": "BM_LinkedCells_UpdateForcesOnly<Layout::SoA, VectorPolicy::Auto>",
            "category": "linked_cells_simd",
        },
        {
            "config": "native",
            "label": "APRIL LinkedCells AoSoA SIMD",
            "match": "BM_LinkedCells_UpdateForcesOnly<Layout::AoSoA<>, VectorPolicy::Auto>",
            "category": "linked_cells_simd",
        },
        {
            "config": "native",
            "label": "APRIL DirectSum SoA SIMD",
            "match": "BM_DirectSum_UpdateForcesOnly<Layout::SoA, VectorPolicy::Auto>",
            "category": "direct_sum_simd",
        },
        {
            "config": "native",
            "label": "APRIL DirectSum AoSoA SIMD",
            "match": "BM_DirectSum_UpdateForcesOnly<Layout::AoSoA<>, VectorPolicy::Auto>",
            "category": "direct_sum_simd",
        },
        {
            "config": "native",
            "label": "Manual Triangle SoA",
            "match": "BM_Manual_TriangleSoA",
            "category": "manual_reference",
        },
        {
            "config": "native",
            "label": "Manual Triangle SoA explicit SIMD",
            "match": "BM_Manual_TriangleSoA_ExplicitSIMD",
            "category": "manual_reference",
        },
        {
            "config": "native",
            "label": "Manual absolute max perf",
            "match": "BM_Manual_AbsoluteMaxPerf",
            "category": "lower_bound_reference",
        },
        {
            "config": "native",
            "label": "Manual realistic vector read",
            "match": "BM_Manual_RealisticVectorRead",
            "category": "manual_reference",
        },

        # Scalar/no-auto-vectorization rows. These may not exist unless native-novec was parsed.
        {
            "config": "native-novec",
            "label": "NOVEC APRIL DirectSum AoS scalar",
            "match": "BM_DirectSum_UpdateForcesOnly<Layout::AoS, VectorPolicy::Scalar>",
            "category": "novec_scalar",
            "optional": True,
        },
        {
            "config": "native-novec",
            "label": "NOVEC APRIL DirectSum SoA scalar",
            "match": "BM_DirectSum_UpdateForcesOnly<Layout::SoA, VectorPolicy::Scalar>",
            "category": "novec_scalar",
            "optional": True,
        },
        {
            "config": "native-novec",
            "label": "NOVEC Manual Triangle AoS",
            "match": "BM_Manual_TriangleAoS",
            "category": "novec_manual_reference",
            "optional": True,
        },
        {
            "config": "native-novec",
            "label": "NOVEC Manual Triangle SoA",
            "match": "BM_Manual_TriangleSoA",
            "category": "novec_manual_reference",
            "optional": True,
        },
    ]

    rows = []
    df = micro[micro["benchmark"] == "force_kernel_bench"].copy()

    for item in wanted:
        subset = df[
            (df["config"] == item["config"])
            & (df["benchmark_case"].astype(str).str.startswith(item["match"], na=False))
        ]

        if subset.empty and item.get("optional"):
            continue

        row = select_first(subset, item["label"])

        rows.append({
            "label": item["label"],
            "category": item["category"],
            "config": row.get("config"),
            "benchmark_case": row.get("benchmark_case"),
            "container": row.get("container"),
            "layout": row.get("layout"),
            "vector_policy": row.get("vector_policy"),
            "implementation": row.get("implementation"),
            "workload": row.get("workload"),
            "ns_per_interaction": row.get("ns_per_interaction"),
            "interactions_per_second": row.get("interactions_per_second"),
            "real_time": row.get("real_time"),
            "cpu_time": row.get("cpu_time"),
            "time_unit": row.get("time_unit"),
            "run_id": row.get("run_id"),
        })

    out = pd.DataFrame(rows)

    # Add speedup relative to key scalar baselines where possible.
    def add_relative(reference_label: str, column_name: str) -> None:
        ref_rows = out[out["label"] == reference_label]
        if ref_rows.empty:
            out[column_name] = math.nan
            return

        ref_ns = float(ref_rows.iloc[0]["ns_per_interaction"])
        out[column_name] = ref_ns / out["ns_per_interaction"]

    add_relative("APRIL LinkedCells AoS scalar", "speedup_vs_lc_aos_scalar")
    add_relative("APRIL LinkedCells SoA scalar", "speedup_vs_lc_soa_scalar")
    add_relative("APRIL DirectSum AoSoA SIMD", "speedup_vs_april_directsum_aosoa_simd")

    return out


def extract_simd_layout(micro: pd.DataFrame) -> pd.DataFrame:
    """
    Small table focused only on SIMD/layout effect.
    """
    df = micro[
        (micro["config"] == "native")
        & (micro["benchmark"] == "force_kernel_bench")
    ].copy()

    wanted = [
        {
            "label": "DirectSum AoS scalar",
            "match": "BM_DirectSum_UpdateForcesOnly<Layout::AoS, VectorPolicy::Scalar>",
        },
        {
            "label": "DirectSum SoA scalar",
            "match": "BM_DirectSum_UpdateForcesOnly<Layout::SoA, VectorPolicy::Scalar>",
        },
        {
            "label": "DirectSum SoA SIMD",
            "match": "BM_DirectSum_UpdateForcesOnly<Layout::SoA, VectorPolicy::Auto>",
        },
        {
            "label": "DirectSum AoSoA SIMD",
            "match": "BM_DirectSum_UpdateForcesOnly<Layout::AoSoA<>, VectorPolicy::Auto>",
        },
        {
            "label": "LinkedCells AoS scalar",
            "match": "BM_LinkedCells_UpdateForcesOnly<Layout::AoS, VectorPolicy::Scalar>",
        },
        {
            "label": "LinkedCells SoA scalar",
            "match": "BM_LinkedCells_UpdateForcesOnly<Layout::SoA, VectorPolicy::Scalar>",
        },
        {
            "label": "LinkedCells SoA SIMD",
            "match": "BM_LinkedCells_UpdateForcesOnly<Layout::SoA, VectorPolicy::Auto>",
        },
        {
            "label": "LinkedCells AoSoA SIMD",
            "match": "BM_LinkedCells_UpdateForcesOnly<Layout::AoSoA<>, VectorPolicy::Auto>",
        },
    ]

    rows = []
    for item in wanted:
        row = select_first(
            df[df["benchmark_case"].astype(str).str.startswith(item["match"], na=False)],
            item["label"],
        )

        rows.append({
            "label": item["label"],
            "config": row.get("config"),
            "benchmark_case": row.get("benchmark_case"),
            "container": row.get("container"),
            "layout": row.get("layout"),
            "vector_policy": row.get("vector_policy"),
            "implementation": row.get("implementation"),
            "ns_per_interaction": row.get("ns_per_interaction"),
            "interactions_per_second": row.get("interactions_per_second"),
            "run_id": row.get("run_id"),
        })

    out = pd.DataFrame(rows)

    # Container-local speedups.
    for container in ["DirectSum", "LinkedCells"]:
        scalar = out[
            (out["container"] == container)
            & (out["label"].str.contains("AoS scalar"))
        ]
        if not scalar.empty:
            base = float(scalar.iloc[0]["ns_per_interaction"])
            mask = out["container"] == container
            out.loc[mask, "speedup_vs_aos_scalar"] = base / out.loc[mask, "ns_per_interaction"]

    return out


def extract_strong_scaling(argon: pd.DataFrame) -> pd.DataFrame:
    """
    Extract main APRIL native strong scaling runs.

    Default main scenario:
      config=native
      scaling=strong
      layout=SoA
      schedule=C08
      ordering=hilbert

    Keeps all executors, but the resulting CSV can be filtered later.
    """
    df = argon.copy()

    require_columns(
        df,
        ["config", "scaling", "n", "rho", "dt", "steps", "layout", "schedule", "ordering", "threads", "performance_mups"],
        "april_argon_scaling.csv",
    )

    df = clean_numeric(df, ["n", "rho", "dt", "steps", "threads", "performance_mups"])

    main = df[
        (df["config"] == "native")
        & (df["scaling"] == "strong")
        & (df["layout"] == "SoA")
        & (df["schedule"] == "C08")
        & (df["ordering"] == "hilbert")
    ].copy()

    if main.empty:
        raise SystemExit("No APRIL native strong-scaling rows found for SoA/C08/hilbert.")

    # Keep only the scenarios relevant for the thesis comparison.
    # This preserves both dt=0.005 and dt=1e-7 if both exist.
    columns = [
        "engine",
        "config",
        "scenario",
        "run_id",
        "scaling",
        "n",
        "particles",
        "rho",
        "dt",
        "steps",
        "bx",
        "by",
        "bz",
        "schedule",
        "layout",
        "executor",
        "ordering",
        "threads",
        "total_cores",
        "integration_time_s",
        "performance_mups",
        "mups_computed",
        "avg_step_time_s",
        "median_step_time_s",
        "std_deviation_s",
        "wall_time_seconds",
    ]

    columns = [c for c in columns if c in main.columns]
    main = main[columns].copy()

    # Speedup per unique scenario family.
    group_cols = [
        c for c in ["dt", "n", "rho", "steps", "bx", "by", "bz", "schedule", "layout", "executor", "ordering"]
        if c in main.columns
    ]

    out_parts = []
    for _, group in main.groupby(group_cols, dropna=False):
        g = group.sort_values("threads").copy()
        g = add_speedup_columns(g)
        out_parts.append(g)

    return pd.concat(out_parts, ignore_index=True)


def write_markdown_summary(
    path: Path,
    abstraction: pd.DataFrame,
    force: pd.DataFrame,
    scaling: pd.DataFrame,
) -> None:
    lines: list[str] = []

    lines.append("# APRIL thesis numbers")
    lines.append("")

    lines.append("## Abstraction overhead")
    lines.append("")
    abs_main = abstraction[abstraction["group"] != "Ratio"].copy()
    lines.append(abs_main[[
        "label",
        "ns_per_interaction",
        "interactions_per_second",
        "note",
    ]].to_markdown(index=False))
    lines.append("")

    ratios = abstraction[abstraction["group"] == "Ratio"].copy()
    if not ratios.empty:
        lines.append("### Ratios")
        lines.append("")
        lines.append(ratios[["label", "ratio_value", "note"]].to_markdown(index=False))
        lines.append("")

    lines.append("## Force-kernel focus")
    lines.append("")
    lines.append(force[[
        "label",
        "config",
        "category",
        "ns_per_interaction",
        "interactions_per_second",
    ]].to_markdown(index=False))
    lines.append("")

    lines.append("## APRIL strong scaling")
    lines.append("")
    cols = [
        "dt",
        "n",
        "threads",
        "executor",
        "performance_mups",
        "speedup",
        "parallel_efficiency",
        "median_step_time_s",
    ]
    cols = [c for c in cols if c in scaling.columns]
    lines.append(scaling[cols].sort_values([c for c in ["dt", "executor", "threads"] if c in cols]).to_markdown(index=False))
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--april-dir", type=Path, default=Path("analysis/april"))
    parser.add_argument("--out-dir", type=Path, default=Path("analysis/thesis"))
    args = parser.parse_args()

    root = args.project_root.resolve()
    april_dir = args.april_dir if args.april_dir.is_absolute() else root / args.april_dir
    out_dir = args.out_dir if args.out_dir.is_absolute() else root / args.out_dir

    out_dir.mkdir(parents=True, exist_ok=True)

    micro = read_csv(april_dir / "april_microbench.csv")
    argon = read_csv(april_dir / "april_argon_scaling.csv")

    micro = clean_numeric(
        micro,
        [
            "ns_per_interaction",
            "interactions_per_second",
            "real_time",
            "cpu_time",
            "threads",
            "items_per_second",
        ],
    )

    argon = clean_numeric(
        argon,
        [
            "n",
            "particles",
            "rho",
            "dt",
            "steps",
            "threads",
            "total_cores",
            "integration_time_s",
            "performance_mups",
            "mups_computed",
            "avg_step_time_s",
            "median_step_time_s",
            "std_deviation_s",
            "wall_time_seconds",
        ],
    )

    abstraction = extract_abstraction_overhead(micro)
    force = extract_force_kernel_focus(micro)
    simd_layout = extract_simd_layout(micro)
    scaling = extract_strong_scaling(argon)

    abstraction.to_csv(out_dir / "april_abstraction_overhead.csv", index=False)
    force.to_csv(out_dir / "april_force_kernel_focus.csv", index=False)
    simd_layout.to_csv(out_dir / "april_simd_layout.csv", index=False)
    scaling.to_csv(out_dir / "april_strong_scaling.csv", index=False)

    write_markdown_summary(
        out_dir / "april_thesis_numbers.md",
        abstraction,
        force,
        scaling,
    )

    print(f"Wrote {out_dir / 'april_abstraction_overhead.csv'}")
    print(f"Wrote {out_dir / 'april_force_kernel_focus.csv'}")
    print(f"Wrote {out_dir / 'april_simd_layout.csv'}")
    print(f"Wrote {out_dir / 'april_strong_scaling.csv'}")
    print(f"Wrote {out_dir / 'april_thesis_numbers.md'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())