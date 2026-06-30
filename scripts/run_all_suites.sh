#!/usr/bin/env bash
set -euo pipefail

# Optional shared thread list for suite runs
export ARGON_THREADS="${ARGON_THREADS:-1 2 3 4 6 8 11 16 23 32 37 45 50 56}"

# -------------------------
# APRIL
# -------------------------

GB_REPETITIONS=10 \
GB_AGGREGATES_ONLY=false \
./scripts/run_april_suite.sh --only force native-novec

GB_REPETITIONS=10 \
GB_AGGREGATES_ONLY=false \
./scripts/run_april_suite.sh --only hardcoded native

ARGON_DT=0.005 \
ARGON_STRONG_REPEATS=3 \
./scripts/run_april_suite.sh --only strong native

ARGON_DT=0.0000001 \
ARGON_STRONG_REPEATS=3 \
./scripts/run_april_suite.sh --only strong native

# # -------------------------
# # LAMMPS
# # -------------------------

ARGON_DT=0.005 \
LAMMPS_FORCE_REPEATS=3 \
LAMMPS_ARGON_REPEATS=3 \
ARGON_DT=0.005 \
./scripts/run_lammps_suite.sh --only both openmp-native

LAMMPS_FORCE_REPEATS=3 \
LAMMPS_ARGON_REPEATS=3 \
ARGON_DT=0.0000001 \
LAMMPS_MPI_RANKS_MODE=threads \
./scripts/run_lammps_suite.sh --only both openmp-native












