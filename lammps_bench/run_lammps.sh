#!/bin/bash
set -e

# --- Configuration ---
PROJECT_ROOT="$(pwd)/.."
INTEL_BIN="${PROJECT_ROOT}/lammps/build_intel/lmp"
KOKKOS_BIN="${PROJECT_ROOT}/lammps/build_kokkos/lmp"
INPUT_FILE="./in.argon_block"

# --- Usage ---
usage() {
    echo "Usage: $0 <intel|kokkos> <threads> <n> <rho> <steps>"
    echo "Example: $0 intel 32 100 0.8 500"
    exit 1
}

if [ "$#" -ne 5 ]; then usage; fi

BACKEND=$1
THREADS=$2
N_DIM=$3
RHO=$4
STEPS=$5

# --- Environment Setup ---
export OMP_NUM_THREADS=$THREADS
export OMP_PLACES=cores
export OMP_PROC_BIND=close

# --- Execution Logic ---
case $BACKEND in
    intel)
        if [ ! -f "$INTEL_BIN" ]; then echo "Error: Intel binary not found!"; exit 1; fi
        echo "--- Running LAMMPS INTEL: T=$THREADS, N=$N_DIM, Rho=$RHO ---"
        
        # -sf intel: Use vectorized kernels
        # -pk intel 0: Use internal thread management
        # lrt yes: Enable Long Range Threading for neighbor builds
        numactl --localalloc "$INTEL_BIN" \
            -in "$INPUT_FILE" \
            -var n "$N_DIM" -var rho "$RHO" -var steps "$STEPS" \
            -sf intel \
            -pk intel 0 mode double omp "$THREADS" lrt no
        ;;

    kokkos)
        if [ ! -f "$KOKKOS_BIN" ]; then echo "Error: Kokkos binary not found!"; exit 1; fi
        echo "--- Running LAMMPS KOKKOS: T=$THREADS, N=$N_DIM, Rho=$RHO ---"
        
        # -k on: Initialize Kokkos
        # t $THREADS: Set OpenMP thread count for Kokkos backend
        # -sf kk: Use Kokkos-vectorized styles
        numactl --localalloc "$KOKKOS_BIN" \
            -k on t "$THREADS" -sf kk \
            -in "$INPUT_FILE" \
            -var n "$N_DIM" -var rho "$RHO" -var steps "$STEPS"
        ;;

    *)
        usage
        ;;
esac