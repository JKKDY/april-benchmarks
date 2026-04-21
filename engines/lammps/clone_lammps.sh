#!/bin/bash
set -e

PROJECT_ROOT=$(pwd)
LAMMPS_DIR="${PROJECT_ROOT}/lammps"
LAMMPS_TAG="stable_22Jul2025_update3"

# 1. Shared Repository with pinned stable release
if [ ! -d "$LAMMPS_DIR" ]; then
    echo "Cloning LAMMPS ($LAMMPS_TAG)..."
    git clone --depth 1 -b "$LAMMPS_TAG" https://github.com/lammps/lammps.git "$LAMMPS_DIR"
fi