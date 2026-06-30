#!/usr/bin/env bash
set -euo pipefail

# Run the April benchmark suite for one build config.
#
# Result layout comes from engines/april/run.sh:
#   results/april/<config>/<benchmark>/<scenario>/<time>/
#
# Usage:
#   scripts/run_april_suite.sh [--only all|force|hardcoded|micro|argon|strong|weak] [config]
#
# Default:
#   scripts/run_april_suite.sh
#       uses native
#       runs all benchmarks
#
# Examples:
#   scripts/run_april_suite.sh
#   scripts/run_april_suite.sh native
#   scripts/run_april_suite.sh --only hardcoded native
#   scripts/run_april_suite.sh --only strong native
#   scripts/run_april_suite.sh --only argon native
#
# Google Benchmark overrides:
#   GB_REPETITIONS=3
#   GB_AGGREGATES_ONLY=false
#
# Argon environment overrides:
#   ARGON_THREADS="1 2 3 4 6 8 11 16 23 32 45 56"
#   ARGON_N=100
#   ARGON_WEAK_BASE_N=32
#   ARGON_RHO=0.8442
#   ARGON_DT=0.005
#   ARGON_STEPS=500
#   ARGON_BX=2 ARGON_BY=2 ARGON_BZ=2
#   ARGON_SCHEDULE=C08
#   ARGON_LAYOUT=SoA
#   ARGON_EXECUTOR=OmpExecutor
#   ARGON_ORDERING=hilbert
#   ARGON_STRONG_REPEATS=3
#   ARGON_WEAK_REPEATS=1
#
# Valid --only values:
#   all         run everything
#   force       run force_kernel_bench only
#   hardcoded   run april_vs_hardcoded only
#   micro       run force_kernel_bench and april_vs_hardcoded
#   argon       run strong and weak argon_block sweeps
#   strong      run strong scaling argon_block sweep only
#   weak        run weak scaling argon_block sweep only

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

APRIL_RUN="${PROJECT_ROOT}/engines/april/run.sh"

usage() {
    cat >&2 <<EOF
Usage:
  $0 [--only all|force|hardcoded|micro|argon|strong|weak] [config]

Default:
  $0
      uses native
      runs all benchmarks

Options:
  --only WHAT
      all         run everything
      force       run force_kernel_bench only
      hardcoded   run april_vs_hardcoded only
      micro       run force_kernel_bench and april_vs_hardcoded
      argon       run strong and weak argon_block sweeps
      strong      run strong scaling argon_block sweep only
      weak        run weak scaling argon_block sweep only

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
  $0 --only hardcoded native
  $0 --only strong native
  $0 --only argon native

Google Benchmark overrides:
  GB_REPETITIONS=3
  GB_AGGREGATES_ONLY=false

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
  ARGON_STRONG_REPEATS=3
  ARGON_WEAK_REPEATS=1

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

ONLY="all"
CONFIG="native"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --only)
            if [[ $# -lt 2 ]]; then
                echo "Missing value for --only" >&2
                usage
            fi
            ONLY="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage
            ;;
        *)
            CONFIG="$1"
            shift
            ;;
    esac
done

case "$ONLY" in
    all|force|hardcoded|micro|argon|strong|weak)
        ;;
    *)
        echo "Unknown --only value: $ONLY" >&2
        echo "Valid values: all force hardcoded micro argon strong weak" >&2
        exit 1
        ;;
esac

should_run() {
    local target="$1"

    case "$ONLY:$target" in
        all:*)
            return 0
            ;;
        micro:force|micro:hardcoded)
            return 0
            ;;
        argon:strong|argon:weak)
            return 0
            ;;
        "$target":"$target")
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

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

GB_REPETITIONS="${GB_REPETITIONS:-1}"
GB_AGGREGATES_ONLY="${GB_AGGREGATES_ONLY:-true}"

echo "Running April benchmark suite"
echo "  config:               $CONFIG"
echo "  only:                 $ONLY"
echo "  suite time:           $SUITE_TIME"
echo "  project:              $PROJECT_ROOT"
echo "  GB repetitions:       $GB_REPETITIONS"
echo "  GB aggregates only:   $GB_AGGREGATES_ONLY"
echo

# ------------------------------------------------------------------------------
# 1. Google Benchmark microbenchmarks
# ------------------------------------------------------------------------------

if should_run force; then
    echo "============================================================"
    echo "Running force_kernel_bench"
    echo "============================================================"

    SCENARIO=default RUN_ID="$SUITE_TIME" "$APRIL_RUN" "$CONFIG" force_kernel_bench \
        --benchmark_repetitions="$GB_REPETITIONS" \
        --benchmark_report_aggregates_only="$GB_AGGREGATES_ONLY" \
        --benchmark_out_format=json \
        --benchmark_out=force_kernel_bench.json
else
    echo "Skipping force_kernel_bench because --only=$ONLY"
fi

