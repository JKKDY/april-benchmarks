#!/usr/bin/env bash
set -euo pipefail

# Run the April benchmark suite for one build config.
#
# Result layout comes from engines/april/run.sh:
#   results/april/<config>/<benchmark>/<scenario>/<time>/
#
# Usage:
#   scripts/run_april_suite.sh [config]
#
# Default:
#   scripts/run_april_suite.sh
#     uses native

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

APRIL_RUN="${PROJECT_ROOT}/engines/april/run.sh"

usage() {
    cat >&2 <<EOF
Usage:
  $0 [config]

Default:
  $0
      uses native

Config examples:
  generic
  generic-novec
  sse
  sse-novec
  avx2
  avx2-novec
  avx512
  avx512-novec
  native
  native-novec
  native-gcc
  native-gcc-novec

Examples:
  $0
  $0 native
  $0 native-novec
  $0 native-gcc
  $0 native-gcc-novec

Argon environment overrides:
  ARGON_THREADS="1 2 3 4 6 8 11 16 23 32 45 56"
  ARGON_N=100
  ARGON_WEAK_BASE_N=32
  ARGON_RHO=0.8442
  ARGON_DT=0.005
  ARGON_STEPS=500
  ARGON_BX=2 ARGON_BY=2 ARGON_BZ=2
  ARGON_SCHEDULE=C08
  ARGON_LAYOUT=SoA
  ARGON_EXECUTOR=OmpExecutor
  ARGON_ORDERING=hilbert

Valid orderings:
  hilbert
  morton
  none

Valid executors:
  OmpExecutor
  NativeSpinExecutor
  NativeBarrierExecutor
EOF
    exit 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
fi

CONFIG="${1:-native}"

if [[ ! -x "$APRIL_RUN" ]]; then
    echo "April run script not found or not executable: $APRIL_RUN" >&2
    exit 1
fi

BUILD_DIR="${PROJECT_ROOT}/build/april-${CONFIG}"
if [[ ! -d "$BUILD_DIR" ]]; then
    echo "Build directory not found: $BUILD_DIR" >&2
    echo "Did you build this config?" >&2
    exit 1
fi

SUITE_TIME="${SUITE_TIME:-$(date +%Y%m%d_%H%M%S)}"

echo "Running April benchmark suite"
echo "  config:     $CONFIG"
echo "  suite time: $SUITE_TIME"
echo "  project:    $PROJECT_ROOT"
echo

# ------------------------------------------------------------------------------
# 1. Google Benchmark microbenchmarks
# ------------------------------------------------------------------------------

echo "============================================================"
echo "Running force_kernel_bench"
echo "============================================================"

SCENARIO=default RUN_ID="$SUITE_TIME" "$APRIL_RUN" "$CONFIG" force_kernel_bench \
    --benchmark_repetitions=3 \
    --benchmark_report_aggregates_only=true \
    --benchmark_out_format=json \
    --benchmark_out=force_kernel_bench.json

echo
echo "============================================================"
echo "Running april_vs_hardcoded"
echo "============================================================"

SCENARIO=default RUN_ID="$SUITE_TIME" "$APRIL_RUN" "$CONFIG" april_vs_hardcoded \
    --benchmark_repetitions=3 \
    --benchmark_report_aggregates_only=true \
    --benchmark_out_format=json \
    --benchmark_out=april_vs_hardcoded.json

# ------------------------------------------------------------------------------
# 2. Argon block scaling sweeps
# ------------------------------------------------------------------------------

ARGON_N="${ARGON_N:-100}"
ARGON_WEAK_BASE_N="${ARGON_WEAK_BASE_N:-32}"

ARGON_RHO="${ARGON_RHO:-0.8442}"
ARGON_DT="${ARGON_DT:-0.005}"
ARGON_STEPS="${ARGON_STEPS:-500}"

ARGON_BX="${ARGON_BX:-2}"
ARGON_BY="${ARGON_BY:-2}"
ARGON_BZ="${ARGON_BZ:-2}"

ARGON_SCHEDULE="${ARGON_SCHEDULE:-C08}"
ARGON_LAYOUT="${ARGON_LAYOUT:-SoA}"
ARGON_EXECUTOR="${ARGON_EXECUTOR:-OmpExecutor}"
ARGON_ORDERING="${ARGON_ORDERING:-hilbert}"

case "$ARGON_ORDERING" in
    hilbert|morton|none)
        ;;
    *)
        echo "Unknown ARGON_ORDERING: $ARGON_ORDERING" >&2
        echo "Valid values: hilbert morton none" >&2
        exit 1
        ;;
esac

ARGON_THREADS=(${ARGON_THREADS:-1 2 3 4 6 8 11 16 23 32 45 56})

