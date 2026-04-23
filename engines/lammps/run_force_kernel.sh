#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() {
    cat >&2 <<EOF
Usage:
  $0 [options]

Options:
  --config CONFIG       LAMMPS build config
                        openmp-generic
                        openmp-native
                        intel-generic
                        intel-native

  --n N                 particles per dimension, default: 32
  --steps STEPS         force-loop benchmark steps, default: 20
  --datafile FILE       optional datafile path
  --no-generate         do not regenerate datafile
  --help                show this help

Environment:
  SCENARIO              scenario folder name, default: n<N>_steps<STEPS>
  RUN_ID                run folder name, default: timestamp
  RESULT_ROOT           override result root, default: <repo>/results/lammps

Examples:
  $0 --config openmp-native --n 100 --steps 20
  $0 --config intel-native --n 100 --steps 20
EOF
    exit 1
}

sanitize_path_component() {
    local value="$1"
    value="${value// /_}"
    value="${value//\//_}"
    value="${value//:/-}"
    value="${value//,/}"
    echo "$value"
}

CONFIG="openmp-native"
N_DIM="32"
STEPS="20"
DATAFILE=""
GENERATE="yes"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)
            CONFIG="$2"
            shift 2
            ;;
        --n|--n-dim|--n_dim)
            N_DIM="$2"
            shift 2
            ;;
        --steps)
            STEPS="$2"
            shift 2
            ;;
        --datafile)
            DATAFILE="$2"
            shift 2
            ;;
        --no-generate)
            GENERATE="no"
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage
            ;;
    esac
done

case "$CONFIG" in
    openmp-generic|openmp-native|intel-generic|intel-native)
        ;;
    *)
        echo "Unknown config: $CONFIG" >&2
        usage
        ;;
esac

CONFIG_SAFE="$(sanitize_path_component "$CONFIG")"
BENCHMARK="force_kernel_bench"
SCENARIO="$(sanitize_path_component "${SCENARIO:-n${N_DIM}_steps${STEPS}}")"
RUN_ID="$(sanitize_path_component "${RUN_ID:-$(date +%Y%m%d_%H%M%S)}")"

RESULT_BASE="${RESULT_ROOT:-${PROJECT_ROOT}/results/lammps}"
RESULT_DIR="${RESULT_BASE}/${CONFIG_SAFE}/${BENCHMARK}/${SCENARIO}/${RUN_ID}"
mkdir -p "$RESULT_DIR"

STDOUT_FILE="${RESULT_DIR}/stdout.log"
STDERR_FILE="${RESULT_DIR}/stderr.log"
META_FILE="${RESULT_DIR}/run_info.txt"
COMMAND_FILE="${RESULT_DIR}/command.txt"
CONFIG_FILE="${RESULT_DIR}/configuration.log"
METRICS_FILE="${RESULT_DIR}/derived_metrics.txt"

LAMMPS_BIN="${PROJECT_ROOT}/build/lammps-${CONFIG}/install/bin/lmp"
INPUT_FILE="${SCRIPT_DIR}/force_kernel_bench.in"
GRID_SCRIPT="${SCRIPT_DIR}/make_force_kernel_grid.py"

if [[ ! -x "$LAMMPS_BIN" ]]; then
    echo "Missing LAMMPS binary: $LAMMPS_BIN" >&2
    echo "Build it first, for example:" >&2
    echo "  ${SCRIPT_DIR}/build_lammps.sh ${CONFIG}" >&2
    exit 1
fi

if [[ ! -f "$INPUT_FILE" ]]; then
    echo "Missing input file: $INPUT_FILE" >&2
    exit 1
fi

if [[ "$GENERATE" == "yes" && ! -f "$GRID_SCRIPT" ]]; then
    echo "Missing grid generator: $GRID_SCRIPT" >&2
    exit 1
fi

if [[ -z "$DATAFILE" ]]; then
    DATAFILE="${RESULT_DIR}/force_kernel_grid_n${N_DIM}.data"
else
    DATAFILE="$(realpath "$DATAFILE")"
