#!/bin/bash
# --- CoolMUC-4 Environment Setup ---
module load intel
module load intel-mkl
module load intel-mpi
module load intel-oneapi-tbb
module load gcc/14.2.0
module load cmake
module load ninja

# --- Path Configuration ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BENCH_DIR="${PROJECT_ROOT}/lammps_bench"
OUTPUT_CSV="${PROJECT_ROOT}/bench_results/lammps_results.csv"

# --- Benchmark Settings ---
# BACKENDS=("intel" "kokkos")
BACKENDS=("intel")
THREADS=(1 2 4 8 16 24 32)
N_DIM=100
RHO=0.8
STEPS=500
N_PARTICLES=$((N_DIM * N_DIM * N_DIM))

mkdir -p "${PROJECT_ROOT}/bench_results"
echo "Backend,Threads,Time_Sec,MUPS" > "$OUTPUT_CSV"

echo "------------------------------------------------------------"
echo " Starting LAMMPS Suite (N=$N_PARTICLES)"
echo "------------------------------------------------------------"

cd "$BENCH_DIR"

for backend in "${BACKENDS[@]}"; do
    
    export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(dirname $(which icpx))/../lib:$(dirname $(which icpx))/../lib/intel64
    for t in "${THREADS[@]}"; do
        echo -n "Running $backend | T=$t... "

        # Capture run output
        ./run_lammps.sh "$backend" "$t" "$N_DIM" "$RHO" "$STEPS" > "last_run.log" 2>&1
        
        # FIX: We use 'tail -n 1' to ensure we only get the FINAL production loop time
        # and 'tr' to remove any carriage returns or extra whitespace
        LTIME=$(grep "Loop time of" last_run.log | tail -n 1 | awk '{print $4}' | tr -d '\r\n ')

        # Sanity check: Ensure LTIME is actually a number
        if [[ ! "$LTIME" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
            echo "FAILED (Parsed time: '$LTIME')"
            continue
        fi

        # Perform math using bc
        MUPS=$(echo "scale=4; ($N_PARTICLES * $STEPS) / ($LTIME * 1000000)" | bc -l)

        # Log and Print
        echo "$backend,$t,$LTIME,$MUPS" >> "$OUTPUT_CSV"
        printf "Time: %8.2fs | MUPS: %8.4f\n" "$LTIME" "$MUPS"
    done
done