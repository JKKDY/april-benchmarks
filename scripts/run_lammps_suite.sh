#!/usr/bin/env bash
set -euo pipefail

# Run the LAMMPS benchmark suite for one build config.
#
# Result layout comes from engines/lammps/run_*.sh:
#   results/lammps/<config>/<benchmark>/<scenario>/<time>/
#
# Usage:
#   scripts/run_lammps_suite.sh [--only force|argon|both] [config]
#
# Default:
#   scripts/run_lammps_suite.sh
#     uses openmp-native and runs both benchmarks

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

LAMMPS_ARGON_RUN="${PROJECT_ROOT}/engines/lammps/run_argon.sh"
LAMMPS_FORCE_RUN="${PROJECT_ROOT}/engines/lammps/run_force_kernel.sh"

usage() {
    cat >&2 <<EOF
Usage:
  $0 [--only force|argon|both] [config]

Default:
  $0
      uses openmp-native
      runs both force kernel and argon block

Options:
  --only WHAT           choose benchmark subset: force, argon, both
                        default: both

Config examples:
  openmp-generic
  openmp-native
  intel-generic
  intel-native

Examples:
  $0
  $0 openmp-native
  $0 intel-native
  $0 --only force intel-native
  $0 --only argon openmp-native
  $0 --only both intel-native

Force-kernel overrides:
  FORCE_N=50
  FORCE_STEPS=100

Argon environment overrides:
  ARGON_THREADS="1 2 3 4 6 8 11 16 23 32 45 56"
  ARGON_N=100
  ARGON_WEAK_BASE_N=32
  ARGON_RHO=0.8442
  ARGON_DT=0.005
  ARGON_STEPS=500

LAMMPS runtime:
  LAMMPS_BIND=close
  LAMMPS_MPI_RANKS_MODE=threads
      threads: strong scaling uses ranks=1, threads=T
      mpi:     strong scaling uses ranks=T, threads=1
      hybrid:  uses LAMMPS_HYBRID_RANKS and threads=T/ranks

  LAMMPS_HYBRID_RANKS=4
      only used for LAMMPS_MPI_RANKS_MODE=hybrid
EOF
    exit 1
}

ONLY="both"
CONFIG="openmp-native"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --only)
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
    force|argon|both)
        ;;
    *)
        echo "Unknown --only value: $ONLY" >&2
        echo "Valid values: force argon both" >&2
        exit 1
        ;;
esac

case "$CONFIG" in
    openmp-generic|openmp-native|intel-generic|intel-native)
        ;;
    *)
        echo "Unknown LAMMPS config: $CONFIG" >&2
        usage
        ;;
esac

if [[ ! -x "$LAMMPS_ARGON_RUN" ]]; then
    echo "LAMMPS argon run script not found or not executable: $LAMMPS_ARGON_RUN" >&2
    exit 1
fi

if [[ ! -x "$LAMMPS_FORCE_RUN" ]]; then
    echo "LAMMPS force-kernel run script not found or not executable: $LAMMPS_FORCE_RUN" >&2
    exit 1
fi

BUILD_DIR="${PROJECT_ROOT}/build/lammps-${CONFIG}"
if [[ ! -d "$BUILD_DIR" ]]; then
    echo "Build directory not found: $BUILD_DIR" >&2
    echo "Did you build this config?" >&2
    exit 1
fi

SUITE_TIME="${SUITE_TIME:-$(date +%Y%m%d_%H%M%S)}"

echo "Running LAMMPS benchmark suite"
echo "  config:     $CONFIG"
echo "  only:       $ONLY"
echo "  suite time: $SUITE_TIME"
echo "  project:    $PROJECT_ROOT"
echo

# ------------------------------------------------------------------------------
# 1. Force-kernel benchmark
# ------------------------------------------------------------------------------

if [[ "$ONLY" == "force" || "$ONLY" == "both" ]]; then
    FORCE_N="${FORCE_N:-50}"
    FORCE_STEPS="${FORCE_STEPS:-100}"

    echo "============================================================"
    echo "Running force_kernel_bench"
    echo "============================================================"
    echo "  n:      $FORCE_N"
    echo "  steps:  $FORCE_STEPS"
    echo

    SCENARIO="n${FORCE_N}_singlecore_steps${FORCE_STEPS}" \
    RUN_ID="$SUITE_TIME" \
    "$LAMMPS_FORCE_RUN" \
        --config "$CONFIG" \
        --n "$FORCE_N" \
        --steps "$FORCE_STEPS"
else
    echo "Skipping force_kernel_bench because --only=$ONLY"
fi

# ------------------------------------------------------------------------------
# 2. Argon block scaling sweeps
# ------------------------------------------------------------------------------

