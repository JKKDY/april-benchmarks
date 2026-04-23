#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LAMMPS_SOURCE_DIR="${PROJECT_ROOT}/external/lammps"

usage() {
    cat >&2 <<EOF
Usage:
  $0 [<config|all>]

Configs:
  openmp-generic
  openmp-native
  intel-generic
  intel-native
  all

Default:
  $0
    builds openmp-native
EOF
    exit 1
}

if [[ $# -eq 0 ]]; then
    CONFIG="openmp-native"
else
    CONFIG="$1"
fi

if [[ "$CONFIG" == "-h" || "$CONFIG" == "--help" ]]; then
    usage
fi

if [[ ! -d "$LAMMPS_SOURCE_DIR" ]]; then
    echo "Missing LAMMPS source dir: $LAMMPS_SOURCE_DIR" >&2
    echo "Run on login node first: engines/lammps/fetch_deps.sh" >&2
    exit 1
fi

build_one() {
    local config="$1"

    local build_mpi="OFF"
    local build_omp="ON"
    local pkg_openmp="ON"
    local pkg_intel="OFF"

    local cc=""
    local cxx=""

    local clang_common_flags="-O3 -DNDEBUG -fno-math-errno -ffast-math -fopenmp"
    local intel_generic_flags="-O3 -DNDEBUG -fp-model=fast -qopenmp"
    local intel_native_flags="-O3 -DNDEBUG -xHost -qopenmp -qopt-zmm-usage=high -fp-model=fast"

    local extra_cxx_flags=""
    local extra_c_flags=""
    local runtime_hint=""
    local intel_arch=""
    local intel_lrt_mode=""

    case "$config" in
        openmp-generic)
            module load llvm/20.1.2 cmake ninja
            cc="clang"
            cxx="clang++"
            build_mpi="OFF"
            pkg_intel="OFF"
            extra_c_flags="$clang_common_flags"
            extra_cxx_flags="$clang_common_flags"
            runtime_hint="Run with 1 process, threads, -sf omp"
            ;;

        openmp-native)
            module load llvm/20.1.2 cmake ninja
            cc="clang"
            cxx="clang++"
            build_mpi="OFF"
            pkg_intel="OFF"
            extra_c_flags="$clang_common_flags -march=native"
            extra_cxx_flags="$clang_common_flags -march=native"
            runtime_hint="Run with 1 process, threads, -sf omp"
            ;;

        intel-generic)
            module load intel intel-mpi intel-mkl intel-oneapi-tbb cmake ninja
            cc="mpiicx"
            cxx="mpiicpx"
            build_mpi="ON"
            pkg_intel="ON"
            extra_c_flags="$intel_generic_flags"
            extra_cxx_flags="$intel_generic_flags"
            intel_arch="cpu"
            intel_lrt_mode="none"
            runtime_hint="Run either as 1 MPI rank + threads (-sf intel) or many MPI ranks (-sf intel)"
            ;;

        intel-native)
            module load intel intel-mpi intel-mkl intel-oneapi-tbb cmake ninja
            cc="mpiicx"
            cxx="mpiicpx"
            build_mpi="ON"
            pkg_intel="ON"
            extra_c_flags="$intel_native_flags"
            extra_cxx_flags="$intel_native_flags"
            intel_arch="cpu"
            intel_lrt_mode="none"
            runtime_hint="Run either as 1 MPI rank + threads (-sf intel) or many MPI ranks (-sf intel)"
            ;;

        *)
            echo "Unknown config: $config" >&2
            usage
            ;;
    esac

    local build_dir="${PROJECT_ROOT}/build/lammps-${config}"
    local install_dir="${build_dir}/install"

    export CC="$cc"
    export CXX="$cxx"

    echo
    echo "============================================================"
    echo "Building LAMMPS config: $config"
    echo "============================================================"
    echo "CC: $CC"
    echo "CXX: $CXX"
    echo "Extra C Flags: $extra_c_flags"
    echo "Extra CXX Flags: $extra_cxx_flags"
    echo "BUILD_MPI: $build_mpi"
    echo "BUILD_OMP: $build_omp"
    echo "PKG_OPENMP: $pkg_openmp"
    echo "PKG_INTEL: $pkg_intel"
    echo "Build Dir: $build_dir"
    echo

    local cmake_args=(
        -S "${LAMMPS_SOURCE_DIR}/cmake"
        -B "$build_dir"
        -G Ninja
        -DCMAKE_BUILD_TYPE=Release
        -DCMAKE_INSTALL_PREFIX="$install_dir"
        -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
        -DCMAKE_C_COMPILER="$CC"
        -DCMAKE_CXX_COMPILER="$CXX"
        -DCMAKE_C_FLAGS="$extra_c_flags"
        -DCMAKE_CXX_FLAGS="$extra_cxx_flags"
        -DBUILD_MPI="$build_mpi"
        -DBUILD_OMP="$build_omp"
        -DPKG_OPENMP="$pkg_openmp"
        -DPKG_INTEL="$pkg_intel"
    )

    if [[ "$pkg_intel" == "ON" ]]; then
        cmake_args+=(
            -DINTEL_ARCH="$intel_arch"
            -DINTEL_LRT_MODE="$intel_lrt_mode"
            -DLAMMPS_FP_MODEL=fast
        )
    fi

    cmake "${cmake_args[@]}"
    cmake --build "$build_dir" --parallel
    cmake --install "$build_dir"

    local info_file="${build_dir}/benchmark_info.txt"
    {
        echo "Engine: LAMMPS"
        echo "Config: $config"
        echo "Build Date: $(date --iso-8601=seconds)"
        echo "Project Root: $PROJECT_ROOT"
        echo "Build Dir: $build_dir"
        echo "Install Dir: $install_dir"
        echo "CC: $(command -v "$CC")"
        echo "CXX: $(command -v "$CXX")"
        echo "Extra C Flags: $extra_c_flags"
        echo "Extra CXX Flags: $extra_cxx_flags"
        echo "CMAKE_BUILD_TYPE: Release"
        echo "BUILD_MPI: $build_mpi"
        echo "BUILD_OMP: $build_omp"
        echo "PKG_OPENMP: $pkg_openmp"
        echo "PKG_INTEL: $pkg_intel"
        if [[ "$pkg_intel" == "ON" ]]; then
            echo "INTEL_ARCH: $intel_arch"
            echo "INTEL_LRT_MODE: $intel_lrt_mode"
            echo "LAMMPS_FP_MODEL: fast"
        fi
        echo "Runtime Hint: $runtime_hint"
        echo "CMake: $(cmake --version | head -n 1)"
        echo "Ninja: $(ninja --version)"
        echo "LAMMPS Source Dir: $LAMMPS_SOURCE_DIR"
        echo "LAMMPS Commit: $(git -C "$LAMMPS_SOURCE_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
        echo "Benchmark Repo Commit: $(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
    } > "$info_file"

    echo "Built: $config"
    echo "Binary: ${install_dir}/lmp"
    echo "Info:   $info_file"
}

if [[ "$CONFIG" == "all" ]]; then
    build_one openmp-generic
    build_one openmp-native
    build_one intel-generic
    build_one intel-native
else
    build_one "$CONFIG"
fi