if should_run hardcoded; then
    echo
    echo "============================================================"
    echo "Running april_vs_hardcoded"
    echo "============================================================"

    SCENARIO=default RUN_ID="$SUITE_TIME" "$APRIL_RUN" "$CONFIG" april_vs_hardcoded \
        --benchmark_repetitions="$GB_REPETITIONS" \
        --benchmark_report_aggregates_only="$GB_AGGREGATES_ONLY" \
        --benchmark_out_format=json \
        --benchmark_out=april_vs_hardcoded.json
else
    echo "Skipping april_vs_hardcoded because --only=$ONLY"
fi

# ------------------------------------------------------------------------------
# 2. Argon block scaling sweeps
# ------------------------------------------------------------------------------

if should_run strong || should_run weak; then
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

    ARGON_STRONG_REPEATS="${ARGON_STRONG_REPEATS:-1}"
    ARGON_WEAK_REPEATS="${ARGON_WEAK_REPEATS:-1}"

    ARGON_THREADS=(${ARGON_THREADS:-1 2 3 4 6 8 11 16 23 32 45 56})

    case "$ARGON_ORDERING" in
        hilbert|morton|none)
            ;;
        *)
            echo "Unknown ARGON_ORDERING: $ARGON_ORDERING" >&2
            echo "Valid values: hilbert morton none" >&2
            exit 1
            ;;
    esac

    case "$ARGON_EXECUTOR" in
        OmpExecutor|NativeSpinExecutor|NativeBarrierExecutor)
            ;;
        *)
            echo "Unknown ARGON_EXECUTOR: $ARGON_EXECUTOR" >&2
            echo "Valid values: OmpExecutor NativeSpinExecutor NativeBarrierExecutor" >&2
            exit 1
            ;;
    esac

    weak_n_for_threads() {
        local base_n="$1"
        local threads="$2"

        python3 - "$base_n" "$threads" <<'PY'
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
        local repeat="$4"

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

        local run_id
        run_id="${SUITE_TIME}_${scaling}_rep${repeat}"

        echo "------------------------------------------------------------"
        echo "Running argon_block"
        echo "  scaling:   $scaling"
        echo "  repeat:    $repeat"
        echo "  tag:       $tag"
        echo "  n:         $n"
        echo "  particles: $particles"
        echo "  threads:   $threads"
        echo "  rho:       $ARGON_RHO"
        echo "  dt:        $ARGON_DT"
        echo "  steps:     $ARGON_STEPS"
        echo "  block:     ${ARGON_BX}x${ARGON_BY}x${ARGON_BZ}"
        echo "  schedule:  $ARGON_SCHEDULE"
        echo "  layout:    $ARGON_LAYOUT"
        echo "  executor:  $ARGON_EXECUTOR"
        echo "  ordering:  $ARGON_ORDERING"
        echo "  scenario:  $scenario"
        echo "  run id:    $run_id"
        echo "------------------------------------------------------------"

        RUN_PREFIX="numactl --localalloc" \
        OMP_NUM_THREADS="$threads" \
        OMP_PLACES=cores \
        OMP_PROC_BIND=close \
        OMP_DYNAMIC=FALSE \
        SCENARIO="$scenario" RUN_ID="$run_id" "$APRIL_RUN" "$CONFIG" argon_block \
            "$n" "$ARGON_RHO" "$ARGON_DT" "$threads" "$ARGON_STEPS" \
            "$ARGON_BX" "$ARGON_BY" "$ARGON_BZ" \
            "$ARGON_SCHEDULE" "$ARGON_LAYOUT" "$ARGON_EXECUTOR" "$ARGON_ORDERING" "$tag"
    }

    if should_run strong; then
        echo
        echo "============================================================"
        echo "Running argon_block strong scaling sweep"
        echo "============================================================"
        echo "  repeats:   $ARGON_STRONG_REPEATS"
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

        for R in $(seq 1 "$ARGON_STRONG_REPEATS"); do
            for T in "${ARGON_THREADS[@]}"; do
                run_argon_once "strong" "$ARGON_N" "$T" "$R"
            done
        done
    else
        echo "Skipping strong scaling because --only=$ONLY"
    fi

    if should_run weak; then
        echo
        echo "============================================================"
        echo "Running argon_block weak scaling sweep"
        echo "============================================================"
        echo "  repeats:           $ARGON_WEAK_REPEATS"
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

        for R in $(seq 1 "$ARGON_WEAK_REPEATS"); do
            for T in "${ARGON_THREADS[@]}"; do
                N_WEAK="$(weak_n_for_threads "$ARGON_WEAK_BASE_N" "$T")"
                run_argon_once "weak" "$N_WEAK" "$T" "$R"
            done
        done
    else
        echo "Skipping weak scaling because --only=$ONLY"
    fi
else
    echo "Skipping argon_block because --only=$ONLY"
fi

echo
echo "April benchmark suite complete."
echo "Results:"
echo "  ${PROJECT_ROOT}/results/april/${CONFIG}/"
echo
echo "Suite time:"
echo "  $SUITE_TIME"
