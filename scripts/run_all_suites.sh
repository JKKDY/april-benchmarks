#!/usr/bin/env bash
set -euo pipefail

# Optional shared thread list for suite runs
# export ARGON_THREADS="${ARGON_THREADS:-1 2 4 8 16 32 56}"

# -------------------------
# APRIL
# -------------------------

./scripts/run_april_suite.sh native
ARGON_EXECUTOR=NativeSpinExecutor ./scripts/run_april_suite.sh native
ARGON_ORDERING=hilbert ./scripts/run_april_suite.sh native


./scripts/run_april_suite.sh native-novec
./scripts/run_april_suite.sh native-gcc
./scripts/run_april_suite.sh sse

./scripts/run_april_suite.sh native # running twice to gauge variability


ARGON_ORDERING=none ./scripts/run_april_suite.sh
ARGON_DT=0.0000001 ./scripts/run_april_suite.sh


# -------------------------
# LAMMPS
# -------------------------

./scripts/run_lammps_suite.sh openmp-generic
./scripts/run_lammps_suite.sh openmp-native

LAMMPS_MPI_RANKS_MODE=threads ./scripts/run_lammps_suite.sh intel-native
LAMMPS_MPI_RANKS_MODE=mpi     ./scripts/run_lammps_suite.sh intel-native
LAMMPS_MPI_RANKS_MODE=mpi     ./scripts/run_lammps_suite.sh intel-generic

ARGON_DT=0.0000001 ./scripts/run_lammps_suite.sh openmp-native




