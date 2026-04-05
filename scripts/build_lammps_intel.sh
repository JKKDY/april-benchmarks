#!/bin/bash
set -e

# 1. CoolMUC-4 Environment Setup
module load intel
module load intel-mpi
module load intel-mkl
module load intel-oneapi-tbb
module load cmake
module load ninja

echo "==========================================="
echo " Building LAMMPS (USER-INTEL) for CoolMUC-4"
echo "==========================================="

PROJECT_ROOT=$(pwd)
LAMMPS_DIR="${PROJECT_ROOT}/lammps"

mkdir -p "${LAMMPS_DIR}/build_intel"
cd "${LAMMPS_DIR}/build_intel"

# Use Ninja for faster builds (-G Ninja)
cmake ../cmake -G Ninja \
  -D CMAKE_C_COMPILER=mpiicx \
  -D CMAKE_CXX_COMPILER=mpiicpx \
  -D BUILD_MPI=yes \
  -D BUILD_OMP=yes \
  -D PKG_INTEL=yes \
  -D PKG_OPENMP=yes \
  -D INTEL_ARCH=cpu \
  -D INTEL_LRT=yes \
  -D LAMMPS_FP_MODEL="fast" \
  -D CMAKE_CXX_FLAGS="-O3 -xHost -qopenmp -qopt-zmm-usage=high -ffast-math" \
  -D CMAKE_BUILD_TYPE=Release

# Build using Ninja
echo "Compiling with $(nproc) cores via Ninja..."
ninja -j 32

echo "Done! Executable is at: $(pwd)/lmp"