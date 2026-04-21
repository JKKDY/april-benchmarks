#!/usr/bin/env bash
set -euo pipefail

module load gcc/14.2.0 cmake ninja

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

APRIL_SOURCE_DIR="${PROJECT_ROOT}/external/april"
GBENCH_SOURCE_DIR="${PROJECT_ROOT}/external/googlebenchmark"
XSIMD_SOURCE_DIR="${PROJECT_ROOT}/external/xsimd"

usage() {
    cat >&2 <<EOF
Usage:
  $0 [<isa|all>] [--allow-auto-vectorization|--disable-auto-vectorization]

ISA options:
  scalar
  sse
  avx2
  avx512
  native
  all

Vectorization mode:
  --allow-auto-vectorization      default, does not add -fno-tree-vectorize
  --disable-auto-vectorization    adds -fno-tree-vectorize

Defaults:
  $0
      builds native-autovec

  $0 native
      builds native-autovec

Special behavior:
  $0 all
      builds:
        scalar-novec
        sse-novec
        avx2-novec
        avx512-novec
        native-novec
        native-autovec

Build output variants:
  scalar-autovec
  scalar-novec
  sse-autovec
  sse-novec
  avx2-autovec
  avx2-novec
  avx512-autovec
  avx512-novec
  native-autovec
  native-novec

Examples:
  $0
  $0 native
  $0 native --disable-auto-vectorization
  $0 avx2
  $0 avx2 --disable-auto-vectorization
  $0 avx512
  $0 all
EOF
    exit 1
}

check_dependencies() {
    if [[ ! -d "$APRIL_SOURCE_DIR" ]]; then
        echo "Missing April dependency: $APRIL_SOURCE_DIR" >&2
        echo "Run: engines/april/fetch_deps.sh" >&2
        exit 1
    fi

    if [[ ! -d "$GBENCH_SOURCE_DIR" ]]; then
        echo "Missing Google Benchmark dependency: $GBENCH_SOURCE_DIR" >&2
        echo "Run: engines/april/fetch_deps.sh" >&2
        exit 1
    fi

    if [[ ! -d "$XSIMD_SOURCE_DIR" ]]; then
        echo "Missing xsimd dependency: $XSIMD_SOURCE_DIR" >&2
        echo "Run this on the login node first: engines/april/fetch_deps.sh" >&2
        exit 1
    fi
}