fi

if [[ "$GENERATE" == "yes" ]]; then
    echo "Generating force-kernel grid:"
    echo "  n_dim    = $N_DIM"
    echo "  datafile = $DATAFILE"
    python3 "$GRID_SCRIPT" "$N_DIM" "$DATAFILE" | tee "${RESULT_DIR}/grid_generation.log"
else
    if [[ ! -f "$DATAFILE" ]]; then
        echo "Datafile does not exist and --no-generate was given: $DATAFILE" >&2
        exit 1
    fi
fi

# This benchmark is intentionally single-rank, single-thread.
export OMP_NUM_THREADS=1
export OMP_DYNAMIC=FALSE

LAMMPS_ARGS=(
    -in "$INPUT_FILE"
    -var datafile "$DATAFILE"
    -var n_dim "$N_DIM"
    -var steps "$STEPS"
)

RUN_CMD=()

case "$CONFIG" in
    openmp-generic|openmp-native)
        # Keep OpenMP package suffix enabled, but force 1 thread.
        LAMMPS_ARGS+=(-sf omp -pk omp 1)
        RUN_CMD=("$LAMMPS_BIN")
        ;;

    intel-generic|intel-native)
        module load intel intel-mpi intel-mkl intel-oneapi-tbb

        export KMP_BLOCKTIME=0
        export KMP_AFFINITY=granularity=fine,compact,1,0

        # Keep INTEL package suffix enabled, but force 1 thread.
        LAMMPS_ARGS+=(-sf intel -pk intel 1)
        RUN_CMD=(mpirun -np 1 "$LAMMPS_BIN")
        ;;
esac

printf "%q " "${RUN_CMD[@]}" "${LAMMPS_ARGS[@]}" > "$COMMAND_FILE"
printf "\n" >> "$COMMAND_FILE"

{
    echo "Engine: LAMMPS"
    echo "Config: $CONFIG"
    echo "Benchmark: $BENCHMARK"
    echo "Scenario: $SCENARIO"
    echo "Run ID: $RUN_ID"
    echo "Run Date: $(date --iso-8601=seconds)"
    echo "Hostname: $(hostname)"
    echo "Project Root: $PROJECT_ROOT"
    echo "Result Dir: $RESULT_DIR"
    echo "Working Dir: $RESULT_DIR"
    echo "LAMMPS Binary: $LAMMPS_BIN"
    echo "Input File: $INPUT_FILE"
    echo "Datafile: $DATAFILE"
    echo "n_dim: $N_DIM"
    echo "steps: $STEPS"
    echo "ranks: 1"
    echo "threads: 1"
    echo "Command: $(cat "$COMMAND_FILE")"
    echo "Benchmark Repo Commit: $(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
    echo
    echo "Environment:"
    echo "  OMP_NUM_THREADS=${OMP_NUM_THREADS:-unset}"
    echo "  OMP_DYNAMIC=${OMP_DYNAMIC:-unset}"
    echo "  OMP_PLACES=${OMP_PLACES:-unset}"
    echo "  OMP_PROC_BIND=${OMP_PROC_BIND:-unset}"
    echo "  KMP_AFFINITY=${KMP_AFFINITY:-unset}"
    echo "  KMP_BLOCKTIME=${KMP_BLOCKTIME:-unset}"
    echo "  SLURM_JOB_ID=${SLURM_JOB_ID:-unset}"
    echo "  SLURM_CPUS_PER_TASK=${SLURM_CPUS_PER_TASK:-unset}"
    echo
    echo "Build Info:"
    if [[ -f "${PROJECT_ROOT}/build/lammps-${CONFIG}/benchmark_info.txt" ]]; then
        cat "${PROJECT_ROOT}/build/lammps-${CONFIG}/benchmark_info.txt"
    else
        echo "No benchmark_info.txt found"
    fi
} > "$META_FILE"

