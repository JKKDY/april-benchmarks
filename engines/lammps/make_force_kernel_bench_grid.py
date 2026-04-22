#!/usr/bin/env python3
import sys

if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} <n_dim> <output.data>")
    sys.exit(1)

n_dim = int(sys.argv[1])
out = sys.argv[2]

a = 1.1225

L = (n_dim - 1) * a
half_L = 0.5 * L

E = 1.5 * L
half_E = 0.5 * E

N = n_dim ** 3

with open(out, "w") as f:
    f.write("LAMMPS data file for APRIL grid\n\n")
    f.write(f"{N} atoms\n")
    f.write("1 atom types\n\n")

    f.write(f"{-half_E:.17g} {half_E:.17g} xlo xhi\n")
    f.write(f"{-half_E:.17g} {half_E:.17g} ylo yhi\n")
    f.write(f"{-half_E:.17g} {half_E:.17g} zlo zhi\n\n")

    f.write("Masses\n\n")
    f.write("1 1.0\n\n")

    f.write("Atoms # atomic\n\n")

    atom_id = 1
    for ix in range(n_dim):
        x = -half_L + ix * a
        for iy in range(n_dim):
            y = -half_L + iy * a
            for iz in range(n_dim):
                z = -half_L + iz * a
                f.write(f"{atom_id} 1 {x:.17g} {y:.17g} {z:.17g}\n")
                atom_id += 1