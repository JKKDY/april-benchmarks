#!/usr/bin/env python3
"""
Extract APRIL benchmark results into CSV files.

Expected layout:

  ./results/april/native/argon_block/...
  ./results/april/native/april_vs_hardcoded/...

Outputs:

  ./analysis/april_argon_block_runs.csv
  ./analysis/april_argon_block_summary.csv
  ./analysis/april_vs_hardcoded_runs.csv
  ./analysis/april_vs_hardcoded_summary.csv

Paper-relevant metrics:
  - argon_block: Performance MUPS from APRIL stdout.log
  - april_vs_hardcoded: aggregate mean real_time from Google Benchmark JSON
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


ARGON_SCENARIO_RE = re.compile(
    r"^(?P<scaling>strong|weak)"
    r"_n(?P<n_dim>\d+)"
    r"_p(?P<particles>\d+)"
    r"_rho(?P<rho>[0-9.]+)"
    r"_dt(?P<dt>[0-9.]+)"
    r"_steps(?P<steps>\d+)"
    r"_b(?P<block_x>\d+)x(?P<block_y>\d+)x(?P<block_z>\d+)"
    r"_(?P<cell_config>[^_]+)"
    r"_(?P<layout>[^_]+)"
    r"_(?P<executor>[^_]+)"
    r"_(?P<ordering>[^_]+)"
    r"_t(?P<threads>\d+)$"
)


APRIL_STDOUT_PATTERNS = {
    "steps_processed": r"Steps processed:\s+([0-9]+)",
    "particles_processed": r"Particles processed:\s+([0-9]+)",
    "wall_time_total_s": r"Wall time \(total\):\s+([0-9.eE+-]+)\s+s",
    "integration_time_s": r"Integration time:\s+([0-9.eE+-]+)\s+s",
    "throughput_it_s": r"Throughput:\s+([0-9.eE+-]+)\s+it/s",
    "performance_mups": r"Performance:\s+([0-9.eE+-]+)\s+MUPS",
    "avg_step_time_s": r"Avg step time:\s+([0-9.eE+-]+)\s+s",
    "median_step_time_s": r"Median step time:\s+([0-9.eE+-]+)\s+s",
    "min_step_time_s": r"Min step time:\s+([0-9.eE+-]+)\s+s",
    "max_step_time_s": r"Max step time:\s+([0-9.eE+-]+)\s+s",
    "stddev_step_time_s": r"Std Deviation:\s+([0-9.eE+-]+)\s+s",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("./results"),
        help="Path to benchmark results directory. Default: ./results",
    )
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        default=Path("./analysis"),
        help="Output directory for CSV files. Default: ./analysis",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def parse_colon_or_equals_file(path: Path) -> dict[str, str]:
    """
    Parses simple metadata files such as run_info.txt.

    Supports:
      Key: value
      key=value
    """
    data: dict[str, str] = {}

    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if "=" in line and not line.startswith("Command:"):
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
        elif ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()

    return data


def parse_april_stdout(path: Path) -> dict[str, Any]:
    text = read_text(path)
    data: dict[str, Any] = {}

    for key, pattern in APRIL_STDOUT_PATTERNS.items():
        match = re.search(pattern, text)
        if not match:
            data[key] = ""
            continue

        value = match.group(1)
        if key in {"steps_processed", "particles_processed"}:
            data[key] = int(value)
        else:
            data[key] = float(value)

    return data


def maybe_int(value: str | None) -> int | str:
    if value is None or value == "":
        return ""
    try:
        return int(value)
    except ValueError:
        return value


def maybe_float(value: str | None) -> float | str:
    if value is None or value == "":
        return ""
    try:
        return float(value)
    except ValueError:
        return value


def parse_argon_scenario(scenario: str) -> dict[str, Any]:
    match = ARGON_SCENARIO_RE.match(scenario)
    if not match:
        return {}

    out: dict[str, Any] = match.groupdict()

    for key in ["n_dim", "particles", "steps", "block_x", "block_y", "block_z", "threads"]:
        out[key] = int(out[key])

    out["rho"] = float(out["rho"])
    out["dt"] = float(out["dt"])

    return out


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarize_numeric(
    rows: list[dict[str, Any]],
    group_keys: list[str],
    value_key: str,
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[float]] = defaultdict(list)

    for row in rows:
        value = row.get(value_key)
        if value == "" or value is None:
            continue
        groups[tuple(row.get(key, "") for key in group_keys)].append(float(value))

    summary_rows: list[dict[str, Any]] = []

    for group, values in sorted(groups.items()):
        item = {key: value for key, value in zip(group_keys, group)}
        item["n_reps"] = len(values)
        item[f"{value_key}_mean"] = statistics.mean(values)
        item[f"{value_key}_median"] = statistics.median(values)
        item[f"{value_key}_min"] = min(values)
        item[f"{value_key}_max"] = max(values)
        item[f"{value_key}_stddev"] = statistics.stdev(values) if len(values) > 1 else 0.0
        summary_rows.append(item)

    return summary_rows


def extract_april_argon(results_dir: Path) -> list[dict[str, Any]]:
    april_root = results_dir / "april"
    rows: list[dict[str, Any]] = []

    for stdout_path in sorted(april_root.glob("*/argon_block/*/*/stdout.log")):
        run_dir = stdout_path.parent
        scenario_dir = run_dir.parent
        benchmark_dir = scenario_dir.parent
        config_dir = benchmark_dir.parent

        config = config_dir.name
        benchmark = benchmark_dir.name
        scenario = scenario_dir.name
        run_id = run_dir.name

        scenario_data = parse_argon_scenario(scenario)
        stdout_data = parse_april_stdout(stdout_path)
        run_info = parse_colon_or_equals_file(run_dir / "run_info.txt")

        row: dict[str, Any] = {
            "engine": "april",
            "config": config,
            "benchmark": benchmark,
            "scenario": scenario,
            "run_id": run_id,
            "run_date": run_info.get("Run Date", ""),
            "hostname": run_info.get("Hostname", ""),
            "exit_status": maybe_int(run_info.get("Exit Status", "")),
            "wall_time_process_s": maybe_float(run_info.get("Wall Time Seconds", "")),
            "result_dir": str(run_dir),
        }

        row.update(scenario_data)
        row.update(stdout_data)

        # Validate/derive MUPS if stdout did not contain the rounded Performance line.
        if row.get("performance_mups", "") == "":
            particles_processed = row.get("particles_processed", "")
            integration_time_s = row.get("integration_time_s", "")
            if particles_processed != "" and integration_time_s not in ("", 0):
                row["performance_mups"] = float(particles_processed) / float(integration_time_s) / 1e6

        rows.append(row)

    return rows


def split_google_benchmark_name(run_name: str) -> dict[str, Any]:
    """
    Extracts useful dimensions from Google Benchmark run_name.

    Examples:
      BM_April_DirectSum<Layout::AoS, VectorPolicy::Scalar>/16/500/...
      BM_Baseline_Handcoded_SoA_Rotate_SIMD/16/500/...
    """
    parts = run_name.split("/")
    kernel = parts[0]
    args = [p for p in parts[1:] if not p.startswith("min_time") and not p.startswith("min_warmup_time")]

    out: dict[str, Any] = {
        "kernel": kernel,
        "benchmark_args": "/".join(args),
        "arg0": args[0] if len(args) > 0 else "",
        "arg1": args[1] if len(args) > 1 else "",
        "arg2": args[2] if len(args) > 2 else "",
        "implementation": "",
        "layout": "",
        "vector_policy": "",
        "baseline_variant": "",
    }

    if kernel.startswith("BM_April_"):
        out["implementation"] = "April"

        layout_match = re.search(r"Layout::([^,\>]+(?:<[^>]*>)?)", kernel)
        vector_match = re.search(r"VectorPolicy::([^,\>]+)", kernel)

        if layout_match:
            out["layout"] = layout_match.group(1)
        if vector_match:
            out["vector_policy"] = vector_match.group(1)

    elif kernel.startswith("BM_Baseline_Handcoded_"):
        out["implementation"] = "Handcoded"
        out["baseline_variant"] = kernel.removeprefix("BM_Baseline_Handcoded_")

        variant = out["baseline_variant"]
        if variant.startswith("AoS"):
            out["layout"] = "AoS"
        elif variant.startswith("SoA"):
            out["layout"] = "SoA"

        if "SIMD" in variant:
            out["vector_policy"] = "SIMD"
        elif "Scalar" in variant:
            out["vector_policy"] = "Scalar"

    return out


def extract_april_vs_hardcoded(results_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    april_root = results_dir / "april"

    all_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    for json_path in sorted(april_root.glob("*/april_vs_hardcoded/*/*/april_vs_hardcoded.json")):
        run_dir = json_path.parent
        scenario_dir = run_dir.parent
        benchmark_dir = scenario_dir.parent
        config_dir = benchmark_dir.parent

        config = config_dir.name
        benchmark = benchmark_dir.name
        scenario = scenario_dir.name
        run_id = run_dir.name

        with json_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        context = payload.get("context", {})
        benchmarks = payload.get("benchmarks", [])

        for b in benchmarks:
            run_name = b.get("run_name", b.get("name", ""))
            parsed_name = split_google_benchmark_name(run_name)

            row: dict[str, Any] = {
                "engine": "april",
                "config": config,
                "benchmark": benchmark,
                "scenario": scenario,
                "run_id": run_id,
                "date": context.get("date", ""),
                "hostname": context.get("host_name", ""),
                "cpu_scaling_enabled": context.get("cpu_scaling_enabled", ""),
                "name": b.get("name", ""),
                "run_name": run_name,
                "run_type": b.get("run_type", ""),
                "aggregate_name": b.get("aggregate_name", ""),
                "repetition_index": b.get("repetition_index", ""),
                "repetitions": b.get("repetitions", ""),
                "threads": b.get("threads", ""),
                "iterations": b.get("iterations", ""),
                "real_time_ms": b.get("real_time", ""),
                "cpu_time_ms": b.get("cpu_time", ""),
                "time_unit": b.get("time_unit", ""),
                "items_per_second": b.get("items_per_second", ""),
                "ns_per_interaction": b.get("ns/interaction", ""),
                "json_path": str(json_path),
            }

            row.update(parsed_name)
            all_rows.append(row)

            if row["run_type"] == "aggregate" and row["aggregate_name"] == "mean":
                summary_rows.append(row)

    return all_rows, summary_rows


def main() -> None:
    args = parse_args()

    results_dir: Path = args.results_dir
    analysis_dir: Path = args.analysis_dir
    analysis_dir.mkdir(parents=True, exist_ok=True)

    argon_rows = extract_april_argon(results_dir)

    argon_fields = [
        "engine",
        "config",
        "benchmark",
        "scaling",
        "scenario",
        "run_id",
        "run_date",
        "hostname",
        "n_dim",
        "particles",
        "rho",
        "dt",
        "steps",
        "block_x",
        "block_y",
        "block_z",
        "cell_config",
        "layout",
        "executor",
        "ordering",
        "threads",
        "steps_processed",
        "particles_processed",
        "wall_time_total_s",
        "integration_time_s",
        "throughput_it_s",
        "performance_mups",
        "avg_step_time_s",
        "median_step_time_s",
        "min_step_time_s",
        "max_step_time_s",
        "stddev_step_time_s",
        "wall_time_process_s",
        "exit_status",
        "result_dir",
    ]

    write_csv(
        analysis_dir / "april_argon_block_runs.csv",
        argon_rows,
        argon_fields,
    )

    argon_summary = summarize_numeric(
        argon_rows,
        group_keys=[
            "engine",
            "config",
            "benchmark",
            "scaling",
            "n_dim",
            "particles",
            "rho",
            "dt",
            "steps",
            "block_x",
            "block_y",
            "block_z",
            "cell_config",
            "layout",
            "executor",
            "ordering",
            "threads",
        ],
        value_key="performance_mups",
    )

    argon_summary_fields = [
        "engine",
        "config",
        "benchmark",
        "scaling",
        "n_dim",
        "particles",
        "rho",
        "dt",
        "steps",
        "block_x",
        "block_y",
        "block_z",
        "cell_config",
        "layout",
        "executor",
        "ordering",
        "threads",
        "n_reps",
        "performance_mups_mean",
        "performance_mups_median",
        "performance_mups_min",
        "performance_mups_max",
        "performance_mups_stddev",
    ]

    write_csv(
        analysis_dir / "april_argon_block_summary.csv",
        argon_summary,
        argon_summary_fields,
    )

    hardcoded_rows, hardcoded_summary_rows = extract_april_vs_hardcoded(results_dir)

    hardcoded_fields = [
        "engine",
        "config",
        "benchmark",
        "scenario",
        "run_id",
        "date",
        "hostname",
        "cpu_scaling_enabled",
        "implementation",
        "layout",
        "vector_policy",
        "baseline_variant",
        "kernel",
        "benchmark_args",
        "arg0",
        "arg1",
        "arg2",
        "name",
        "run_name",
        "run_type",
        "aggregate_name",
        "repetition_index",
        "repetitions",
        "threads",
        "iterations",
        "real_time_ms",
        "cpu_time_ms",
        "time_unit",
        "items_per_second",
        "ns_per_interaction",
        "json_path",
    ]

    write_csv(
        analysis_dir / "april_vs_hardcoded_runs.csv",
        hardcoded_rows,
        hardcoded_fields,
    )

    write_csv(
        analysis_dir / "april_vs_hardcoded_summary.csv",
        hardcoded_summary_rows,
        hardcoded_fields,
    )

    print(f"Wrote {len(argon_rows)} APRIL argon run rows")
    print(f"Wrote {len(argon_summary)} APRIL argon summary rows")
    print(f"Wrote {len(hardcoded_rows)} APRIL-vs-hardcoded benchmark rows")
    print(f"Wrote {len(hardcoded_summary_rows)} APRIL-vs-hardcoded mean rows")
    print(f"CSV output directory: {analysis_dir}")


if __name__ == "__main__":
    main()