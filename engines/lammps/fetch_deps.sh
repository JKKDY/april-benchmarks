#!/usr/bin/env bash
set -euo pipefail

module load git || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

EXTERNAL_DIR="${PROJECT_ROOT}/external"
LAMMPS_DIR="${EXTERNAL_DIR}/lammps"

LAMMPS_REPO="${LAMMPS_REPO:-https://github.com/lammps/lammps.git}"
LAMMPS_REF="${LAMMPS_REF:-stable}"

mkdir -p "$EXTERNAL_DIR"

if [[ ! -d "$LAMMPS_DIR/.git" ]]; then
    git clone "$LAMMPS_REPO" "$LAMMPS_DIR"
fi

git -C "$LAMMPS_DIR" fetch --tags --prune
git -C "$LAMMPS_DIR" checkout "$LAMMPS_REF"

INFO_FILE="${EXTERNAL_DIR}/lammps_dependency_info.txt"
{
    echo "Dependency Fetch Date: $(date --iso-8601=seconds)"
    echo "LAMMPS Repo: $LAMMPS_REPO"
    echo "LAMMPS Ref: $LAMMPS_REF"
    echo "LAMMPS Commit: $(git -C "$LAMMPS_DIR" rev-parse HEAD)"
} > "$INFO_FILE"

echo "Fetched LAMMPS into: $LAMMPS_DIR"
echo "Info written to: $INFO_FILE"