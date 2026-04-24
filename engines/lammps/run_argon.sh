#!/usr/bin/env bash
set -euo pipefail

module load llvm/20.1.2

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

  --n N                 particles per dimension, default: 100
  --rho RHO             density, default: 0.8442
  --steps STEPS         timed benchmark steps, default: 500
  --dt DT               timestep, default: 0.001
  --threads T           OpenMP threads, default: 1
  --ranks R             MPI ranks, default: 1
  --datafile FILE       optional datafile path
  --no-generate         do not regenerate datafile
  --bind close|spread   OpenMP binding, default: close
  --help                show this help

Environment:
  SCENARIO              scenario folder name
  RUN_ID                run folder name, default: timestamp
  RESULT_ROOT           override result root, default: <repo>/results/lammps

Examples:
  $0 --config openmp-native --n 100 --steps 500 --dt 0.001 --threads 8

  $0 --config intel-native --n 100 --steps 500 --dt 0.001 --ranks 4 --threads 1
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
N_DIM="100"
RHO="0.8442"
STEPS="500"
DT="0.001"
THREADS="1"
RANKS="1"
DATAFILE=""
GENERATE="yes"
BIND="close"

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
        --rho)
            RHO="$2"
            shift 2
            ;;
        --steps)
            STEPS="$2"
            shift 2
            ;;
        --dt)
            DT="$2"
            shift 2
            ;;
        --threads)
            THREADS="$2"
            shift 2
            ;;
        --ranks)
            RANKS="$2"
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
        --bind)
            BIND="$2"
            shift 2
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

case "$BIND" in
    close|spread)
        ;;
    *)
        echo "Invalid --bind value: $BIND" >&2
        echo "Expected: close or spread" >&2
        exit 1
        ;;
esac

CONFIG_SAFE="$(sanitize_path_component "$CONFIG")"
BENCHMARK="argon_block"
SCENARIO="$(sanitize_path_component "${SCENARIO:-n${N_DIM}_rho${RHO}_dt${DT}_steps${STEPS}_r${RANKS}_t${THREADS}}")"
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
INPUT_FILE="${SCRIPT_DIR}/argon_block.in"
GRID_SCRIPT="${SCRIPT_DIR}/make_argon_grid.py"

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
    DATAFILE="${RESULT_DIR}/argon_grid_n${N_DIM}_rho${RHO}.data"
else
    DATAFILE="$(realpath "$DATAFILE")"
fi

if [[ "$GENERATE" == "yes" ]]; then
    echo "Generating argon grid:"
    echo "  n_dim    = $N_DIM"
    echo "  rho      = $RHO"
    echo "  datafile = $DATAFILE"
    python3 "$GRID_SCRIPT" "$N_DIM" "$RHO" "$DATAFILE" | tee "${RESULT_DIR}/grid_generation.log"
else
    if [[ ! -f "$DATAFILE" ]]; then
        echo "Datafile does not exist and --no-generate was given: $DATAFILE" >&2
        exit 1
    fi
fi

export OMP_NUM_THREADS="$THREADS"
export OMP_PLACES=cores
export OMP_PROC_BIND="$BIND"
export OMP_DYNAMIC=FALSE

LAMMPS_ARGS=(
    -in "$INPUT_FILE"
    -var datafile "$DATAFILE"
    -var rho "$RHO"
    -var n "$N_DIM"
    -var steps "$STEPS"
    -var dt "$DT"
)

RUN_CMD=()

case "$CONFIG" in
    openmp-generic|openmp-native)
        module load llvm/20.1.2
        LAMMPS_ARGS+=(-sf omp -pk omp "$THREADS")
        RUN_CMD=("$LAMMPS_BIN")
        ;;

    intel-generic|intel-native)
        module load intel intel-mpi intel-mkl intel-oneapi-tbb

        export KMP_AFFINITY=granularity=fine,compact,1,0
        export KMP_BLOCKTIME=0

        # mode double keeps Intel-package runs closer to normal LAMMPS precision.
        LAMMPS_ARGS+=(-sf intel -pk intel "$THREADS" mode double)
        RUN_CMD=(mpirun -np "$RANKS" "$LAMMPS_BIN")
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
    echo "rho: $RHO"
    echo "steps: $STEPS"
    echo "dt: $DT"
    echo "ranks: $RANKS"
    echo "threads: $THREADS"
    echo "bind: $BIND"
    echo "Command: $(cat "$COMMAND_FILE")"
    echo "Benchmark Repo Commit: $(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
    echo
    echo "Environment:"
    echo "  OMP_NUM_THREADS=${OMP_NUM_THREADS:-unset}"
    echo "  OMP_PLACES=${OMP_PLACES:-unset}"
    echo "  OMP_PROC_BIND=${OMP_PROC_BIND:-unset}"
    echo "  OMP_DYNAMIC=${OMP_DYNAMIC:-unset}"
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
    echo "rho=$RHO"
    echo "steps=$STEPS"
    echo "dt=$DT"
    echo "ranks=$RANKS"
    echo "threads=$THREADS"
    echo "bind=$BIND"
    echo "datafile=$DATAFILE"
    echo "input_file=$INPUT_FILE"
    echo "lammps_bin=$LAMMPS_BIN"
    echo "command=$(cat "$COMMAND_FILE")"
} > "$CONFIG_FILE"

