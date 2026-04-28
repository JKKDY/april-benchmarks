#!/usr/bin/env bash
set -euo pipefail

# Optional shared thread list for suite runs
export ARGON_THREADS="${ARGON_THREADS:-1 2 3 4 6 8 11 16 23 32 37 45 50 56}"

# -------------------------
# APRIL
# -------------------------

./scripts/run_april_suite.sh native
./scripts/run_april_suite.sh native-novec
./scripts/run_april_suite.sh native-gcc

ARGON_EXECUTOR=NativeSpinExecutor ./scripts/run_april_suite.sh native
ARGON_ORDERING=none ./scripts/run_april_suite.sh native

ARGON_LAYOUT=AoS ./scripts/run_april_suite.sh native
ARGON_LAYOUT=AoSoA ./scripts/run_april_suite.sh native

./scripts/run_april_suite.sh native # running a second time to gauge variability

ARGON_BX=4 ARGON_BY=4 ARGON_BZ=4 ./scripts/run_april_suite.sh native
ARGON_DT=0.0000001 ./scripts/run_april_suite.sh native

ARGON_STEPS=200 ARGON_N=160 ./scripts/run_april_suite.sh native

# -------------------------
# LAMMPS
# -------------------------


./scripts/run_lammps_suite.sh openmp-generic
./scripts/run_lammps_suite.sh openmp-native
./scripts/run_lammps_suite.sh openmp-native

LAMMPS_MPI_RANKS_MODE=threads ./scripts/run_lammps_suite.sh intel-native
LAMMPS_MPI_RANKS_MODE=mpi     ./scripts/run_lammps_suite.sh intel-native
LAMMPS_MPI_RANKS_MODE=mpi     ./scripts/run_lammps_suite.sh intel-generic

ARGON_DT=0.0000001 ./scripts/run_lammps_suite.sh openmp-native
ARGON_DT=0.0000001 ./scripts/run_lammps_suite.sh intel-native

ARGON_STEPS=200 ARGON_N=160 ./scripts/run_lammps_suite.sh openmp-generic












