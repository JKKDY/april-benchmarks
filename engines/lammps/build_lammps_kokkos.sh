#!/bin/bash
set -e

# 1. CoolMUC-4 Environment Setup
module load gcc/14.2.0
module load openmpi # Or whatever MPI module goes with GCC on your system
module load cmake
module load ninja

echo "==========================================="
echo " Building LAMMPS (KOKKOS) for CoolMUC-4   "
echo "==========================================="

PROJECT_ROOT=$(pwd)
LAMMPS_DIR="${PROJECT_ROOT}/lammps"

mkdir -p "${LAMMPS_DIR}/build_kokkos"
cd "${LAMMPS_DIR}/build_kokkos"

# Use Ninja for faster builds (-G Ninja)
cmake ../cmake -G Ninja \
  -D CMAKE_CXX_COMPILER=mpicxx \
  -D CMAKE_C_COMPILER=mpicc \
  -D BUILD_MPI=yes \
  -D BUILD_OMP=yes \
  -D PKG_KOKKOS=yes \
  -D Kokkos_ENABLE_SERIAL=yes \
  -D Kokkos_ENABLE_OPENMP=yes \
  -D Kokkos_ARCH_SPR=ON \
  -D CMAKE_CXX_FLAGS="-O3 -march=native -ffast-math" \
  -D CMAKE_BUILD_TYPE=Release

# Build using Ninja
echo "Compiling with $(nproc) cores via Ninja..."
ninja -j 32

echo "Done! Executable is at: $(pwd)/lmp"