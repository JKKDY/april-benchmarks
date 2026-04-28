#!/usr/bin/env python3
"""
Parse LAMMPS benchmark results into flat CSV tables.

Expected layout:
  results/lammps/<config>/<benchmark>/<scenario>/<run_id>/

Primary inputs per run:
  - derived_metrics.txt
  - configuration.log
  - run_info.txt
  - command.txt
  - stdout.log / log.lammps, when useful

Outputs:
  analysis/lammps/lammps_all_runs.csv
  analysis/lammps/lammps_force_kernel.csv
  analysis/lammps/lammps_scaling.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import shlex
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PATH_KEYS = {
    "result_dir",
    "datafile",
    "input_file",
    "lammps_bin",
    "stdout_file",
    "stderr_file",
    "log_file",
    "configuration_file",
    "metrics_file",
    "build_dir",
    "install_dir",
}

NUMERIC_KEYS = {
    "n",
    "n_dim",
    "atoms",
    "particles",
    "rho",
    "steps",
    "dt",
    "ranks",
    "threads",
    "total_cores",
    "loop_time_s",
    "timesteps_per_second",
    "matom_step_per_second",
    "performance_mups",
    "avg_step_time_s",
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
    "pair_ns_per_interaction",
    "pair_interactions_per_second",
    "wall_time_s",
    "wall_time_seconds",
}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def maybe_number(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    s = value.strip()
    if s.lower() in {"", "unknown", "unset", "none", "nan"}:
        return s

    if s.endswith("%"):
        s = s[:-1]

    try:
        if any(ch in s for ch in ".eE+-"):
            return float(s)
        return int(s)
    except Exception:
        return value


def parse_kv_file(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}

    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue

        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()

    return data


def parse_colon_file(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}

    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue

        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()

    return data


def parse_command(path: Path) -> str:
    return read_text(path).strip()


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


def infer_kind(benchmark: str) -> str:
    if benchmark == "force_kernel_bench":
        return "force_kernel"
    if benchmark == "argon_block":
        return "scaling"
    return "other"


def infer_from_path(run_dir: Path) -> Dict[str, Any]:
    """
    Infer config/benchmark/scenario/run_id from:
      .../results/lammps/<config>/<benchmark>/<scenario>/<run_id>
    """
    out: Dict[str, Any] = {}
    parts = run_dir.parts

    if "lammps" not in parts:
        return out

    idx = parts.index("lammps")
    tail = parts[idx + 1 :]

    if len(tail) >= 4:
        out["config"] = tail[0]
        out["benchmark"] = tail[1]
        out["scenario"] = tail[2]
        out["run_id"] = tail[3]

    return out


def parse_run_info(path: Path) -> Dict[str, Any]:
    """
    Extract selected LAMMPS metadata from run_info.txt.
    """
    text = read_text(path)
    flat = parse_colon_file(path)

    out: Dict[str, Any] = {}

    direct_map = {
        "Engine": "engine_from_run_info",
        "Config": "config",
        "Benchmark": "benchmark",
        "Scenario": "scenario",
        "Run ID": "run_id",
        "Run Date": "run_date",
        "Hostname": "hostname",
        "Result Dir": "result_dir_from_run_info",
        "LAMMPS Binary": "lammps_bin",
        "Input File": "input_file",
        "Datafile": "datafile",
        "n_dim": "n_dim",
        "rho": "rho",
        "steps": "steps",
        "dt": "dt",
        "ranks": "ranks",
        "threads": "threads",
        "bind": "bind",
        "Build Dir": "build_dir",
        "Install Dir": "install_dir",
        "CC": "cc",
        "CXX": "cxx",
        "Extra C Flags": "extra_c_flags",
        "Extra CXX Flags": "extra_cxx_flags",
        "CMAKE_BUILD_TYPE": "cmake_build_type",
        "BUILD_MPI": "build_mpi",
        "BUILD_OMP": "build_omp",
        "PKG_OPENMP": "pkg_openmp",
        "PKG_INTEL": "pkg_intel",
        "INTEL_ARCH": "intel_arch",
        "INTEL_LRT_MODE": "intel_lrt_mode",
        "LAMMPS_FP_MODEL": "lammps_fp_model",
        "LAMMPS Commit": "lammps_commit",
        "Benchmark Repo Commit": "benchmark_repo_commit",
        "Wall Time Seconds": "wall_time_seconds",
    }

    for source, dest in direct_map.items():
        if source in flat:
            out[dest] = flat[source]

    env_patterns = {
        "omp_num_threads": r"OMP_NUM_THREADS=([^\n]+)",
        "omp_places": r"OMP_PLACES=([^\n]+)",
        "omp_proc_bind": r"OMP_PROC_BIND=([^\n]+)",
        "omp_dynamic": r"OMP_DYNAMIC=([^\n]+)",
        "kmp_affinity": r"KMP_AFFINITY=([^\n]+)",
        "kmp_blocktime": r"KMP_BLOCKTIME=([^\n]+)",
        "slurm_job_id": r"SLURM_JOB_ID=([^\n]+)",
        "slurm_cpus_per_task": r"SLURM_CPUS_PER_TASK=([^\n]+)",
    }

    for key, pattern in env_patterns.items():
        m = re.search(pattern, text)
        if m:
            out[key] = m.group(1).strip()

    return out


_SCALING_RE = re.compile(
    r"^(?P<scaling>strong|weak)"
    r"_n(?P<n>\d+)"
    r"_p(?P<particles>\d+)"
    r"_rho(?P<rho>[-+0-9.eE]+)"
    r"_dt(?P<dt>[-+0-9.eE]+)"
    r"_steps(?P<steps>\d+)"
    r"_(?P<mode>threads|mpi|hybrid)"
    r"_r(?P<ranks>\d+)"
    r"_t(?P<threads>\d+)"
    r"_bind(?P<bind>[^_]+)$"
)


_FORCE_RE = re.compile(
    r"^n(?P<n>\d+)_singlecore_steps(?P<steps>\d+)$"
)


def parse_scenario(scenario: str, benchmark: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    if benchmark == "argon_block":
        m = _SCALING_RE.match(scenario)
        if m:
            out.update(m.groupdict())
            for key in ["n", "particles", "steps", "ranks", "threads"]:
                out[key] = int(out[key])
            for key in ["rho", "dt"]:
                out[key] = float(out[key])
            out["total_cores"] = int(out["ranks"]) * int(out["threads"])

    elif benchmark == "force_kernel_bench":
        m = _FORCE_RE.match(scenario)
        if m:
            out.update(m.groupdict())
            out["n"] = int(out["n"])
            out["steps"] = int(out["steps"])
            out["particles"] = int(out["n"]) ** 3
            out.setdefault("ranks", 1)
            out.setdefault("threads", 1)
            out.setdefault("total_cores", 1)

    return out


def parse_stdout_or_log(path: Path) -> Dict[str, Any]:
    """
    Parse useful fallback data from stdout.log or log.lammps.
    derived_metrics.txt is preferred, but this helps fill gaps.
    """
    text = read_text(path)
    out: Dict[str, Any] = {}

    m = re.search(r"LAMMPS \(([^)]+)\)", text)
    if m:
        out["lammps_version"] = m.group(1).strip()

    m = re.search(r"Performance:\s*[^,\n]+,\s*([0-9.eE+-]+)\s+timesteps/s,\s*([0-9.eE+-]+)\s+Matom-step/s", text)
    if m:
        out["timesteps_per_second"] = float(m.group(1))
        out["matom_step_per_second"] = float(m.group(2))

    m = re.search(r"(\d+(?:\.\d+)?)%\s+CPU use with", text)
    if m:
        out["cpu_use_percent"] = float(m.group(1))

    m = re.search(r"Total # of neighbors =\s*([0-9.eE+-]+)", text)
    if m:
        value = float(m.group(1))
        out["total_neighbors"] = int(value) if value.is_integer() else value

    m = re.search(r"Neighbor list builds =\s*([0-9]+)", text)
    if m:
        out["neighbor_list_builds"] = int(m.group(1))

    m = re.search(r"Dangerous builds =\s*([0-9]+)", text)
    if m:
        out["dangerous_builds"] = int(m.group(1))

    return out


def add_derived_fields(row: Dict[str, Any]) -> None:
    """
    Add common fields aligned with APRIL parser output.
    """
    atoms = maybe_number(row.get("atoms", ""))
    particles = maybe_number(row.get("particles", ""))

    if "particles" not in row and isinstance(atoms, int):
        row["particles"] = atoms

    if "atoms" not in row and isinstance(particles, int):
        row["atoms"] = particles

    ranks = maybe_number(row.get("ranks", ""))
    threads = maybe_number(row.get("threads", ""))

    if isinstance(ranks, int) and isinstance(threads, int):
        row["total_cores"] = ranks * threads

    matom = maybe_number(row.get("matom_step_per_second", ""))
    if isinstance(matom, (int, float)):
        row["performance_mups"] = float(matom)

    loop_time = maybe_number(row.get("loop_time_s", ""))
    steps = maybe_number(row.get("steps", ""))

    if isinstance(loop_time, (int, float)) and isinstance(steps, int) and steps > 0:
        row["avg_step_time_s"] = float(loop_time) / steps

    # For force_kernel_bench, derived_metrics uses neighbors_per_step.
    neighbors_per_step = maybe_number(row.get("neighbors_per_step", ""))
    pair_time = maybe_number(row.get("pair_time_s", ""))

    if isinstance(pair_time, (int, float)) and isinstance(steps, int) and steps > 0:
        if isinstance(neighbors_per_step, (int, float)) and neighbors_per_step > 0:
            row.setdefault(
                "pair_ns_per_interaction",
                float(pair_time) * 1.0e9 / (steps * float(neighbors_per_step)),
            )
            row.setdefault(
                "pair_interactions_per_second",
                steps * float(neighbors_per_step) / float(pair_time),
            )

    # For argon_block, derived_metrics uses total_neighbors from the final timed run.
    total_neighbors = maybe_number(row.get("total_neighbors", ""))
    if isinstance(pair_time, (int, float)) and isinstance(steps, int) and steps > 0:
        if isinstance(total_neighbors, (int, float)) and total_neighbors > 0:
            row.setdefault(
                "pair_ns_per_interaction",
                float(pair_time) * 1.0e9 / (steps * float(total_neighbors)),
            )
            row.setdefault(
                "pair_interactions_per_second",
                steps * float(total_neighbors) / float(pair_time),
            )

    # Keep LAMMPS force-kernel naming aligned with APRIL microbench naming.
    if "ns_per_interaction" in row and "pair_ns_per_interaction" not in row:
        row["pair_ns_per_interaction"] = row["ns_per_interaction"]

    if "interactions_per_second" in row and "pair_interactions_per_second" not in row:
        row["pair_interactions_per_second"] = row["interactions_per_second"]


def read_run(run_dir: Path, root: Path) -> Optional[Dict[str, Any]]:
    metrics_path = run_dir / "derived_metrics.txt"
    config_path = run_dir / "configuration.log"
    run_info_path = run_dir / "run_info.txt"
    command_path = run_dir / "command.txt"

    if not any(p.exists() for p in [metrics_path, config_path, run_info_path, command_path]):
        return None

    row: Dict[str, Any] = {}

    row.update(infer_from_path(run_dir))

    # Lowest priority: run info.
    row.update(parse_run_info(run_info_path))

    # Configuration and metrics should override run_info where they are more explicit.
    row.update(parse_kv_file(config_path))
    row.update(parse_kv_file(metrics_path))

    benchmark = str(row.get("benchmark", ""))
    scenario = str(row.get("scenario", ""))

    # Scenario adds scaling/mode and can fill missing values.
    scenario_data = parse_scenario(scenario, benchmark)
    for key, value in scenario_data.items():
        row.setdefault(key, value)

    # Fallback parse from stdout/log for values parser may have missed.
    stdout_data = parse_stdout_or_log(run_dir / "stdout.log")
    log_data = parse_stdout_or_log(run_dir / "log.lammps")

    for key, value in log_data.items():
        row.setdefault(key, value)
    for key, value in stdout_data.items():
        row.setdefault(key, value)

    command = parse_command(command_path)
    if command:
        row["command"] = command

    row["engine"] = "lammps"
    row["kind"] = infer_kind(benchmark)
    row["result_dir"] = str(run_dir)
    row["stdout_file"] = str(run_dir / "stdout.log")
    row["stderr_file"] = str(run_dir / "stderr.log")
    row["log_file"] = str(run_dir / "log.lammps")
    row["configuration_file"] = str(config_path)
    row["metrics_file"] = str(metrics_path)

    add_derived_fields(row)

    return normalize_record(row, root)


def discover_run_dirs(results_root: Path) -> List[Path]:
    seen: set[Path] = set()

    markers = [
        "derived_metrics.txt",
        "configuration.log",
        "run_info.txt",
        "command.txt",
    ]

    for marker in markers:
        for path in results_root.rglob(marker):
            seen.add(path.parent.resolve())

    return sorted(seen)


def union_fieldnames(rows: Iterable[Dict[str, Any]]) -> List[str]:
    materialized = list(rows)
    seen: set[str] = set()

    for row in materialized:
        seen.update(row.keys())

    preferred = [
        "engine",
        "kind",
        "config",
        "benchmark",
        "scenario",
        "run_id",
        "scaling",
        "mode",
        "n",
        "n_dim",
        "atoms",
        "particles",
        "rho",
        "steps",
        "dt",
        "ranks",
        "threads",
        "total_cores",
        "bind",
        "loop_time_s",
        "timesteps_per_second",
        "matom_step_per_second",
        "performance_mups",
        "avg_step_time_s",
        "cpu_use_percent",
        "pair_time_s",
        "neigh_time_s",
        "comm_time_s",
        "modify_time_s",
        "total_neighbors",
        "neighbors_per_step",
        "neighbor_list_builds",
        "dangerous_builds",
        "ns_per_interaction",
        "interactions_per_second",
        "pair_ns_per_interaction",
        "pair_interactions_per_second",
        "wall_time_s",
        "wall_time_seconds",
        "hostname",
        "run_date",
        "lammps_version",
        "build_mpi",
        "build_omp",
        "pkg_openmp",
        "pkg_intel",
        "intel_arch",
        "intel_lrt_mode",
        "lammps_fp_model",
        "cc",
        "cxx",
        "extra_c_flags",
        "extra_cxx_flags",
        "cmake_build_type",
        "lammps_commit",
        "benchmark_repo_commit",
        "omp_num_threads",
        "omp_places",
        "omp_proc_bind",
        "omp_dynamic",
        "kmp_affinity",
        "kmp_blocktime",
        "slurm_job_id",
        "slurm_cpus_per_task",
        "datafile",
        "input_file",
        "lammps_bin",
        "command",
        "result_dir",
        "stdout_file",
        "stderr_file",
        "log_file",
        "configuration_file",
        "metrics_file",
    ]

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
        default=Path("results/lammps"),
        help="LAMMPS results root.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("analysis/lammps"),
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
        raise SystemExit(f"LAMMPS results root does not exist: {results_root}")

    run_dirs = discover_run_dirs(results_root)
    if not run_dirs:
        raise SystemExit(f"No LAMMPS result runs found under: {results_root}")

    all_rows: List[Dict[str, Any]] = []

    for run_dir in run_dirs:
        row = read_run(run_dir, project_root)
        if row is not None:
            all_rows.append(row)

    if not all_rows:
        raise SystemExit(f"No parseable LAMMPS result runs found under: {results_root}")

    force_rows = [row for row in all_rows if row.get("kind") == "force_kernel"]
    scaling_rows = [row for row in all_rows if row.get("kind") == "scaling"]

    write_csv(out_dir / "lammps_all_runs.csv", all_rows)
    write_csv(out_dir / "lammps_force_kernel.csv", force_rows)
    write_csv(out_dir / "lammps_scaling.csv", scaling_rows)

    print(f"Wrote {len(all_rows)} rows:    {out_dir / 'lammps_all_runs.csv'}")
    print(f"Wrote {len(force_rows)} rows:  {out_dir / 'lammps_force_kernel.csv'}")
    print(f"Wrote {len(scaling_rows)} rows:{out_dir / 'lammps_scaling.csv'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())