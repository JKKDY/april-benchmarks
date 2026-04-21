#!/usr/bin/env bash
set -euo pipefail

# Run one April benchmark binary once.
#
# Result layout:
#   results/april/<config>/<benchmark>/<scenario>/<time>/
#
# Usage:
#   engines/april/run.sh <variant> <binary> [binary args...]
#
# Examples:
#   engines/april/run.sh native-novec force_kernel_bench
#   engines/april/run.sh native-novec april_vs_hardcoded
#   SCENARIO=n32_rho0.8442_t8 engines/april/run.sh native-novec argon_block 32 0.8442 0.001 8 1000 2 2 2 C08 SoA NativeSpinExecutor
#
# Optional environment variables:
#   SCENARIO     Scenario folder name. Default: default
#   RUN_ID       Time/run folder name. Default: current timestamp
#   RESULT_ROOT  Override result root directory. Default: <repo>/results/april

module load gcc/14.2.0 cmake ninja

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() {
    cat >&2 <<EOF
Usage:
  $0 <variant> <binary> [binary args...]

Result layout:
  results/april/<config>/<benchmark>/<scenario>/<time>/

Variant examples:
  scalar-novec
  sse-novec
  avx2-novec
  avx512-novec
  native-novec
  native-autovec

Examples:
  $0 native-novec force_kernel_bench
  $0 native-novec april_vs_hardcoded
  SCENARIO=n32_rho0.8442_t8 $0 native-novec argon_block 32 0.8442 0.001 8 1000 2 2 2 C08 SoA NativeSpinExecutor

Argon positional arguments:
  n rho dt threads steps [bx by bz] [schedule] [layout] [executor]

Argon example:
  $0 native-novec argon_block 32 0.8442 0.001 8 1000 2 2 2 C08 SoA NativeSpinExecutor

Known schedules:
  C01 C08 C18 C27 C64 C02_Z C04_XY

Known layouts:
  SoA AoS AoSoA

Known executors:
  NativeSpinExecutor NativeBarrierExecutor OmpExecutor
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

if [[ $# -lt 2 ]]; then
    usage
fi

VARIANT="$1"
BINARY_NAME="$2"
shift 2

CONFIG="$(sanitize_path_component "$VARIANT")"
BENCHMARK="$(sanitize_path_component "$BINARY_NAME")"
SCENARIO="$(sanitize_path_component "${SCENARIO:-default}")"
RUN_ID="$(sanitize_path_component "${RUN_ID:-$(date +%Y%m%d_%H%M%S)}")"

BUILD_DIR="${PROJECT_ROOT}/build/april-${VARIANT}"
BIN="${BUILD_DIR}/bin/${BINARY_NAME}"

if [[ ! -d "$BUILD_DIR" ]]; then
    echo "Build directory not found: $BUILD_DIR" >&2
    echo "Did you build this variant?" >&2
    exit 1
fi

if [[ ! -x "$BIN" ]]; then
    echo "Binary not found or not executable: $BIN" >&2
    echo "Available binaries:" >&2
    find "$BUILD_DIR/bin" -maxdepth 1 -type f -perm -u+x -printf "  %f\n" 2>/dev/null || true
    exit 1
fi

RESULT_BASE="${RESULT_ROOT:-${PROJECT_ROOT}/results/april}"
RESULT_DIR="${RESULT_BASE}/${CONFIG}/${BENCHMARK}/${SCENARIO}/${RUN_ID}"

mkdir -p "$RESULT_DIR"

STDOUT_FILE="${RESULT_DIR}/stdout.log"
STDERR_FILE="${RESULT_DIR}/stderr.log"
META_FILE="${RESULT_DIR}/run_info.txt"
COMMAND_FILE="${RESULT_DIR}/command.txt"

printf "%q " "$BIN" "$@" > "$COMMAND_FILE"
printf "\n" >> "$COMMAND_FILE"

{
    echo "Engine: April"
    echo "Config: $CONFIG"
    echo "Variant: $VARIANT"
    echo "Benchmark: $BENCHMARK"
    echo "Binary: $BINARY_NAME"
    echo "Scenario: $SCENARIO"
    echo "Run ID: $RUN_ID"
    echo "Run Date: $(date --iso-8601=seconds)"
    echo "Hostname: $(hostname)"
    echo "Project Root: $PROJECT_ROOT"
    echo "Build Dir: $BUILD_DIR"
    echo "Result Dir: $RESULT_DIR"
    echo "Working Dir: $RESULT_DIR"
    echo "Command: $(cat "$COMMAND_FILE")"
    echo "Benchmark Repo Commit: $(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
    echo
    echo "Environment:"
    echo "  OMP_NUM_THREADS=${OMP_NUM_THREADS:-unset}"
    echo "  OMP_PLACES=${OMP_PLACES:-unset}"
    echo "  OMP_PROC_BIND=${OMP_PROC_BIND:-unset}"
    echo "  OMP_DYNAMIC=${OMP_DYNAMIC:-unset}"
    echo "  SLURM_JOB_ID=${SLURM_JOB_ID:-unset}"
    echo "  SLURM_CPUS_PER_TASK=${SLURM_CPUS_PER_TASK:-unset}"
    echo
    echo "Build Info:"
    if [[ -f "$BUILD_DIR/benchmark_info.txt" ]]; then
        cat "$BUILD_DIR/benchmark_info.txt"
    else
        echo "No benchmark_info.txt found"
    fi
} > "$META_FILE"

echo "Running:"
echo "  $(cat "$COMMAND_FILE")"
echo "Result directory:"
echo "  $RESULT_DIR"

START_NS="$(date +%s%N)"

(
    cd "$RESULT_DIR"
    if [[ -n "${RUN_PREFIX:-}" ]]; then
        # shellcheck disable=SC2086
        $RUN_PREFIX "$BIN" "$@" > "$STDOUT_FILE" 2> "$STDERR_FILE"
    else
        "$BIN" "$@" > "$STDOUT_FILE" 2> "$STDERR_FILE"
    fi
)

END_NS="$(date +%s%N)"
ELAPSED_NS="$((END_NS - START_NS))"

{
    echo
    echo "Wall Time Seconds: $(awk "BEGIN { printf \"%.6f\", ${ELAPSED_NS} / 1000000000 }")"
    echo "Exit Status: 0"
} >> "$META_FILE"

echo "Done."
echo "stdout: $STDOUT_FILE"
echo "stderr: $STDERR_FILE"
echo "meta:   $META_FILE"