This repository contains code and recent results for benchmarking April. 



## Benchmarking April
To fetch dependencies run: 

```
./engines/april/fetch_deps.sh
```

To build all targets run: 


```
./engines/april/build.sh all
```


To execute a benchmark suite for April run: 

```
./scripts/run_april_suite.sh
```
This script supports various configuration options. These are documented inside the script. 


## Benchmarking LAMMPS
LAMMPS is used as a comparison to April. To fetch dependencies and build run: 

```
./engines/lammps/fetch_deps.sh && 
./engines/lammps/build.sh all 
```

This will create lammps executables with openMP and Intel package respectively. 

To execute a benchmark suite for LAMMPS run: 

```
./scripts/run_lammps_suite.sh
```


## Reproducing Results
This repository contains raw data from various benchmarking runs. These were gathered on an exlusive Node on the CoolMuc4 Linux cluster on the Inter partition. Theexact commands used were: 


```
srun -M inter -p cm4_inter --exclusive -N 1 --t=08:00:00 --pty bash
./scripts/run_all_suites.sh
```