{
    echo "config=$CONFIG"
    echo "benchmark=$BENCHMARK"
    echo "scenario=$SCENARIO"
    echo "run_id=$RUN_ID"
    echo "n_dim=$N_DIM"
    echo "atoms=$((N_DIM * N_DIM * N_DIM))"
    echo "steps=$STEPS"
    echo "ranks=1"
    echo "threads=1"
    echo "datafile=$DATAFILE"
    echo "input_file=$INPUT_FILE"
    echo "lammps_bin=$LAMMPS_BIN"
    echo "command=$(cat "$COMMAND_FILE")"
} > "$CONFIG_FILE"

echo
echo "============================================================"
echo "Running LAMMPS force-kernel benchmark"
echo "============================================================"
echo "Result directory:"
echo "  $RESULT_DIR"
echo "Command:"
echo "  $(cat "$COMMAND_FILE")"
echo

START_NS="$(date +%s%N)"

set +e
(
    cd "$RESULT_DIR"
    "${RUN_CMD[@]}" "${LAMMPS_ARGS[@]}"
) > "$STDOUT_FILE" 2> "$STDERR_FILE"
STATUS="$?"
set -e

END_NS="$(date +%s%N)"
ELAPSED_NS="$((END_NS - START_NS))"
WALL_SECONDS="$(awk "BEGIN { printf \"%.6f\", ${ELAPSED_NS} / 1000000000 }")"

{
    echo
    echo "Wall Time Seconds: $WALL_SECONDS"
    echo "Exit Status: $STATUS"
} >> "$META_FILE"

if [[ "$STATUS" -ne 0 ]]; then
    echo "LAMMPS failed with exit status $STATUS" >&2
    echo "stdout: $STDOUT_FILE" >&2
    echo "stderr: $STDERR_FILE" >&2
    exit "$STATUS"
fi

PAIR_TIME="$(
    awk -F'|' '
        /^Pair[[:space:]]*\|/ {
            val=$3
            gsub(/^[ \t]+|[ \t]+$/, "", val)
        }
        END {
            if (val != "") print val
        }
    ' "$STDOUT_FILE"
)"

NEIGHBORS="$(
    awk '
        /^Total # of neighbors =/ {
            val=$6
        }
        END {
            if (val != "") print val
        }
    ' "$STDOUT_FILE"
)"

if [[ -z "$PAIR_TIME" ]]; then
    echo "ERROR: Could not parse Pair time from: $STDOUT_FILE" >&2
    exit 1
fi

if [[ -z "$NEIGHBORS" ]]; then
    echo "ERROR: Could not parse Total # of neighbors from: $STDOUT_FILE" >&2
    exit 1
fi

read -r NS_PER_INTERACTION INTERACTIONS_PER_SECOND < <(
    python3 - <<EOF
pair_time = float("$PAIR_TIME")
neighbors = float("$NEIGHBORS")
steps = float("$STEPS")

ns_per_interaction = pair_time * 1.0e9 / (steps * neighbors)
interactions_per_second = steps * neighbors / pair_time

print(f"{ns_per_interaction:.9g} {interactions_per_second:.9g}")
EOF
)

{
    echo "config=$CONFIG"
    echo "benchmark=$BENCHMARK"
    echo "scenario=$SCENARIO"
    echo "run_id=$RUN_ID"
    echo "n_dim=$N_DIM"
    echo "atoms=$((N_DIM * N_DIM * N_DIM))"
    echo "steps=$STEPS"
    echo "pair_time_s=$PAIR_TIME"
    echo "neighbors_per_step=$NEIGHBORS"
    echo "ns_per_interaction=$NS_PER_INTERACTION"
    echo "interactions_per_second=$INTERACTIONS_PER_SECOND"
    echo "wall_time_s=$WALL_SECONDS"
} > "$METRICS_FILE"

cat "$METRICS_FILE" >> "$META_FILE"

echo "Done."
echo "stdout:        $STDOUT_FILE"
echo "stderr:        $STDERR_FILE"
echo "meta:          $META_FILE"
echo "configuration: $CONFIG_FILE"
echo "metrics:       $METRICS_FILE"
echo
cat "$METRICS_FILE"