#!/bin/bash
set -e

# --- Configuration ---
PROJECT_ROOT="$(pwd)/.."
INTEL_BIN="${PROJECT_ROOT}/lammps/build_intel/lmp"
KOKKOS_BIN="${PROJECT_ROOT}/lammps/build_kokkos/lmp"
INPUT_FILE="./in.argon_block"

# --- Usage ---
usage() {
    echo "Usage: $0 <intel|kokkos> <physical_cores> <n> <rho> <steps>"
    echo "Example: $0 intel 32 100 0.8 500"
    exit 1
}

if [ "$#" -ne 5 ]; then usage; fi

BACKEND=$1
CORES=$2
N_DIM=$3
RHO=$4
STEPS=$5

# --- Execution Logic ---
case $BACKEND in
    intel)
        if [ ! -f "$INTEL_BIN" ]; then echo "Error: Intel binary not found!"; exit 1; fi
        echo "--- Running LAMMPS INTEL: Cores=$CORES (MPI=$CORES, OMP=1), N=$N_DIM, Rho=$RHO ---"
        
        # 1. Load Intel Environment
        module load intel intel-mpi intel-mkl intel-oneapi-tbb

        # 2. Intel-Specific Thread & Affinity Setup
        # export KMP_BLOCKTIME=0
        # export KMP_AFFINITY=granularity=fine,compact,1,0
        # export MKL_NUM_THREADS=1
        # export OMP_NUM_THREADS=1  # 2 threads per MPI task to use SMT/Hyperthreading
        export OMP_NUM_THREADS="$CORES"
        export OMP_PROC_BIND=close
        export OMP_PLACES=cores
        export KMP_SETTINGS=1
        export KMP_AFFINITY=verbose,granularity=fine,compact,1,0
        # export KMP_AFFINITY=granularity=fine,spread
        # export I_MPI_PIN=off

        # 3. Launch via MPI
        mpirun -np 1 --bind-to none numactl --localalloc "$INTEL_BIN" \
            -in "$INPUT_FILE" \
            -var n "$N_DIM" -var rho "$RHO" -var steps "$STEPS" \
            -sf intel \
            -pk intel 0 mode double omp "$CORES" lrt no
        ;;
    omp)
        # We use the standard binary but with the OPENMP package flags
        # Use -np 1 to kill MPI domain decomposition (Fair comparison)
        echo "--- Running LAMMPS OPENMP: Threads=$CORES (Single Rank), N=$N_DIM, Rho=$RHO ---"
        
        module load intel intel-mpi intel-mkl intel-oneapi-tbb


        export OMP_NUM_THREADS="$CORES"
        export OMP_PROC_BIND=close
        export OMP_PLACES=cores
         export KMP_SETTINGS=1
        export KMP_AFFINITY=verbose,granularity=fine,compact,1,0

        # -sf omp: Use the OpenMP package styles
        # -pk omp $CORES: Allocate X threads to the OpenMP package
        # -var newton off: Use this if your library does NOT use Newton's 3rd law
        mpirun -np 1 --bind-to none numactl --localalloc "$INTEL_BIN" \
            -in "$INPUT_FILE" \
            -var n "$N_DIM" -var rho "$RHO" -var steps "$STEPS" \
            -sf omp \
            -pk omp "$CORES"
        ;;

    kokkos)
        if [ ! -f "$KOKKOS_BIN" ]; then echo "Error: Kokkos binary not found!"; exit 1; fi
        echo "--- Running LAMMPS KOKKOS: T=$CORES, N=$N_DIM, Rho=$RHO ---"
        
        module load gcc/14.2.0
        module load openmpi 

        # 2. Strict MPI-Only Setup (Kills the OpenMP Thrashing)
        export OMP_NUM_THREADS="$CORES"
        export OMP_PLACES=cores
        export OMP_PROC_BIND=close

        # -k on: Initialize Kokkos
        # t $THREADS: Set OpenMP thread count for Kokkos backend
        # -sf kk: Use Kokkos-vectorized styles
        mpirun -np 1 --bind-to none numactl --localalloc "$KOKKOS_BIN" \
            -k on t "$CORES" -sf kk \
            -in "$INPUT_FILE" \
            -var n "$N_DIM" -var rho "$RHO" -var steps "$STEPS"
        ;;

    *)
        usage
        ;;

        
esac
