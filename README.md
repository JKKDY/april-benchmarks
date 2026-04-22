



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





mpirun -np 1 ./build/lammps-intel-native/lmp -in engines/lammps/force_kernel_bench.in -var datafile engines/lammps/grid_50.data -var n_dim 50 -var steps 100 



From the repo root, examples:

## Argon block

OpenMP native, 16 threads:

```bash
engines/lammps/run_argon.sh \
  --config openmp-serial-native \
  --n 100 \
  --rho 0.8442 \
  --steps 1000 \
  --dt 0.005 \
  --threads 16
```

Intel native, 1 rank × 16 threads:

```bash
engines/lammps/run_argon.sh \
  --config intel-native \
  --n 100 \
  --rho 0.8442 \
  --steps 1000 \
  --dt 0.005 \
  --ranks 1 \
  --threads 16
```

Intel native, 8 ranks × 2 threads:

```bash
engines/lammps/run_argon.sh \
  --config intel-native \
  --n 100 \
  --rho 0.8442 \
  --steps 1000 \
  --dt 0.005 \
  --ranks 8 \
  --threads 2
```

With explicit scenario name:

```bash
SCENARIO=n100_rho0.8442_dt0.005_r8_t2 \
engines/lammps/run_argon.sh \
  --config intel-native \
  --n 100 \
  --rho 0.8442 \
  --steps 1000 \
  --dt 0.005 \
  --ranks 8 \
  --threads 2
```

---

## Force kernel

OpenMP native, single rank/thread, with OpenMP suffix:

```bash
engines/lammps/run_force_kernel.sh \
  --config openmp-serial-native \
  --n 100 \
  --steps 100
```

Intel native, single rank/thread, with Intel suffix:

```bash
engines/lammps/run_force_kernel.sh \
  --config intel-native \
  --n 100 \
  --steps 100
```

Generic builds:

```bash
engines/lammps/run_force_kernel.sh \
  --config openmp-serial-generic \
  --n 100 \
  --steps 100
```

```bash
engines/lammps/run_force_kernel.sh \
  --config intel-generic \
  --n 100 \
  --steps 100
```

With explicit scenario name:

```bash
SCENARIO=n100_singlecore \
engines/lammps/run_force_kernel.sh \
  --config intel-native \
  --n 100 \
  --steps 100
```



Example commands for lammsp suite:

scripts/run_lammps_suite.sh --only force intel-native
scripts/run_lammps_suite.sh --only argon openmp-serial-native
scripts/run_lammps_suite.sh --only both intel-native
scripts/run_lammps_suite.sh intel-native

ARGON_THREADS="1 2 4 8" ARGON_N=80 ARGON_STEPS=100 \
scripts/run_lammps_suite.sh --only argon intel-native