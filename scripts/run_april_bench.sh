#!/bin/bash
#SBATCH -J AprilInterBench
#SBATCH -o %j.out
#SBATCH -e %j.err
#SBATCH --clusters=inter        # MANDATORY for cm4_inter
#SBATCH -p cm4_inter           # Partition name
#SBATCH -t 00:20:00            # Reduced to 20m for faster queue turnaround
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1    # One application instance
#SBATCH --cpus-per-task=32     # 32 logical cores
#SBATCH --sockets-per-node=1   # Force all threads onto one physical CPU socket
#SBATCH --mem=16G              # Memory limit
#SBATCH --get-user-env         # Recommended by LRZ to propagate environment

module load gcc/14.2.0 cmake ninja


PROJECT_ROOT="$SLURM_SUBMIT_DIR"
BUILD_DIR="${PROJECT_ROOT}/april_bench_build"


cd "$BUILD_DIR"

# 3. Build on the compute node (targets current CPU)
echo "--- Starting Ninja Build on $(hostname) ---"
ninja -j "$SLURM_CPUS_PER_TASK"

# 4. Run Benchmark
echo "--- Starting Benchmark ---"
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export OMP_PLACES=cores
export OMP_PROC_BIND=close
export OMP_DISPLAY_ENV=VERBOSE

numactl --localalloc ./april_bench/argon_block