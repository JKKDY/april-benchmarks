#!/usr/bin/env python3
import sys
import math

if len(sys.argv) != 4:
    print(f"Usage: {sys.argv[0]} <n_dim> <rho> <output.data>")
    sys.exit(1)

n_dim = int(sys.argv[1])
rho = float(sys.argv[2])
out = sys.argv[3]

N = n_dim ** 3

volume = N / rho
L = volume ** (1.0 / 3.0)
half_L = 0.5 * L
spacing = L / n_dim
origin = -half_L + 0.5 * spacing

with open(out, "w") as f:
    f.write("LAMMPS data file for APRIL argon environment\n\n")
    f.write(f"{N} atoms\n")
    f.write("1 atom types\n\n")

    f.write(f"{-half_L:.17g} {half_L:.17g} xlo xhi\n")
    f.write(f"{-half_L:.17g} {half_L:.17g} ylo yhi\n")
    f.write(f"{-half_L:.17g} {half_L:.17g} zlo zhi\n\n")

    f.write("Masses\n\n")
    f.write("1 1.0\n\n")

    f.write("Atoms # atomic\n\n")

    atom_id = 1
    for ix in range(n_dim):
        x = origin + ix * spacing
        for iy in range(n_dim):
            y = origin + iy * spacing
            for iz in range(n_dim):
                z = origin + iz * spacing
                f.write(f"{atom_id} 1 {x:.17g} {y:.17g} {z:.17g}\n")
                atom_id += 1

print(f"N        = {N}")
print(f"rho      = {rho}")
print(f"L        = {L:.17g}")
print(f"spacing  = {spacing:.17g}")
print(f"origin   = {origin:.17g}")