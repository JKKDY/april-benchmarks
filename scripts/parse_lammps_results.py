#!/usr/bin/env python3
"""
Parse LAMMPS benchmark results into flat tables.

Expected result layout:
  results/lammps/<config>/<benchmark>/<scenario>/<run_id>/

Primary inputs per run:
  - derived_metrics.txt
  - configuration.log

Outputs:
  - lammps_force_kernel.csv
  - lammps_scaling.csv
  - lammps_all_runs.csv
"""

from __future__ import annotations

import argparse
import csv
import shlex
from pathlib import Path
from typing import Dict, Iterable, List


NUMERIC_KEYS = {
    "n_dim",
    "atoms",
    "rho",
    "steps",
    "dt",
    "ranks",
    "threads",
    "loop_time_s",
    "timesteps_per_second",
    "matom_step_per_second",
    "cpu_use_percent",
    "pair_time_s",
    "neigh_time_s",
    "comm_time_s",
    "modify_time_s",
    "total_neighbors",
    "neighbors_per_step",
    "neighbor_list_builds",
    "ns_per_interaction",
    "interactions_per_second",
    "wall_time_s",
}

PATH_KEYS = {
    "result_dir",
    "datafile",
    "input_file",
    "lammps_bin",
}

TEXT_PATH_PREFIX_KEYS = {
    "command",
}


def parse_kv_file(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def maybe_float(value: str):
    try:
        if value.lower() in {"unknown", "unset", ""}:
            return value
        if any(ch in value for ch in ".eE"):
            return float(value)
        return int(value)
    except Exception:
        return value


def infer_kind(benchmark: str) -> str:
    if benchmark == "force_kernel_bench":
        return "force_kernel"
    if benchmark == "argon_block":
        return "scaling"
    return "other"


def relativize_path_string(value: str, root: Path) -> str:
    if not value:
        return value
    p = Path(value)
    if not p.is_absolute():
        return value
    try:
        return str(p.resolve().relative_to(root))
    except Exception:
        return value


def relativize_command(command: str, root: Path) -> str:
    if not command:
        return command
    try:
        parts = shlex.split(command)
    except Exception:
        return command

    out: List[str] = []
    for part in parts:
        p = Path(part)
        if p.is_absolute():
            try:
                part = str(p.resolve().relative_to(root))
            except Exception:
                pass
        out.append(shlex.quote(part))
    return " ".join(out)


def normalize_record(record: Dict[str, str], root: Path) -> Dict[str, object]:
    out: Dict[str, object] = {}
    for k, v in record.items():
        if k in NUMERIC_KEYS:
            out[k] = maybe_float(v)
        elif k in PATH_KEYS:
            out[k] = relativize_path_string(v, root)
        elif k in TEXT_PATH_PREFIX_KEYS:
            out[k] = relativize_command(v, root)
        else:
            out[k] = v
    return out


def read_run(result_dir: Path, root: Path) -> Dict[str, object] | None:
    metrics_path = result_dir / "derived_metrics.txt"
    config_path = result_dir / "configuration.log"

    if not metrics_path.exists() and not config_path.exists():
        return None

    config = parse_kv_file(config_path)
    metrics = parse_kv_file(metrics_path)

    merged: Dict[str, str] = {}
    merged.update(config)
    merged.update(metrics)

    parts = result_dir.parts
    if "results" in parts and "lammps" in parts:
        idx = parts.index("lammps")
        tail = parts[idx + 1 :]
        if len(tail) >= 4:
            merged.setdefault("config", tail[0])
            merged.setdefault("benchmark", tail[1])
            merged.setdefault("scenario", tail[2])
            merged.setdefault("run_id", tail[3])

    merged["engine"] = "lammps"
    merged["result_dir"] = str(result_dir)
    merged["kind"] = infer_kind(str(merged.get("benchmark", "")))

    return normalize_record(merged, root)


def discover_runs(results_root: Path, root: Path) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []

    for path in results_root.rglob("derived_metrics.txt"):
        run_dir = path.parent
        row = read_run(run_dir, root)
        if row is not None:
            rows.append(row)

    seen_dirs = {Path(root / str(r["result_dir"])) if not str(r["result_dir"]).startswith("/") else Path(r["result_dir"]) for r in rows}
    for path in results_root.rglob("configuration.log"):
        run_dir = path.parent
        if run_dir in seen_dirs:
            continue
        row = read_run(run_dir, root)
        if row is not None:
            rows.append(row)

    rows.sort(
        key=lambda r: (
            str(r.get("config", "")),
            str(r.get("benchmark", "")),
            str(r.get("scenario", "")),
            str(r.get("run_id", "")),
        )
    )
    return rows


def union_fieldnames(rows: Iterable[Dict[str, object]]) -> List[str]:
    preferred = [
        "engine",
        "kind",
        "config",
        "benchmark",
        "scenario",
        "run_id",
        "n_dim",
        "atoms",
        "rho",
        "steps",
        "dt",
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
        "modify_time_s",
        "total_neighbors",
        "neighbors_per_step",
        "neighbor_list_builds",
        "ns_per_interaction",
        "interactions_per_second",
        "wall_time_s",
        "datafile",
        "input_file",
        "lammps_bin",
        "command",
        "result_dir",
    ]
    seen = set()
    for row in rows:
        seen.update(row.keys())

    ordered = [f for f in preferred if f in seen]
    remaining = sorted(seen - set(ordered))
    return ordered + remaining


def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = union_fieldnames(rows)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("results/lammps"),
        help="Root of the LAMMPS results tree.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("analysis/lammps"),
        help="Output directory for the generated CSV tables.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("."),
        help="Repository root used to relativize paths.",
    )
    args = parser.parse_args()

    root = args.project_root.resolve()
    results_root = (root / args.results_root).resolve() if not args.results_root.is_absolute() else args.results_root.resolve()
    out_dir = (root / args.out_dir).resolve() if not args.out_dir.is_absolute() else args.out_dir.resolve()

    if not results_root.exists():
        raise SystemExit(f"Results root does not exist: {results_root}")

    all_rows = discover_runs(results_root, root)
    if not all_rows:
        raise SystemExit(f"No LAMMPS runs found under: {results_root}")

    force_rows = [r for r in all_rows if r.get("kind") == "force_kernel"]
    scaling_rows = [r for r in all_rows if r.get("kind") == "scaling"]

    write_csv(out_dir / "lammps_all_runs.csv", all_rows)
    if force_rows:
        write_csv(out_dir / "lammps_force_kernel.csv", force_rows)
    if scaling_rows:
        write_csv(out_dir / "lammps_scaling.csv", scaling_rows)

    print(f"Wrote {len(all_rows)} total runs to {out_dir / 'lammps_all_runs.csv'}")
    if force_rows:
        print(f"Wrote {len(force_rows)} force-kernel runs to {out_dir / 'lammps_force_kernel.csv'}")
    if scaling_rows:
        print(f"Wrote {len(scaling_rows)} scaling runs to {out_dir / 'lammps_scaling.csv'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())