
cmake_minimum_required(VERSION 3.28)

project(AprilBenchmarks VERSION 0.1.0 LANGUAGES CXX)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# DEPENDENCIES (April )
include(FetchContent)

set(APRIL_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(APRIL_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(APRIL_BUILD_BENCHMARKS OFF CACHE BOOL "" FORCE)

FetchContent_Declare(
        April
        GIT_REPOSITORY https://github.com/JKKDY/april.git
        GIT_TAG dev
)
FetchContent_MakeAvailable(April)


# BENCHMARK CONFIGURATION TARGET
# We create an INTERFACE library to hold all benchmark-specific flags and links
add_library(AprilBench_configs INTERFACE
        april_bench/utils.hpp
)
target_compile_features(AprilBench_configs INTERFACE cxx_std_23)

# Link Core Engine and Google Benchmark
target_link_libraries(AprilBench_configs INTERFACE
        April
)

target_compile_definitions(AprilBench_configs INTERFACE
        PROJECT_SOURCE_DIR="${PROJECT_SOURCE_DIR}"
)

# Aggressive optimizations for accurate profiling
target_compile_options(AprilBench_configs INTERFACE
        $<$<CXX_COMPILER_ID:GNU,Clang>:
            -O3
            -march=native
            -fno-math-errno
            -ffast-math
        >
        $<$<CXX_COMPILER_ID:MSVC>:
            /O2
            /arch:AVX512
            /fp:fast
        >
)

# ------------------------------------------------------------------------------
# HELPER FUNCTION
# ------------------------------------------------------------------------------
function(add_april_benchmark target_name source_file)
    add_executable(${target_name} ${source_file})

    # Link the shared benchmark configurations
    target_link_libraries(${target_name} PRIVATE AprilBench_configs)

    # Optional: group them nicely in IDEs like Visual Studio or CLion
    set_target_properties(${target_name} PROPERTIES FOLDER "Benchmarks")
endfunction()

# ------------------------------------------------------------------------------
# SUBDIRECTORIES
# ------------------------------------------------------------------------------
# Hand over to the folder containing your benchmark cpp files
add_subdirectory(april_bench)