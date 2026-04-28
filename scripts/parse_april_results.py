#!/usr/bin/env python3
"""
Parse APRIL benchmark results into flat CSV tables.

Expected layout:
  results/april/<config>/<benchmark>/<scenario>/<run_id>/

Outputs:
  analysis/april/april_all_runs.csv
  analysis/april/april_microbench.csv
  analysis/april/april_argon_scaling.csv

The parser uses, when available:
  - Google Benchmark JSON files
  - stdout.log
  - stderr.log
  - run_info.txt
  - command.txt

Design:
  - JSON is the primary source for Google Benchmark microbenchmarks.
  - stdout.log is the primary source for APRIL argon_block simulation reports.
  - command.txt is preferred over scenario parsing for argon parameters.
  - scenario parsing is used as fallback and for scaling labels.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shlex
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


MICROBENCH_BENCHMARKS = {
    "force_kernel_bench",
    "april_vs_hardcoded",
}

ARGON_BENCHMARKS = {
    "argon_block",
}

PATH_KEYS = {
    "result_dir",
    "build_dir",
    "stdout_file",
    "stderr_file",
    "json_file",
    "executable",
}

NUMERIC_KEYS = {
    "threads",
    "ranks",
    "total_cores",
    "n",
    "particles",
    "particles_processed",
    "steps",
    "steps_processed",
    "rho",
    "dt",
    "bx",
    "by",
    "bz",
    "wall_time_seconds",
    "integration_time_s",
    "throughput_it_per_s",
    "performance_mups",
    "mups_computed",
    "atom_steps",
    "avg_step_time_s",
    "median_step_time_s",
    "min_step_time_s",
    "max_step_time_s",
    "std_deviation_s",
    "ns_per_interaction",
    "interactions_per_second",
    "items_per_second",
    "real_time",
    "cpu_time",
    "iterations",
    "repetitions",
    "repetition_index",
    "family_index",
    "per_family_instance_index",
    "context_num_cpus",
    "context_mhz_per_cpu",
    "context_cpu_scaling_enabled",
}

ARGON_COMMAND_LAYOUT = [
    "binary",
    "n",
    "rho",
    "dt",
    "threads",
    "steps",
    "bx",
    "by",
    "bz",
    "schedule",
    "layout",
    "executor",
    "ordering",
    "tag",
]


def maybe_number(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if stripped.lower() in {"", "unknown", "unset", "none", "nan"}:
        return stripped

    percent = False
    if stripped.endswith("%"):
        percent = True
        stripped = stripped[:-1]

    try:
        if any(ch in stripped for ch in ".eE+-"):
            parsed: Any = float(stripped)
        else:
            parsed = int(stripped)

        if percent:
            return float(parsed)

        return parsed
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

    normalized: List[str] = []
    for part in parts:
        p = Path(part)
        if p.is_absolute():
            try:
                part = str(p.resolve().relative_to(root))
            except Exception:
                pass
        normalized.append(shlex.quote(part))

    return " ".join(normalized)


def normalize_record(record: Dict[str, Any], root: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    for key, value in record.items():
        if isinstance(value, str) and key in NUMERIC_KEYS:
            out[key] = maybe_number(value)
        elif isinstance(value, str) and key in PATH_KEYS:
            out[key] = relativize_path_string(value, root)
        elif isinstance(value, str) and key == "command":
            out[key] = relativize_command(value, root)
        else:
            out[key] = value

    return out


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def parse_command(path: Path) -> str:
    return read_text(path).strip()


def parse_colon_file(path: Path) -> Dict[str, str]:
    """
    Parse simple 'Key: Value' files.

    This is intentionally simple. Repeated keys are overwritten by later values.
    For APRIL run_info.txt this is acceptable because the most useful build-info
    values appear later in the file.
    """
    data: Dict[str, str] = {}

    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue

        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()

    return data


def parse_run_info_text(path: Path) -> Dict[str, Any]:
    """
    Extract selected run/build metadata from APRIL run_info.txt.
    """
    text = read_text(path)
    flat = parse_colon_file(path)

    out: Dict[str, Any] = {}

    direct_map = {
        "Engine": "engine_from_run_info",
        "Config": "config",
        "Config Raw": "config_raw",
        "Benchmark": "benchmark",
        "Binary": "binary",
        "Scenario": "scenario",
        "Run ID": "run_id",
        "Run Date": "run_date",
        "Hostname": "hostname",
        "Build Dir": "build_dir",
        "Result Dir": "result_dir_from_run_info",
        "Wall Time Seconds": "wall_time_seconds",
        "Variant": "variant",
        "ISA Variant": "isa_variant",
        "Build Variant": "build_variant",
        "Compiler Family": "compiler_family",
        "Auto-vectorization": "auto_vectorization",
        "CC": "cc",
        "CXX": "cxx",
        "Extra CXX Flags": "extra_cxx_flags",
        "CMAKE_BUILD_TYPE": "cmake_build_type",
        "APRIL_ENABLE_OPENMP": "april_enable_openmp",
        "APRIL_ENABLE_XSIMD": "april_enable_xsimd",
        "APRIL_BENCH_ENABLE_EXPLICIT_SIMD_BASELINES": "april_bench_enable_explicit_simd_baselines",
        "April Commit": "april_commit",
        "April Branch": "april_branch",
        "Google Benchmark Commit": "googlebenchmark_commit",
        "xsimd Commit": "xsimd_commit",
        "Benchmark Repo Commit": "benchmark_repo_commit",
    }

    for source_key, dest_key in direct_map.items():
        if source_key in flat:
            out[dest_key] = flat[source_key]

    env_patterns = {
        "omp_num_threads": r"OMP_NUM_THREADS=([^\n]+)",
        "omp_places": r"OMP_PLACES=([^\n]+)",
        "omp_proc_bind": r"OMP_PROC_BIND=([^\n]+)",
        "omp_dynamic": r"OMP_DYNAMIC=([^\n]+)",
        "slurm_job_id": r"SLURM_JOB_ID=([^\n]+)",
        "slurm_cpus_per_task": r"SLURM_CPUS_PER_TASK=([^\n]+)",
    }

    for key, pattern in env_patterns.items():
        m = re.search(pattern, text)
        if m:
            out[key] = m.group(1).strip()

    return out


def parse_stderr(path: Path) -> Dict[str, Any]:
    """
    Parse useful Google Benchmark stderr context not always convenient in JSON.
    """
    text = read_text(path)
    out: Dict[str, Any] = {}

    if "CPU scaling is enabled" in text:
        out["stderr_cpu_scaling_warning"] = True

    m = re.search(r"Run on \((\d+) X ([0-9.]+) MHz CPU s\)", text)
    if m:
        out["stderr_num_cpus"] = int(m.group(1))
        out["stderr_mhz_per_cpu"] = float(m.group(2))

    m = re.search(r"Load Average:\s*([0-9.]+),\s*([0-9.]+),\s*([0-9.]+)", text)
    if m:
        out["stderr_load_avg_1m"] = float(m.group(1))
        out["stderr_load_avg_5m"] = float(m.group(2))
        out["stderr_load_avg_15m"] = float(m.group(3))

    return out


def infer_from_path(run_dir: Path) -> Dict[str, Any]:
    """
    Infer config/benchmark/scenario/run_id from:
      .../results/april/<config>/<benchmark>/<scenario>/<run_id>
    """
    parts = run_dir.parts
    out: Dict[str, Any] = {}

    if "april" not in parts:
        return out

    idx = parts.index("april")
    tail = parts[idx + 1 :]

    if len(tail) >= 4:
        out["config"] = tail[0]
        out["benchmark"] = tail[1]
        out["scenario"] = tail[2]
        out["run_id"] = tail[3]

    return out


def read_common_metadata(run_dir: Path, root: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    out.update(infer_from_path(run_dir))
    out.update(parse_run_info_text(run_dir / "run_info.txt"))
    out.update(parse_stderr(run_dir / "stderr.log"))

    command = parse_command(run_dir / "command.txt")

    out["engine"] = "april"
    out["result_dir"] = str(run_dir)
    out["command"] = command
    out["stdout_file"] = str(run_dir / "stdout.log")
    out["stderr_file"] = str(run_dir / "stderr.log")

    return normalize_record(out, root)


def parse_argon_command(command: str) -> Dict[str, Any]:
    """
    Parse APRIL argon command line:

      <bin>/argon_block n rho dt threads steps bx by bz schedule layout executor ordering tag

    This is preferred over scenario parsing because some schedule names contain underscores.
    """
    out: Dict[str, Any] = {}

    if not command:
        return out

    try:
        parts = shlex.split(command)
    except Exception:
        return out

    if len(parts) < 6:
        return out

    binary = Path(parts[0]).name
    if binary != "argon_block":
        return out

    values = parts[: len(ARGON_COMMAND_LAYOUT)]

    for key, value in zip(ARGON_COMMAND_LAYOUT, values):
        if key == "binary":
            continue
        out[key] = value

    int_keys = {"n", "threads", "steps", "bx", "by", "bz"}
    float_keys = {"rho", "dt"}

    for key in int_keys:
        if key in out:
            out[key] = int(out[key])

    for key in float_keys:
        if key in out:
            out[key] = float(out[key])

    if "threads" in out:
        out["total_cores"] = out["threads"]

    if "n" in out:
        n = int(out["n"])
        out.setdefault("particles", n * n * n)

    return out


_SCALING_PREFIX_RE = re.compile(r"^(?P<scaling>strong|weak)_")
_SCENARIO_CORE_RE = re.compile(
    r"_n(?P<n>\d+)"
    r"_p(?P<particles>\d+)"
    r"_rho(?P<rho>[-+0-9.eE]+)"
    r"_dt(?P<dt>[-+0-9.eE]+)"
    r"_steps(?P<steps>\d+)"
)


def parse_argon_scenario_fallback(scenario: str) -> Dict[str, Any]:
    """
    Fallback parser. It intentionally avoids parsing schedule/layout/executor from
    the tail because schedule names may contain underscores.
    """
    out: Dict[str, Any] = {}

    m = _SCALING_PREFIX_RE.search(scenario)
    if m:
        out["scaling"] = m.group("scaling")

    m = _SCENARIO_CORE_RE.search(scenario)
    if m:
        out.update(m.groupdict())
        out["n"] = int(out["n"])
        out["particles"] = int(out["particles"])
        out["rho"] = float(out["rho"])
        out["dt"] = float(out["dt"])
        out["steps"] = int(out["steps"])

    m = re.search(r"_b(?P<bx>\d+)x(?P<by>\d+)x(?P<bz>\d+)_", scenario)
    if m:
        out["bx"] = int(m.group("bx"))
        out["by"] = int(m.group("by"))
        out["bz"] = int(m.group("bz"))

    m = re.search(r"_t(?P<threads>\d+)$", scenario)
    if m:
        out["threads"] = int(m.group("threads"))
        out["total_cores"] = int(m.group("threads"))

    return out


def parse_april_argon_stdout(path: Path) -> Dict[str, Any]:
    """
    Parse APRIL benchmark report from stdout.log.
    """
    text = read_text(path)
    out: Dict[str, Any] = {}

    patterns = {
        "steps_processed": r"Steps processed:\s*([0-9]+)",
        "particles_processed": r"Particles processed:\s*([0-9]+)",
        "wall_time_total_s": r"Wall time \(total\):\s*([0-9.eE+-]+)\s*s",
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


def add_argon_derived_fields(row: Dict[str, Any]) -> None:
    particles = maybe_number(row.get("particles", ""))
    steps = maybe_number(row.get("steps", ""))
    particles_processed = maybe_number(row.get("particles_processed", ""))
    steps_processed = maybe_number(row.get("steps_processed", ""))
    integration_time = maybe_number(row.get("integration_time_s", ""))

    if isinstance(particles, int) and isinstance(steps, int):
        row["atom_steps"] = particles * steps

    if isinstance(particles_processed, int) and isinstance(integration_time, float) and integration_time > 0:
        row["mups_computed"] = particles_processed / integration_time / 1.0e6

    if isinstance(steps_processed, int) and isinstance(integration_time, float) and steps_processed > 0:
        row["avg_step_time_from_integration_s"] = integration_time / steps_processed

    if "threads" in row and "total_cores" not in row:
        row["total_cores"] = row["threads"]


def parse_argon_run(run_dir: Path, root: Path) -> Dict[str, Any]:
    row = read_common_metadata(run_dir, root)
    row["kind"] = "argon_scaling"

    scenario = str(row.get("scenario", ""))
    command = str(row.get("command", ""))

    # Fallback first, command second so command wins.
    row.update(parse_argon_scenario_fallback(scenario))
    row.update(parse_argon_command(command))
    row.update(parse_april_argon_stdout(run_dir / "stdout.log"))

    # Preserve scaling label from scenario even if command parsing won other fields.
    if "scaling" not in row:
        scaling = parse_argon_scenario_fallback(scenario).get("scaling")
        if scaling:
            row["scaling"] = scaling

    add_argon_derived_fields(row)

    return normalize_record(row, root)


def find_json_files(run_dir: Path, benchmark: str) -> List[Path]:
    files: List[Path] = []

    preferred = run_dir / f"{benchmark}.json"
    if preferred.exists():
        files.append(preferred)

    for p in sorted(run_dir.glob("*.json")):
        if p not in files:
            files.append(p)

    return files


def flatten_context(context: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    for key, value in context.items():
        if key == "caches":
            # Keep cache info compact but still available.
            out["context_caches_json"] = json.dumps(value, sort_keys=True)
        elif key == "load_avg" and isinstance(value, list):
            if len(value) > 0:
                out["context_load_avg_1m"] = value[0]
            if len(value) > 1:
                out["context_load_avg_5m"] = value[1]
            if len(value) > 2:
                out["context_load_avg_15m"] = value[2]
        else:
            out[f"context_{key}"] = value

    return out


def parse_microbench_name(name: str) -> Dict[str, Any]:
    """
    Extract lightweight labels from Google Benchmark case names.

    Examples:
      BM_April_DirectSum<Layout::AoS, VectorPolicy::Scalar>/16/500
      BM_Manual_TriangleSoA_ExplicitSIMD/4000/200
    """
    out: Dict[str, Any] = {}

    base = name.split("/", 1)[0]
    out["case_base"] = base

    if "/" in name:
        args = name.split("/")[1:]
        out["case_args"] = "/".join(args)
        if len(args) >= 1 and args[0].isdigit():
            out["case_arg0"] = int(args[0])
        if len(args) >= 2 and args[1].isdigit():
            out["case_arg1"] = int(args[1])

    m = re.search(r"Layout::([^,\s>]+)", name)
    if m:
        out["layout"] = m.group(1)

    m = re.search(r"VectorPolicy::([^,\s>]+)", name)
    if m:
        out["vector_policy"] = m.group(1)

    if "DirectSum" in name:
        out["container"] = "DirectSum"
    elif "LinkedCells" in name:
        out["container"] = "LinkedCells"
    elif "Manual" in name:
        out["container"] = "Manual"
    elif "Baseline" in name:
        out["container"] = "Baseline"

    if "FullIntegration" in name:
        out["workload"] = "full_integration"
    elif "UpdateForcesOnly" in name:
        out["workload"] = "update_forces_only"
    elif "DirectSum" in name:
        out["workload"] = "direct_sum"
    elif "Triangle" in name:
        out["workload"] = "triangle_loop"

    if "ExplicitSIMD" in name or "2D_SIMD" in name or "1D_SIMD" in name:
        out["implementation"] = "explicit_simd"
    elif "VectorPolicy::Auto" in name:
        out["implementation"] = "april_auto_simd"
    elif "VectorPolicy::Scalar" in name:
        out["implementation"] = "scalar"
    elif "Handcoded" in name or "Manual" in name:
        out["implementation"] = "manual"

    if name.startswith("BM_April"):
        out["case_group"] = "april"
    elif "Handcoded" in name:
        out["case_group"] = "handcoded"
    elif name.startswith("BM_Manual"):
        out["case_group"] = "manual"
    else:
        out["case_group"] = "other"

    return out


def add_microbench_derived_fields(row: Dict[str, Any]) -> None:
    if "ns/interaction" in row:
        row["ns_per_interaction"] = row["ns/interaction"]

    if "items_per_second" in row:
        row["interactions_per_second"] = row["items_per_second"]

    if "threads" in row and "total_cores" not in row:
        row["total_cores"] = row["threads"]


def parse_microbench_run(run_dir: Path, root: Path) -> List[Dict[str, Any]]:
    common = read_common_metadata(run_dir, root)
    benchmark = str(common.get("benchmark", ""))

    rows: List[Dict[str, Any]] = []

    for json_file in find_json_files(run_dir, benchmark):
        try:
            payload = json.loads(read_text(json_file))
        except Exception:
            continue

        context = payload.get("context", {})
        benches = payload.get("benchmarks", [])

        context_flat = flatten_context(context)

        for bench in benches:
            row = dict(common)
            row["kind"] = "microbench"
            row["json_file"] = str(json_file)

            row.update(context_flat)

            for key, value in bench.items():
                if key == "name":
                    row["benchmark_case"] = value
                    row.update(parse_microbench_name(str(value)))
                else:
                    row[key] = value

            add_microbench_derived_fields(row)
            rows.append(normalize_record(row, root))

    return rows


def parse_other_run(run_dir: Path, root: Path) -> Dict[str, Any]:
    row = read_common_metadata(run_dir, root)
    row["kind"] = "other"
    return normalize_record(row, root)


def discover_run_dirs(results_root: Path) -> List[Path]:
    seen: set[Path] = set()

    markers = [
        "run_info.txt",
        "stdout.log",
        "command.txt",
    ]

    for marker in markers:
        for p in results_root.rglob(marker):
            seen.add(p.parent.resolve())

    return sorted(seen)


def union_fieldnames(rows: Iterable[Dict[str, Any]]) -> List[str]:
    preferred = [
        "engine",
        "kind",
        "config",
        "benchmark",
        "benchmark_case",
        "case_group",
        "case_base",
        "case_args",
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
        "atom_steps",
        "bx",
        "by",
        "bz",
        "schedule",
        "layout",
        "vector_policy",
        "executor",
        "ordering",
        "threads",
        "ranks",
        "total_cores",
        "container",
        "workload",
        "implementation",
        "real_time",
        "cpu_time",
        "time_unit",
        "iterations",
        "items_per_second",
        "interactions_per_second",
        "ns/interaction",
        "ns_per_interaction",
        "wall_time_seconds",
        "wall_time_total_s",
        "integration_time_s",
        "throughput_it_per_s",
        "performance_mups",
        "mups_computed",
        "avg_step_time_s",
        "avg_step_time_from_integration_s",
        "median_step_time_s",
        "min_step_time_s",
        "max_step_time_s",
        "std_deviation_s",
        "hostname",
        "run_date",
        "variant",
        "isa_variant",
        "build_variant",
        "compiler_family",
        "auto_vectorization",
        "extra_cxx_flags",
        "april_enable_openmp",
        "april_enable_xsimd",
        "april_bench_enable_explicit_simd_baselines",
        "april_commit",
        "april_branch",
        "googlebenchmark_commit",
        "xsimd_commit",
        "benchmark_repo_commit",
        "context_date",
        "context_host_name",
        "context_num_cpus",
        "context_mhz_per_cpu",
        "context_cpu_scaling_enabled",
        "context_load_avg_1m",
        "context_load_avg_5m",
        "context_load_avg_15m",
        "stderr_cpu_scaling_warning",
        "stderr_load_avg_1m",
        "stderr_load_avg_5m",
        "stderr_load_avg_15m",
        "json_file",
        "build_dir",
        "stdout_file",
        "stderr_file",
        "command",
        "result_dir",
    ]

    seen: set[str] = set()
    materialized_rows = list(rows)

    for row in materialized_rows:
        seen.update(row.keys())

    ordered = [key for key in preferred if key in seen]
    remaining = sorted(seen - set(ordered))

    return ordered + remaining


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        return

    fieldnames = union_fieldnames(rows)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("."),
        help="Repository root used to normalize paths.",
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("results/april"),
        help="APRIL results root.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("analysis/april"),
        help="Output directory.",
    )

    args = parser.parse_args()

    project_root = args.project_root.resolve()

    results_root = args.results_root
    if not results_root.is_absolute():
        results_root = project_root / results_root
    results_root = results_root.resolve()

    out_dir = args.out_dir
    if not out_dir.is_absolute():
        out_dir = project_root / out_dir
    out_dir = out_dir.resolve()

    if not results_root.exists():
        raise SystemExit(f"APRIL results root does not exist: {results_root}")

    run_dirs = discover_run_dirs(results_root)
    if not run_dirs:
        raise SystemExit(f"No APRIL result runs found under: {results_root}")

    all_rows: List[Dict[str, Any]] = []
    microbench_rows: List[Dict[str, Any]] = []
    argon_rows: List[Dict[str, Any]] = []

    for run_dir in run_dirs:
        common = read_common_metadata(run_dir, project_root)
        benchmark = str(common.get("benchmark", ""))

        if benchmark in MICROBENCH_BENCHMARKS:
            rows = parse_microbench_run(run_dir, project_root)
            microbench_rows.extend(rows)
            all_rows.extend(rows)
        elif benchmark in ARGON_BENCHMARKS:
            row = parse_argon_run(run_dir, project_root)
            argon_rows.append(row)
            all_rows.append(row)
        else:
            row = parse_other_run(run_dir, project_root)
            all_rows.append(row)

    write_csv(out_dir / "april_all_runs.csv", all_rows)
    write_csv(out_dir / "april_microbench.csv", microbench_rows)
    write_csv(out_dir / "april_argon_scaling.csv", argon_rows)

    print(f"Wrote {len(all_rows)} rows:       {out_dir / 'april_all_runs.csv'}")
    print(f"Wrote {len(microbench_rows)} rows: {out_dir / 'april_microbench.csv'}")
    print(f"Wrote {len(argon_rows)} rows:      {out_dir / 'april_argon_scaling.csv'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())