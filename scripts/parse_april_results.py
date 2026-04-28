#!/usr/bin/env python3
"""
Parse April benchmark results into flat tables.

Expected result layout:
  results/april/<config>/<benchmark>/<scenario>/<run_id>/

Outputs:
  - april_microbench.csv
  - april_argon_scaling.csv
  - april_all_runs.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shlex
from pathlib import Path
from typing import Dict, Iterable, List, Optional


NUMERIC_KEYS = {
    "threads",
    "particles",
    "particles_processed",
    "steps",
    "steps_processed",
    "n",
    "rho",
    "dt",
    "bx",
    "by",
    "bz",
    "wall_time_seconds",
    "integration_time_s",
    "throughput_it_per_s",
    "performance_mups",
    "avg_step_time_s",
    "median_step_time_s",
    "min_step_time_s",
    "max_step_time_s",
    "std_deviation_s",
}


def parse_colon_file(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def maybe_number(value: str):
    try:
        if value.lower() in {"unknown", "unset", ""}:
            return value
        if any(ch in value for ch in ".eE"):
            return float(value)
        return int(value)
    except Exception:
        return value


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


def normalize_record(record: Dict[str, object], root: Path) -> Dict[str, object]:
    out: Dict[str, object] = {}
    for k, v in record.items():
        if isinstance(v, str) and k in NUMERIC_KEYS:
            out[k] = maybe_number(v)
        elif isinstance(v, str) and k in {"result_dir", "build_dir", "stdout_file", "stderr_file", "json_file"}:
            out[k] = relativize_path_string(v, root)
        elif isinstance(v, str) and k in {"command"}:
            out[k] = relativize_command(v, root)
        else:
            out[k] = v
    return out


def parse_command(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def parse_wall_time_from_run_info(run_info: Dict[str, str]) -> Optional[float]:
    value = run_info.get("Wall Time Seconds")
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


_SCALING_RE = re.compile(
    r"^(?P<scaling>strong|weak)"
    r"_n(?P<n>\d+)"
    r"_p(?P<particles>\d+)"
    r"_rho(?P<rho>[-+0-9.eE]+)"
    r"_dt(?P<dt>[-+0-9.eE]+)"
    r"_steps(?P<steps>\d+)"
    r"_b(?P<bx>\d+)x(?P<by>\d+)x(?P<bz>\d+)"
    r"_(?P<schedule>[^_]+)"
    r"_(?P<layout>[^_]+)"
    r"_(?P<executor>[^_]+)"
    r"_(?P<ordering>[^_]+)"
    r"_t(?P<threads>\d+)$"
)


def parse_argon_scenario(scenario: str) -> Dict[str, object]:
    m = _SCALING_RE.match(scenario)
    if not m:
        return {}
    out: Dict[str, object] = m.groupdict()
    for k in ["n", "particles", "steps", "bx", "by", "bz", "threads"]:
        out[k] = int(out[k])  # type: ignore[index]
    for k in ["rho", "dt"]:
        out[k] = float(out[k])  # type: ignore[index]
    return out


def parse_april_argon_stdout(path: Path) -> Dict[str, object]:
    out: Dict[str, object] = {}
    if not path.exists():
        return out

    text = path.read_text(encoding="utf-8", errors="replace")

    patterns = {
        "steps_processed": r"Steps processed:\s*([0-9]+)",
        "particles_processed": r"Particles processed:\s*([0-9]+)",
        "wall_time_seconds": r"Wall time \(total\):\s*([0-9.eE+-]+)\s*s",
        "integration_time_s": r"Integration time:\s*([0-9.eE+-]+)\s*s",
        "throughput_it_per_s": r"Throughput:\s*([0-9.eE+-]+)\s*it/s",
        "performance_mups": r"Performance:\s*([0-9.eE+-]+)\s*MUPS",
        "avg_step_time_s": r"Avg step time:\s*([0-9.eE+-]+)\s*s",
        "median_step_time_s": r"Median step time:\s*([0-9.eE+-]+)\s*s",
        "min_step_time_s": r"Min step time:\s*([0-9.eE+-]+)\s*s",
        "max_step_time_s": r"Max step time:\s*([0-9.eE+-]+)\s*s",
        "std_deviation_s": r"Std Deviation:\s*([0-9.eE+-]+)\s*s",
    }

    for key, pattern in patterns.items():
        m = re.search(pattern, text)
        if m:
            out[key] = maybe_number(m.group(1))

    return out


def find_microbench_jsons(run_dir: Path, benchmark: str) -> List[Path]:
    candidates = []
    preferred = run_dir / f"{benchmark}.json"
    if preferred.exists():
        candidates.append(preferred)
    for p in sorted(run_dir.glob("*.json")):
        if p not in candidates:
            candidates.append(p)
    return candidates


def read_common_run_metadata(run_dir: Path, root: Path) -> Dict[str, object]:
    parts = run_dir.parts
    meta: Dict[str, object] = {}
    if "results" in parts and "april" in parts:
        idx = parts.index("april")
        tail = parts[idx + 1 :]
        if len(tail) >= 4:
            meta["config"] = tail[0]
            meta["benchmark"] = tail[1]
            meta["scenario"] = tail[2]
            meta["run_id"] = tail[3]

    run_info = parse_colon_file(run_dir / "run_info.txt")
    command = parse_command(run_dir / "command.txt")

    if "Config" in run_info:
        meta["config"] = run_info["Config"]
    if "Benchmark" in run_info:
        meta["benchmark"] = run_info["Benchmark"]
    if "Scenario" in run_info:
        meta["scenario"] = run_info["Scenario"]
    if "Run ID" in run_info:
        meta["run_id"] = run_info["Run ID"]
    if "Hostname" in run_info:
        meta["hostname"] = run_info["Hostname"]
    if "Run Date" in run_info:
        meta["run_date"] = run_info["Run Date"]
    if "Build Dir" in run_info:
        meta["build_dir"] = run_info["Build Dir"]

    wall_time = parse_wall_time_from_run_info(run_info)
    if wall_time is not None:
        meta["wall_time_seconds"] = wall_time

    meta["engine"] = "april"
    meta["result_dir"] = str(run_dir)
    meta["command"] = command
    meta["stdout_file"] = str(run_dir / "stdout.log")
    meta["stderr_file"] = str(run_dir / "stderr.log")

    return normalize_record(meta, root)


def parse_microbench_run(run_dir: Path, root: Path) -> List[Dict[str, object]]:
    common = read_common_run_metadata(run_dir, root)
    benchmark = str(common.get("benchmark", ""))

    rows: List[Dict[str, object]] = []
    for json_path in find_microbench_jsons(run_dir, benchmark):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        context = payload.get("context", {})
        benchmarks = payload.get("benchmarks", [])
        for bench in benchmarks:
            row = dict(common)
            row["kind"] = "microbench"
            row["json_file"] = relativize_path_string(str(json_path), root)

            for k, v in context.items():
                row[f"context_{k}"] = v

            for k, v in bench.items():
                if k == "name":
                    row["benchmark_case"] = v
                else:
                    row[k] = v

            rows.append(row)

    return rows


def parse_argon_run(run_dir: Path, root: Path) -> Dict[str, object]:
    common = read_common_run_metadata(run_dir, root)
    common["kind"] = "argon_scaling"

    scenario = str(common.get("scenario", ""))
    common.update(parse_argon_scenario(scenario))
    common.update(parse_april_argon_stdout(run_dir / "stdout.log"))

    return normalize_record(common, root)


def discover_runs(results_root: Path) -> List[Path]:
    run_dirs: List[Path] = []
    seen = set()

    for p in results_root.rglob("run_info.txt"):
        run_dir = p.parent
        if run_dir not in seen:
            seen.add(run_dir)
            run_dirs.append(run_dir)

    for p in results_root.rglob("stdout.log"):
        run_dir = p.parent
        if run_dir not in seen:
            seen.add(run_dir)
            run_dirs.append(run_dir)

    run_dirs.sort()
    return run_dirs


def union_fieldnames(rows: Iterable[Dict[str, object]]) -> List[str]:
    preferred = [
        "engine",
        "kind",
        "config",
        "benchmark",
        "benchmark_case",
        "scenario",
        "run_id",
        "scaling",
        "n",
        "particles",
        "particles_processed",
        "rho",
        "dt",
        "steps",
        "steps_processed",
        "bx",
        "by",
        "bz",
        "schedule",
        "layout",
        "executor",
        "ordering",
        "threads",
        "real_time",
        "cpu_time",
        "time_unit",
        "iterations",
        "wall_time_seconds",
        "integration_time_s",
        "throughput_it_per_s",
        "performance_mups",
        "avg_step_time_s",
        "median_step_time_s",
        "min_step_time_s",
        "max_step_time_s",
        "std_deviation_s",
        "hostname",
        "run_date",
        "json_file",
        "build_dir",
        "stdout_file",
        "stderr_file",
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
        default=Path("results/april"),
        help="Root of the April results tree.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("analysis/april"),
        help="Output directory for generated CSV tables.",
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

    run_dirs = discover_runs(results_root)
    if not run_dirs:
        raise SystemExit(f"No April runs found under: {results_root}")

    micro_rows: List[Dict[str, object]] = []
    argon_rows: List[Dict[str, object]] = []
    all_rows: List[Dict[str, object]] = []

    for run_dir in run_dirs:
        common = read_common_run_metadata(run_dir, root)
        benchmark = str(common.get("benchmark", ""))

        if benchmark in {"force_kernel_bench", "april_vs_hardcoded"}:
            rows = parse_microbench_run(run_dir, root)
            micro_rows.extend(rows)
            all_rows.extend(rows)
        elif benchmark == "argon_block":
            row = parse_argon_run(run_dir, root)
            argon_rows.append(row)
            all_rows.append(row)
        else:
            row = dict(common)
            row["kind"] = "other"
            all_rows.append(row)

    if micro_rows:
        write_csv(out_dir / "april_microbench.csv", micro_rows)
    if argon_rows:
        write_csv(out_dir / "april_argon_scaling.csv", argon_rows)
    write_csv(out_dir / "april_all_runs.csv", all_rows)

    if micro_rows:
        print(f"Wrote {len(micro_rows)} microbench rows to {out_dir / 'april_microbench.csv'}")
    if argon_rows:
        print(f"Wrote {len(argon_rows)} argon rows to {out_dir / 'april_argon_scaling.csv'}")
    print(f"Wrote {len(all_rows)} total rows to {out_dir / 'april_all_runs.csv'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())