#!/usr/bin/env python3
"""
Extract LAMMPS argon_block benchmark results into CSV files.

Expected layout:

  ./results/lammps/openmp-native/argon_block/...
  ./results/lammps/intel-native/argon_block/...

Outputs:

  ./analysis/lammps_argon_block_runs.csv
  ./analysis/lammps_argon_block_summary.csv

Paper-relevant metric:
  - matom_step_per_second from derived_metrics.txt

This is directly comparable to APRIL MUPS:
  atoms * steps / loop_time_s / 1e6
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


LAMMPS_ARGON_SCENARIO_RE = re.compile(
    r"^(?P<scaling>strong|weak)"
    r"_n(?P<n_dim>\d+)"
    r"_p(?P<atoms>\d+)"
    r"_rho(?P<rho>[0-9.]+)"
    r"_dt(?P<dt>[0-9.]+)"
    r"_steps(?P<steps>\d+)"
    r"_threads_r(?P<ranks>\d+)"
    r"_t(?P<threads>\d+)"
    r"_bind(?P<bind>[A-Za-z0-9_-]+)$"
)


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


def parse_key_value_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}

    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue

        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()

    return data


def parse_run_info(path: Path) -> dict[str, str]:
    """
    Parses run_info.txt, which mostly uses:
      Key: value
    """
    data: dict[str, str] = {}

    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()

    return data


def maybe_int(value: Any) -> int | str:
    if value is None or value == "":
        return ""
    try:
        return int(value)
    except ValueError:
        return str(value)


def maybe_float(value: Any) -> float | str:
    if value is None or value == "":
        return ""
    try:
        return float(value)
    except ValueError:
        return str(value)


def parse_percent(value: Any) -> float | str:
    if value is None or value == "":
        return ""

    text = str(value).strip()
    if text.endswith("%"):
        text = text[:-1]

    return maybe_float(text)


def normalize_unknown_float(value: Any) -> float | str:
    if value is None or value == "":
        return ""

    text = str(value).strip()
    if text.lower() in {"unknown", "nan", "none"}:
        return ""

    return maybe_float(text)


def parse_lammps_argon_scenario(scenario: str) -> dict[str, Any]:
    match = LAMMPS_ARGON_SCENARIO_RE.match(scenario)
    if not match:
        return {}

    out: dict[str, Any] = match.groupdict()

    for key in ["n_dim", "atoms", "steps", "ranks", "threads"]:
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


def extract_lammps_argon(results_dir: Path) -> list[dict[str, Any]]:
    lammps_root = results_dir / "lammps"
    rows: list[dict[str, Any]] = []

    for metrics_path in sorted(lammps_root.glob("*/argon_block/*/*/derived_metrics.txt")):
        run_dir = metrics_path.parent
        scenario_dir = run_dir.parent
        benchmark_dir = scenario_dir.parent
        config_dir = benchmark_dir.parent

        config = config_dir.name
        benchmark = benchmark_dir.name
        scenario = scenario_dir.name
        run_id = run_dir.name

        metrics = parse_key_value_file(metrics_path)
        run_info = parse_run_info(run_dir / "run_info.txt")
        scenario_data = parse_lammps_argon_scenario(scenario)

        row: dict[str, Any] = {
            "engine": "lammps",
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

        # Scenario directory is usually reliable. The derived metrics file also
        # repeats these values, so use it as a fallback below.
        row.update(scenario_data)

        row["scaling"] = row.get("scaling", "")
        row["n_dim"] = row.get("n_dim", maybe_int(metrics.get("n_dim", "")))
        row["atoms"] = row.get("atoms", maybe_int(metrics.get("atoms", "")))
        row["rho"] = row.get("rho", maybe_float(metrics.get("rho", "")))
        row["dt"] = row.get("dt", maybe_float(metrics.get("dt", "")))
        row["steps"] = row.get("steps", maybe_int(metrics.get("steps", "")))
        row["ranks"] = row.get("ranks", maybe_int(metrics.get("ranks", "")))
        row["threads"] = row.get("threads", maybe_int(metrics.get("threads", "")))
        row["bind"] = row.get("bind", metrics.get("bind", ""))

        # Paper-relevant throughput metric.
        row["matom_step_per_second"] = normalize_unknown_float(
            metrics.get("matom_step_per_second", "")
        )

        # Additional useful diagnostics.
        row["loop_time_s"] = normalize_unknown_float(metrics.get("loop_time_s", ""))
        row["timesteps_per_second"] = normalize_unknown_float(
            metrics.get("timesteps_per_second", "")
        )
        row["cpu_use_percent"] = parse_percent(metrics.get("cpu_use_percent", ""))
        row["pair_time_s"] = normalize_unknown_float(metrics.get("pair_time_s", ""))
        row["neigh_time_s"] = normalize_unknown_float(metrics.get("neigh_time_s", ""))
        row["comm_time_s"] = normalize_unknown_float(metrics.get("comm_time_s", ""))
        row["output_time_s"] = normalize_unknown_float(metrics.get("output_time_s", ""))
        row["modify_time_s"] = normalize_unknown_float(metrics.get("modify_time_s", ""))
        row["other_time_s"] = normalize_unknown_float(metrics.get("other_time_s", ""))
        row["total_neighbors"] = maybe_int(metrics.get("total_neighbors", ""))
        row["neighbor_list_builds"] = maybe_int(metrics.get("neighbor_list_builds", ""))
        row["wall_time_s"] = normalize_unknown_float(metrics.get("wall_time_s", ""))

        # Sanity fallback: derive Matom-step/s from loop time if the parser did
        # not find the explicit LAMMPS performance value.
        if row["matom_step_per_second"] == "":
            atoms = row.get("atoms", "")
            steps = row.get("steps", "")
            loop_time_s = row.get("loop_time_s", "")

            if atoms != "" and steps != "" and loop_time_s not in ("", 0):
                row["matom_step_per_second"] = (
                    float(atoms) * float(steps) / float(loop_time_s) / 1e6
                )

        rows.append(row)

    return rows


def main() -> None:
    args = parse_args()

    results_dir: Path = args.results_dir
    analysis_dir: Path = args.analysis_dir
    analysis_dir.mkdir(parents=True, exist_ok=True)

    rows = extract_lammps_argon(results_dir)

    run_fields = [
        "engine",
        "config",
        "benchmark",
        "scaling",
        "scenario",
        "run_id",
        "run_date",
        "hostname",
        "n_dim",
        "atoms",
        "rho",
        "dt",
        "steps",
        "ranks",
        "threads",
        "bind",
        "loop_time_s",
        "timesteps_per_second",
        "matom_step_per_second",
        "cpu_use_percent",
        "pair_time_s",
        "neigh_time_s",
        "comm_time_s",
        "output_time_s",
        "modify_time_s",
        "other_time_s",
        "total_neighbors",
        "neighbor_list_builds",
        "wall_time_s",
        "wall_time_process_s",
        "exit_status",
        "result_dir",
    ]

    write_csv(
        analysis_dir / "lammps_argon_block_runs.csv",
        rows,
        run_fields,
    )

    summary_rows = summarize_numeric(
        rows,
        group_keys=[
            "engine",
            "config",
            "benchmark",
            "scaling",
            "n_dim",
            "atoms",
            "rho",
            "dt",
            "steps",
            "ranks",
            "threads",
            "bind",
        ],
        value_key="matom_step_per_second",
    )

    summary_fields = [
        "engine",
        "config",
        "benchmark",
        "scaling",
        "n_dim",
        "atoms",
        "rho",
        "dt",
        "steps",
        "ranks",
        "threads",
        "bind",
        "n_reps",
        "matom_step_per_second_mean",
        "matom_step_per_second_median",
        "matom_step_per_second_min",
        "matom_step_per_second_max",
        "matom_step_per_second_stddev",
    ]

    write_csv(
        analysis_dir / "lammps_argon_block_summary.csv",
        summary_rows,
        summary_fields,
    )

    print(f"Wrote {len(rows)} LAMMPS argon run rows")
    print(f"Wrote {len(summary_rows)} LAMMPS argon summary rows")
    print(f"CSV output directory: {analysis_dir}")


if __name__ == "__main__":
    main()