if [[ "$ONLY" == "argon" || "$ONLY" == "both" ]]; then
    ARGON_N="${ARGON_N:-100}"
    ARGON_WEAK_BASE_N="${ARGON_WEAK_BASE_N:-32}"

    ARGON_RHO="${ARGON_RHO:-0.8442}"
    ARGON_DT="${ARGON_DT:-0.005}"
    ARGON_STEPS="${ARGON_STEPS:-500}"

    ARGON_THREADS=(${ARGON_THREADS:-1 2 3 4 6 8 11 16 23 32 45 56})

    LAMMPS_BIND="${LAMMPS_BIND:-close}"
    LAMMPS_MPI_RANKS_MODE="${LAMMPS_MPI_RANKS_MODE:-threads}"
    LAMMPS_HYBRID_RANKS="${LAMMPS_HYBRID_RANKS:-4}"

    case "$LAMMPS_BIND" in
        close|spread)
            ;;
        *)
            echo "Unknown LAMMPS_BIND: $LAMMPS_BIND" >&2
            echo "Valid values: close spread" >&2
            exit 1
            ;;
    esac

    case "$LAMMPS_MPI_RANKS_MODE" in
        threads|mpi|hybrid)
            ;;
        *)
            echo "Unknown LAMMPS_MPI_RANKS_MODE: $LAMMPS_MPI_RANKS_MODE" >&2
            echo "Valid values: threads mpi hybrid" >&2
            exit 1
            ;;
    esac

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

    choose_lammps_layout() {
        local total="$1"

        case "$LAMMPS_MPI_RANKS_MODE" in
            threads)
                echo "1 $total"
                ;;
            mpi)
                echo "$total 1"
                ;;
            hybrid)
                local ranks="$LAMMPS_HYBRID_RANKS"
                if (( ranks < 1 )); then
                    ranks=1
                fi
                if (( ranks > total )); then
                    ranks="$total"
                fi

                local threads=$((total / ranks))
                if (( threads < 1 )); then
                    threads=1
                fi

                echo "$ranks $threads"
                ;;
        esac
    }

    run_argon_once() {
        local scaling="$1"
        local n="$2"
        local total_cores="$3"

        local particles=$((n * n * n))
        local ranks threads tag scenario

        read -r ranks threads < <(choose_lammps_layout "$total_cores")

        if [[ "$scaling" == "strong" ]]; then
            tag="strong_scaling"
        elif [[ "$scaling" == "weak" ]]; then
            tag="weak_scaling"
        else
            echo "Unknown scaling mode: $scaling" >&2
            exit 1
        fi

        if [[ -n "${SLURM_CPUS_PER_TASK:-}" && "$total_cores" -gt "$SLURM_CPUS_PER_TASK" ]]; then
            echo "Skipping total_cores=$total_cores because SLURM_CPUS_PER_TASK=$SLURM_CPUS_PER_TASK"
            return 0
        fi

        # openmp-* builds are built without MPI, so they must run with ranks=1.
        if [[ "$CONFIG" == openmp-* && "$ranks" -ne 1 ]]; then
            echo "Skipping ranks=$ranks for LAMMPS config: $CONFIG"
            return 0
        fi

        scenario="${scaling}_n${n}_p${particles}_rho${ARGON_RHO}_dt${ARGON_DT}_steps${ARGON_STEPS}_${LAMMPS_MPI_RANKS_MODE}_r${ranks}_t${threads}_bind${LAMMPS_BIND}"

        echo "------------------------------------------------------------"
        echo "Running argon_block"
        echo "  scaling:     $scaling"
        echo "  tag:         $tag"
        echo "  n:           $n"
        echo "  particles:   $particles"
        echo "  total cores: $total_cores"
        echo "  ranks:       $ranks"
        echo "  threads:     $threads"
        echo "  bind:        $LAMMPS_BIND"
        echo "  mode:        $LAMMPS_MPI_RANKS_MODE"
        echo "  scenario:    $scenario"
        echo "------------------------------------------------------------"

        SCENARIO="$scenario" \
        RUN_ID="$SUITE_TIME" \
        "$LAMMPS_ARGON_RUN" \
            --config "$CONFIG" \
            --n "$n" \
            --rho "$ARGON_RHO" \
            --steps "$ARGON_STEPS" \
            --dt "$ARGON_DT" \
            --ranks "$ranks" \
            --threads "$threads" \
            --bind "$LAMMPS_BIND"
    }

    echo
    echo "============================================================"
    echo "Running argon_block strong scaling sweep"
    echo "============================================================"
    echo "  fixed n:   $ARGON_N"
    echo "  rho:       $ARGON_RHO"
    echo "  dt:        $ARGON_DT"
    echo "  steps:     $ARGON_STEPS"
    echo "  mode:      $LAMMPS_MPI_RANKS_MODE"
    echo "  bind:      $LAMMPS_BIND"
    echo "  cores:     ${ARGON_THREADS[*]}"
    echo

    for T in "${ARGON_THREADS[@]}"; do
        run_argon_once "strong" "$ARGON_N" "$T"
    done

    echo
    echo "============================================================"
    echo "Running argon_block weak scaling sweep"
    echo "============================================================"
    echo "  base n @ 1 core: $ARGON_WEAK_BASE_N"
    echo "  rho:             $ARGON_RHO"
    echo "  dt:              $ARGON_DT"
    echo "  steps:           $ARGON_STEPS"
    echo "  mode:            $LAMMPS_MPI_RANKS_MODE"
    echo "  bind:            $LAMMPS_BIND"
    echo "  cores:           ${ARGON_THREADS[*]}"
    echo

    for T in "${ARGON_THREADS[@]}"; do
        N_WEAK="$(weak_n_for_threads "$ARGON_WEAK_BASE_N" "$T")"
        run_argon_once "weak" "$N_WEAK" "$T"
    done
else
    echo "Skipping argon_block because --only=$ONLY"
fi

echo
echo "LAMMPS benchmark suite complete."
echo "Results:"
echo "  ${PROJECT_ROOT}/results/lammps/${CONFIG}/"
echo
echo "Suite time:"
echo "  $SUITE_TIME"