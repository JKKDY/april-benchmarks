#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

EXTERNAL_DIR="${PROJECT_ROOT}/external"

APRIL_REPO="${APRIL_REPO:-https://github.com/JKKDY/april.git}"
APRIL_REF="${APRIL_REF:-dev}"
APRIL_DIR="${EXTERNAL_DIR}/april"

GBENCH_REPO="${GBENCH_REPO:-https://github.com/google/benchmark.git}"
GBENCH_REF="${GBENCH_REF:-v1.8.3}"
GBENCH_DIR="${EXTERNAL_DIR}/googlebenchmark"

XSIMD_REPO="${XSIMD_REPO:-https://github.com/xtensor-stack/xsimd.git}"
XSIMD_REF="${XSIMD_REF:-master}"
XSIMD_DIR="${EXTERNAL_DIR}/xsimd"

mkdir -p "$EXTERNAL_DIR"

fetch_repo() {
    local name="$1"
    local repo="$2"
    local ref="$3"
    local dir="$4"

    echo "============================================================"
    echo "Fetching $name"
    echo "  repo: $repo"
    echo "  ref:  $ref"
    echo "  dir:  $dir"
    echo "============================================================"

    if [[ ! -d "$dir/.git" ]]; then
        git clone "$repo" "$dir"
    fi

    git -C "$dir" fetch --tags --prune
    git -C "$dir" checkout "$ref"

    echo "$name commit: $(git -C "$dir" rev-parse HEAD)"
}

fetch_repo "April" "$APRIL_REPO" "$APRIL_REF" "$APRIL_DIR"
fetch_repo "Google Benchmark" "$GBENCH_REPO" "$GBENCH_REF" "$GBENCH_DIR"
fetch_repo "xsimd" "$XSIMD_REPO" "$XSIMD_REF" "$XSIMD_DIR"

INFO_FILE="${EXTERNAL_DIR}/dependency_info.txt"

{
    echo "Dependency Fetch Date: $(date --iso-8601=seconds)"
    echo
    echo "April:"
    echo "  Repo: $APRIL_REPO"
    echo "  Ref: $APRIL_REF"
    echo "  Commit: $(git -C "$APRIL_DIR" rev-parse HEAD)"
    echo
    echo "Google Benchmark:"
    echo "  Repo: $GBENCH_REPO"
    echo "  Ref: $GBENCH_REF"
    echo "  Commit: $(git -C "$GBENCH_DIR" rev-parse HEAD)"
} > "$INFO_FILE"

echo
echo "Dependencies fetched."
echo "Info written to: $INFO_FILE"