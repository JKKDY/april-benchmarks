#!/usr/bin/env bash
set -euo pipefail

module load gcc/14.2.0 cmake ninja

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() {
    cat >&2 <<EOF
Usage:
  $0 <config> <benchmark> [args...]

Examples:
  $0 native argon_block 0.8442 32 500
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

CONFIG="$1"
BENCHMARK="$2"
shift 2

BUILD_DIR="${PROJECT_ROOT}/build/lammps-${CONFIG}"
LAMMPS_BIN="${BUILD_DIR}/lmp"

if [[ ! -x "$LAMMPS_BIN" ]]; then
    echo "LAMMPS binary not found: $LAMMPS_BIN" >&2
    exit 1
fi

RUN_ID="$(sanitize_path_component "${RUN_ID:-$(date +%Y%m%d_%H%M%S)}")"
SCENARIO="$(sanitize_path_component "${SCENARIO:-default}")"
RESULT_BASE="${RESULT_ROOT:-${PROJECT_ROOT}/results/lammps}"
RESULT_DIR="${RESULT_BASE}/${CONFIG}/${BENCHMARK}/${SCENARIO}/${RUN_ID}"

mkdir -p "$RESULT_DIR"

STDOUT_FILE="${RESULT_DIR}/stdout.log"
STDERR_FILE="${RESULT_DIR}/stderr.log"
META_FILE="${RESULT_DIR}/run_info.txt"
COMMAND_FILE="${RESULT_DIR}/command.txt"

case "$BENCHMARK" in
    argon_block)
        if [[ $# -lt 3 ]]; then
            echo "argon_block requires: <rho> <n> <steps>" >&2
            exit 1
        fi

        RHO="$1"
        N="$2"
        STEPS="$3"

        INPUT_FILE="${SCRIPT_DIR}/inputs/argon_block.in"

        CMD=(
            "$LAMMPS_BIN"
            -in "$INPUT_FILE"
            -var rho "$RHO"
            -var n "$N"
            -var steps "$STEPS"
        )
        ;;
    *)
        echo "Unknown benchmark: $BENCHMARK" >&2
        exit 1
        ;;
esac

printf "%q " "${CMD[@]}" > "$COMMAND_FILE"
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
    echo "Build Dir: $BUILD_DIR"
    echo "Result Dir: $RESULT_DIR"
    echo "Command: $(cat "$COMMAND_FILE")"
    echo "Benchmark Repo Commit: $(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
} > "$META_FILE"

echo "Running:"
echo "  $(cat "$COMMAND_FILE")"
echo "Result directory:"
echo "  $RESULT_DIR"

(
    cd "$RESULT_DIR"
    "${CMD[@]}" > "$STDOUT_FILE" 2> "$STDERR_FILE"
)

echo "Done."
echo "stdout: $STDOUT_FILE"
echo "stderr: $STDERR_FILE"
echo "meta:   $META_FILE"