weak_n_for_threads() {
    local base_n="$1"
    local threads="$2"

    python3 - "$base_n" "$threads" <<'PY'
import math
import sys

base_n = int(sys.argv[1])
threads = int(sys.argv[2])

n = round(base_n * (threads ** (1.0 / 3.0)))
print(max(1, n))
PY
}

run_argon_once() {
    local scaling="$1"
    local n="$2"
    local threads="$3"

    local particles=$((n * n * n))
    local tag

    if [[ "$scaling" == "strong" ]]; then
        tag="strong_scaling"
    elif [[ "$scaling" == "weak" ]]; then
        tag="weak_scaling"
    else
        echo "Unknown scaling mode: $scaling" >&2
        exit 1
    fi

    if [[ -n "${SLURM_CPUS_PER_TASK:-}" && "$threads" -gt "$SLURM_CPUS_PER_TASK" ]]; then
        echo "Skipping threads=$threads because SLURM_CPUS_PER_TASK=$SLURM_CPUS_PER_TASK"
        return 0
    fi

    local scenario
    scenario="${scaling}_n${n}_p${particles}_rho${ARGON_RHO}_dt${ARGON_DT}_steps${ARGON_STEPS}_b${ARGON_BX}x${ARGON_BY}x${ARGON_BZ}_${ARGON_SCHEDULE}_${ARGON_LAYOUT}_${ARGON_EXECUTOR}_${ARGON_ORDERING}_t${threads}"

    echo "------------------------------------------------------------"
    echo "Running argon_block"
    echo "  scaling:   $scaling"
    echo "  tag:       $tag"
    echo "  n:         $n"
    echo "  particles: $particles"
    echo "  threads:   $threads"
    echo "  schedule:  $ARGON_SCHEDULE"
    echo "  layout:    $ARGON_LAYOUT"
    echo "  executor:  $ARGON_EXECUTOR"
    echo "  ordering:  $ARGON_ORDERING"
    echo "  scenario:  $scenario"
    echo "------------------------------------------------------------"

    RUN_PREFIX="numactl --localalloc" \
    OMP_NUM_THREADS="$threads" \
    OMP_PLACES=cores \
    OMP_PROC_BIND=close \
    OMP_DYNAMIC=FALSE \
    SCENARIO="$scenario" RUN_ID="$SUITE_TIME" "$APRIL_RUN" "$CONFIG" argon_block \
        "$n" "$ARGON_RHO" "$ARGON_DT" "$threads" "$ARGON_STEPS" \
        "$ARGON_BX" "$ARGON_BY" "$ARGON_BZ" \
        "$ARGON_SCHEDULE" "$ARGON_LAYOUT" "$ARGON_EXECUTOR" "$ARGON_ORDERING" "$tag"
}

echo
echo "============================================================"
echo "Running argon_block strong scaling sweep"
echo "============================================================"
echo "  fixed n:   $ARGON_N"
echo "  rho:       $ARGON_RHO"
echo "  dt:        $ARGON_DT"
echo "  steps:     $ARGON_STEPS"
echo "  block:     ${ARGON_BX}x${ARGON_BY}x${ARGON_BZ}"
echo "  schedule:  $ARGON_SCHEDULE"
echo "  layout:    $ARGON_LAYOUT"
echo "  executor:  $ARGON_EXECUTOR"
echo "  ordering:  $ARGON_ORDERING"
echo "  threads:   ${ARGON_THREADS[*]}"
echo

for T in "${ARGON_THREADS[@]}"; do
    run_argon_once "strong" "$ARGON_N" "$T"
done

echo
echo "============================================================"
echo "Running argon_block weak scaling sweep"
echo "============================================================"
echo "  base n @ 1 thread: $ARGON_WEAK_BASE_N"
echo "  rho:               $ARGON_RHO"
echo "  dt:                $ARGON_DT"
echo "  steps:             $ARGON_STEPS"
echo "  block:             ${ARGON_BX}x${ARGON_BY}x${ARGON_BZ}"
echo "  schedule:          $ARGON_SCHEDULE"
echo "  layout:            $ARGON_LAYOUT"
echo "  executor:          $ARGON_EXECUTOR"
echo "  ordering:          $ARGON_ORDERING"
echo "  threads:           ${ARGON_THREADS[*]}"
echo

for T in "${ARGON_THREADS[@]}"; do
    N_WEAK="$(weak_n_for_threads "$ARGON_WEAK_BASE_N" "$T")"
    run_argon_once "weak" "$N_WEAK" "$T"
done

echo
echo "April benchmark suite complete."
echo "Results:"
echo "  ${PROJECT_ROOT}/results/april/${CONFIG}/"
echo
echo "Suite time:"
echo "  $SUITE_TIME"