#!/usr/bin/env bash
#SBATCH -J april_suite
#SBATCH -D .
#SBATCH -o %x.%j.out
#SBATCH -e %x.%j.err
#SBATCH --get-user-env
#SBATCH --clusters=cm4
#SBATCH --partition=cm4_tiny
#SBATCH --qos=cm4_tiny
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=112
#SBATCH --time=01:00:00
#SBATCH --exclusive
#SBATCH --hint=nomultithread

set -euo pipefail

module load gcc/14.2.0 cmake ninja
cd "$SLURM_SUBMIT_DIR"

export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export OMP_PLACES=cores
export OMP_PROC_BIND=close

for i in {1..5}; do
  echo "=== Run $i/5 ==="
  srun --cpu-bind=cores ./scripts/run_april_suite.sh
done