cmake_minimum_required(VERSION 3.28)

project(AprilBenchmarks_AprilEngine VERSION 0.1.0 LANGUAGES CXX)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")

# ------------------------------------------------------------------------------
# DEPENDENCIES
# ------------------------------------------------------------------------------
include(FetchContent)

# 1. April Engine
set(APRIL_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(APRIL_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(APRIL_BUILD_BENCHMARKS OFF CACHE BOOL "" FORCE)

FetchContent_Declare(
    April
    GIT_REPOSITORY https://github.com/JKKDY/april.git
    GIT_TAG dev
)
FetchContent_MakeAvailable(April)

# 2. Google Benchmark
set(BENCHMARK_ENABLE_TESTING OFF CACHE BOOL "" FORCE)
set(BENCHMARK_ENABLE_INSTALL OFF CACHE BOOL "" FORCE)

FetchContent_Declare(
    googlebenchmark
    GIT_REPOSITORY https://github.com/google/benchmark.git
    GIT_TAG v1.8.3
)
FetchContent_MakeAvailable(googlebenchmark)

# ------------------------------------------------------------------------------
# APRIL BENCHMARK CONFIGURATION
# ------------------------------------------------------------------------------
add_library(AprilBench_config INTERFACE)

target_include_directories(AprilBench_config INTERFACE
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
)

target_compile_features(AprilBench_config INTERFACE cxx_std_23)

target_link_libraries(AprilBench_config INTERFACE
    April
    benchmark::benchmark
)

target_compile_definitions(AprilBench_config INTERFACE
    PROJECT_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../.."
    APRIL_ENGINE_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
)

target_compile_options(AprilBench_config INTERFACE
    $<$<CXX_COMPILER_ID:GNU,Clang>:
        -O3
        -fno-math-errno
        -ffast-math
    >
    $<$<CXX_COMPILER_ID:MSVC>:
        /O2
        /fp:fast
    >
)

# ------------------------------------------------------------------------------
# HELPER FUNCTION
# ------------------------------------------------------------------------------
function(add_april_benchmark target_name source_file)
    add_executable(${target_name} "${source_file}")

    target_link_libraries(${target_name} PRIVATE AprilBench_config)

    set_target_properties(${target_name} PROPERTIES
        FOLDER "Benchmarks/April"
    )
endfunction()

# ------------------------------------------------------------------------------
# BENCHMARK EXECUTABLES
# ------------------------------------------------------------------------------
add_april_benchmark(argon_block src/argon_block.cpp)
add_april_benchmark(blast_wave src/blast_wave.cpp)
add_april_benchmark(force_kernel_bench src/force_kernel_bench.cpp)
add_april_benchmark(april_vs_hardcoded src/april_vs_hardcoded.cpp)