echo
echo "============================================================"
echo "Running LAMMPS argon benchmark"
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

# Parse the last real benchmark loop.
LOOP_TIME="$(
    awk '
        /^Loop time of/ {
            val=$4
        }
        END {
            if (val != "") print val
        }
    ' "$STDOUT_FILE"
)"

TIMESTEPS_PER_SECOND="$(
    awk '
        /timesteps\/s/ {
            for (i = 1; i <= NF; ++i) {
                if ($i == "timesteps/s") {
                    val=$(i-1)
                }
            }
        }
        END {
            if (val != "") print val
        }
    ' "$STDOUT_FILE"
)"

MATOM_STEP_PER_SECOND="$(
    awk '
        /Matom-step\/s/ {
            for (i = 1; i <= NF; ++i) {
                if ($i == "Matom-step/s") {
                    val=$(i-1)
                }
            }
        }
        END {
            if (val != "") print val
        }
    ' "$STDOUT_FILE"
)"

CPU_USE_PERCENT="$(
    awk '
        /CPU use with/ {
            val=$1
        }
        END {
            if (val != "") print val
        }
    ' "$STDOUT_FILE"
)"

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

NEIGH_TIME="$(
    awk -F'|' '
        /^Neigh[[:space:]]*\|/ {
            val=$3
            gsub(/^[ \t]+|[ \t]+$/, "", val)
        }
        END {
            if (val != "") print val
        }
    ' "$STDOUT_FILE"
)"

COMM_TIME="$(
    awk -F'|' '
        /^Comm[[:space:]]*\|/ {
            val=$3
            gsub(/^[ \t]+|[ \t]+$/, "", val)
        }
        END {
            if (val != "") print val
        }
    ' "$STDOUT_FILE"
)"

MODIFY_TIME="$(
    awk -F'|' '
        /^Modify[[:space:]]*\|/ {
            val=$3
            gsub(/^[ \t]+|[ \t]+$/, "", val)
        }
        END {
            if (val != "") print val
        }
    ' "$STDOUT_FILE"
)"

TOTAL_NEIGHBORS="$(
    awk '
        /^Total # of neighbors =/ {
            val=$6
        }
        END {
            if (val != "") print val
        }
    ' "$STDOUT_FILE"
)"

NEIGHBOR_BUILDS="$(
    awk '
        /^Neighbor list builds =/ {
            val=$5
        }
        END {
            if (val != "") print val
        }
    ' "$STDOUT_FILE"
)"

{
    echo "config=$CONFIG"
    echo "benchmark=$BENCHMARK"
    echo "scenario=$SCENARIO"
    echo "run_id=$RUN_ID"
    echo "n_dim=$N_DIM"
    echo "atoms=$((N_DIM * N_DIM * N_DIM))"
    echo "rho=$RHO"
    echo "steps=$STEPS"
    echo "dt=$DT"
    echo "ranks=$RANKS"
    echo "threads=$THREADS"
    echo "bind=$BIND"
    echo "loop_time_s=${LOOP_TIME:-unknown}"
    echo "timesteps_per_second=${TIMESTEPS_PER_SECOND:-unknown}"
    echo "matom_step_per_second=${MATOM_STEP_PER_SECOND:-unknown}"
    echo "cpu_use_percent=${CPU_USE_PERCENT:-unknown}"
    echo "pair_time_s=${PAIR_TIME:-unknown}"
    echo "neigh_time_s=${NEIGH_TIME:-unknown}"
    echo "comm_time_s=${COMM_TIME:-unknown}"
    echo "modify_time_s=${MODIFY_TIME:-unknown}"
    echo "total_neighbors=${TOTAL_NEIGHBORS:-unknown}"
    echo "neighbor_list_builds=${NEIGHBOR_BUILDS:-unknown}"
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