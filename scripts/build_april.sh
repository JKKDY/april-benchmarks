#!/bin/bash
# persistent build config for reproducability

module load gcc/14.2.0 cmake ninja

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="${PROJECT_ROOT}/april_bench_build"

mkdir -p $BUILD_DIR && cd $BUILD_DIR
echo $BUILD_DIR

export CC=gcc
export CXX=g++

cmake -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DAPRIL_ENABLE_OPENMP=ON \
      "$PROJECT_ROOT"

APRIL_DIR="_deps/april-src"
echo "April Commit: $(git -C $APRIL_DIR rev-parse HEAD)" > benchmark_info.txt
echo "Build Date: $(date)" >> benchmark_info.txt