build_one() {
    local variant="$1"
    local auto_vectorization="$2"

    local common_flags="-fno-math-errno -ffast-math"
    local vectorization_flag="-fno-tree-vectorize"

    local april_xsimd="ON"
    local explicit_simd_baselines="ON"
    local isa_flags=""
    local extra_cxx_flags=""
    local build_suffix=""

    case "$variant" in
        scalar)
            isa_flags=""
            april_xsimd="ON"
            explicit_simd_baselines="OFF"
            ;;
        sse)
            isa_flags="-msse4.2"
            ;;
        avx2)
            isa_flags="-mavx2 -mfma"
            ;;
        avx512)
            isa_flags="-mavx512f -mavx512cd -mavx512dq -mavx512bw -mavx512vl"
            ;;
        native)
            isa_flags="-march=native"
            ;;
        *)
            echo "Unknown ISA variant: $variant" >&2
            usage
            ;;
    esac

    if [[ "$auto_vectorization" == "ON" ]]; then
        extra_cxx_flags="$common_flags $isa_flags"
        build_suffix="${variant}-autovec"
    else
        extra_cxx_flags="$common_flags $isa_flags $vectorization_flag"
        build_suffix="${variant}-novec"
    fi

    local build_dir="${PROJECT_ROOT}/build/april-${build_suffix}"

    export CC="${CC:-gcc}"
    export CXX="${CXX:-g++}"

    echo
    echo "============================================================"
    echo "Building April benchmark config: $build_suffix"
    echo "============================================================"
    echo "ISA Variant: $variant"
    echo "Auto-vectorization: $auto_vectorization"
    echo "Extra CXX Flags: $extra_cxx_flags"
    echo "Build Dir: $build_dir"
    echo

    cmake -S "$SCRIPT_DIR" \
          -B "$build_dir" \
          -G Ninja \
          -DCMAKE_BUILD_TYPE=Release \
          -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
          -DCMAKE_CXX_FLAGS="$extra_cxx_flags" \
          -DFETCHCONTENT_SOURCE_DIR_APRIL="$APRIL_SOURCE_DIR" \
          -DFETCHCONTENT_SOURCE_DIR_GOOGLEBENCHMARK="$GBENCH_SOURCE_DIR" \
          -DFETCHCONTENT_SOURCE_DIR_XSIMD="$XSIMD_SOURCE_DIR" \
          -DAPRIL_ENABLE_OPENMP=ON \
          -DAPRIL_ENABLE_XSIMD="$april_xsimd" \
          -DAPRIL_BENCH_ENABLE_EXPLICIT_SIMD_BASELINES="$explicit_simd_baselines"

    cmake --build "$build_dir" --parallel

    local info_file="$build_dir/benchmark_info.txt"

    {
        echo "Engine: April"
        echo "ISA Variant: $variant"
        echo "Build Variant: $build_suffix"
        echo "Auto-vectorization: $auto_vectorization"
        echo "Build Date: $(date --iso-8601=seconds)"
        echo "Project Root: $PROJECT_ROOT"
        echo "Build Dir: $build_dir"
        echo "CC: $(command -v "$CC")"
        echo "CXX: $(command -v "$CXX")"
        echo "Extra CXX Flags: $extra_cxx_flags"
        echo "CMAKE_BUILD_TYPE: Release"
        echo "APRIL_ENABLE_OPENMP: ON"
        echo "APRIL_ENABLE_XSIMD: $april_xsimd"
        echo "APRIL_BENCH_ENABLE_EXPLICIT_SIMD_BASELINES: $explicit_simd_baselines"
        echo "CMake: $(cmake --version | head -n 1)"
        echo "Ninja: $(ninja --version)"
        echo
        echo "Dependencies:"
        echo "April Source Dir: $APRIL_SOURCE_DIR"
        echo "April Commit: $(git -C "$APRIL_SOURCE_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
        echo "April Branch: $(git -C "$APRIL_SOURCE_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
        echo "Google Benchmark Source Dir: $GBENCH_SOURCE_DIR"
        echo "Google Benchmark Commit: $(git -C "$GBENCH_SOURCE_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
        echo "xsimd Source Dir: $XSIMD_SOURCE_DIR"
        echo "xsimd Commit: $(git -C "$XSIMD_SOURCE_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
        echo
        echo "Benchmark Repo Commit: $(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
    } > "$info_file"

    echo "Built April benchmark variant: $build_suffix"
    echo "Build dir: $build_dir"
    echo "Binaries: $build_dir/bin"
    echo "Build info: $info_file"
}

if [[ $# -eq 0 ]]; then
    VARIANT="native"
    AUTO_VECTORIZATION="ON"
else
    VARIANT="$1"
    AUTO_VECTORIZATION="ON"
fi

if [[ "$VARIANT" == "-h" || "$VARIANT" == "--help" ]]; then
    usage
fi

for arg in "${@:2}"; do
    case "$arg" in
        --allow-auto-vectorization)
            AUTO_VECTORIZATION="ON"
            ;;
        --disable-auto-vectorization)
            AUTO_VECTORIZATION="OFF"
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $arg" >&2
            usage
            ;;
    esac
done

check_dependencies

if [[ "$VARIANT" == "all" ]]; then
    build_one scalar OFF
    build_one sse OFF
    build_one avx2 OFF
    build_one avx512 OFF
    build_one native OFF
    build_one native ON

    echo
    echo "All April benchmark configs built."
    echo "Builds:"
    echo "  ${PROJECT_ROOT}/build/april-scalar-novec"
    echo "  ${PROJECT_ROOT}/build/april-sse-novec"
    echo "  ${PROJECT_ROOT}/build/april-avx2-novec"
    echo "  ${PROJECT_ROOT}/build/april-avx512-novec"
    echo "  ${PROJECT_ROOT}/build/april-native-novec"
    echo "  ${PROJECT_ROOT}/build/april-native-autovec"
else
    build_one "$VARIANT" "$AUTO_VECTORIZATION"
fi