



cmake -S engines/april -B build/april -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/april --parallel


engines/april/build.sh scalar
engines/april/build.sh avx2
engines/april/build.sh avx512 --allow-auto-vectorization
engines/april/build.sh native --allow-auto-vectorization



engines/april/run.sh native-novec force_kernel_bench \
  --benchmark_out_format=json \
  --benchmark_out=force_kernel_bench.json

engines/april/run.sh native-novec april_vs_hardcoded \
  --benchmark_out_format=json \
  --benchmark_out=april_vs_hardcoded.json


engines/april/run.sh native-autovec force_kernel_bench \
  --benchmark_out_format=json \
  --benchmark_out=force_kernel_bench.json

engines/april/run.sh native-autovec april_vs_hardcoded \
  --benchmark_out_format=json \
  --benchmark_out=april_vs_hardcoded.json


# login node
engines/april/fetch_deps.sh

# build node
engines/april/build.sh native

# run node
engines/april/run.sh native-novec april_vs_hardcoded