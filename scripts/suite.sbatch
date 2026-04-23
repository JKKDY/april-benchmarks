#!/usr/bin/env bash
#SBATCH -J benchmark_suite
#SBATCH -D .
#SBATCH -o ./results/slurm/%x.%j.out
#SBATCH -e ./results/slurm/%x.%j.err
#SBATCH --get-user-env
#SBATCH --clusters=cm4
#SBATCH --partition=cm4_tiny
#SBATCH --qos=cm4_tiny
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=112
#SBATCH --time=04:00:00
#SBATCH --exclusive
#SBATCH --hint=nomultithread

set -euo pipefail

module load gcc/14.2.0 cmake ninja

cd "$SLURM_SUBMIT_DIR"

export OMP_PLACES=cores
export OMP_PROC_BIND=close
export OMP_DYNAMIC=FALSE

# Same sweep for APRIL and LAMMPS.
export ARGON_THREADS="${ARGON_THREADS:-1 2 3 4 6 8 11 16 23 32 45 56}"
export ARGON_N="${ARGON_N:-100}"
export ARGON_RHO="${ARGON_RHO:-0.8442}"
export ARGON_DT="${ARGON_DT:-0.005}"
export ARGON_STEPS="${ARGON_STEPS:-500}"

# LAMMPS defaults.
export LAMMPS_MPI_RANKS_MODE="${LAMMPS_MPI_RANKS_MODE:-threads}"
export LAMMPS_BIND="${LAMMPS_BIND:-close}"

APRIL_CONFIG="${APRIL_CONFIG:-native-autovec}"
LAMMPS_CONFIG="${LAMMPS_CONFIG:-openmp-serial-native}"

REPS="${REPS:-5}"
SUITE_BASE_TIME="${SUITE_BASE_TIME:-$(date +%Y%m%d_%H%M%S)}"

echo "============================================================"
echo "Combined APRIL + LAMMPS benchmark suite"
echo "============================================================"
echo "SLURM_JOB_ID:        ${SLURM_JOB_ID:-unset}"
echo "SLURM_CPUS_PER_TASK: ${SLURM_CPUS_PER_TASK:-unset}"
echo "APRIL_CONFIG:        $APRIL_CONFIG"
echo "LAMMPS_CONFIG:       $LAMMPS_CONFIG"
echo "REPS:                $REPS"
echo "SUITE_BASE_TIME:     $SUITE_BASE_TIME"
echo "ARGON_THREADS:       $ARGON_THREADS"
echo "ARGON_N:             $ARGON_N"
echo "ARGON_RHO:           $ARGON_RHO"
echo "ARGON_DT:            $ARGON_DT"
echo "ARGON_STEPS:         $ARGON_STEPS"
echo "LAMMPS_MODE:         $LAMMPS_MPI_RANKS_MODE"
echo "LAMMPS_BIND:         $LAMMPS_BIND"
echo

for i in $(seq 1 "$REPS"); do
    RUN_TAG="${SUITE_BASE_TIME}_rep${i}"

    echo
    echo "============================================================"
    echo "=== Combined run $i/$REPS : $RUN_TAG ==="
    echo "============================================================"

    echo
    echo "------------------------------------------------------------"
    echo "APRIL suite"
    echo "------------------------------------------------------------"
    SUITE_TIME="$RUN_TAG" \
    srun --cpu-bind=cores \
        ./scripts/run_april_suite.sh "$APRIL_CONFIG"

    echo
    echo "------------------------------------------------------------"
    echo "LAMMPS suite"
    echo "------------------------------------------------------------"
    SUITE_TIME="$RUN_TAG" \
    srun --cpu-bind=cores \
        ./scripts/run_lammps_suite.sh "$LAMMPS_CONFIG"
done

echo
echo "Done."
echo "APRIL results:"
echo "  results/april/${APRIL_CONFIG}/"
echo "LAMMPS results:"
echo "  results/lammps/${LAMMPS_CONFIG}/"