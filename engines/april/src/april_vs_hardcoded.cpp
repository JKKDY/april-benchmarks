#include <benchmark/benchmark.h>
#include <vector>
#include <april/april.hpp>

#include "april/exec/executors/sequential_executor.hpp"
#include "april/base/macros.hpp"

using namespace april;

// simulation constants
static constexpr double A = 1.1225;
static constexpr double MASS = 1.0;
static constexpr double SIGMA = 1.0;
static constexpr double EPSILON = 5.0;
static constexpr double R_CUT = 3.0 * SIGMA;
static constexpr double DT = 0.0002;

static constexpr double r_cut2 = R_CUT * R_CUT;
static constexpr double sigma2 = SIGMA * SIGMA;
static constexpr double sigma6 = sigma2 * sigma2 * sigma2;
static constexpr double c6_scalar = 24.0 * EPSILON * sigma6;
static constexpr double c12_scalar = 48.0 * EPSILON * sigma6 * sigma6;

// ------------------
// HARDCODED BASELINE
// ------------------
namespace baseline {
    struct Particle {
        vec3 position = {};
        vec3 old_position = {};
        vec3 force = {};
        vec3 velocity = {};
    };

    struct StateSoA {
        std::vector<double> x, y, z;
        std::vector<double> ox, oy, oz;
        std::vector<double> vx, vy, vz;
        std::vector<double> fx, fy, fz;

        StateSoA(size_t N) {
            x.resize(N, 0.0); y.resize(N, 0.0); z.resize(N, 0.0);
            vx.resize(N, 0.0); vy.resize(N, 0.0); vz.resize(N, 0.0);
            fx.resize(N, 0.0); fy.resize(N, 0.0); fz.resize(N, 0.0);
        }
    };
}



static void BM_Baseline_Handcoded_AoS_Scalar(benchmark::State& state) {
    const int N_DIM = state.range(0);
    const int STEPS = state.range(1);
    const size_t N = N_DIM * N_DIM * N_DIM;

    const double off_x = -0.5 * (N_DIM - 1) * A;
    const double off_y = -0.5 * (N_DIM - 1) * A;
    const double off_z = -0.5 * (N_DIM - 1) * A;

    for (auto _ : state) {
        state.PauseTiming();

        // Rebuild pristine state
        std::vector<baseline::Particle> particles(N);
        size_t idx = 0;
        for (int k = 0; k < N_DIM; ++k) {
            for (int j = 0; j < N_DIM; ++j) {
                for (int i = 0; i < N_DIM; ++i) {
                    particles[idx].position = {i * A + off_x, j * A + off_y, k * A + off_z};
                    particles[idx].old_position = {};
                    particles[idx].velocity = {};
                    particles[idx].force = {};
                    idx++;
                }
            }
        }

        state.ResumeTiming();

        // Execute workload
        for (int step = 0; step < STEPS; ++step) {

            // first half pick
            for (auto& [position, old_position, force, velocity] : particles) {
                old_position = position;
                velocity += (DT / 2.0) * (force / MASS);
                position += DT * velocity;
                force = {};
            }

            for (auto& [position, old_position, force, velocity] : particles) {
                force = {};
            }

            for (size_t i = 0; i < N; ++i) {
                auto& p1 = particles[i];
                for (size_t j = i + 1; j < N; ++j) {
                    auto& p2 = particles[j];

                    const vec3 r = p2.position - p1.position;
                    const double r2 = r.x*r.x + r.y*r.y + r.z*r.z;

                    if (r2 < r_cut2) {
                        const double inv_r2 = 1.0 / r2;
                        const double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                        const double mag = (c12_scalar * inv_r6 - c6_scalar) * inv_r6 * inv_r2;

                        const vec3 f = r * -mag;

                        p1.force += f;
                        p2.force -= f;
                    }
                }
            }

            // second half pick
            for (auto& p : particles) {
                p.velocity += (DT / 2.0) * (p.force / MASS);
            }
        }

        benchmark::DoNotOptimize(particles.data());
        benchmark::ClobberMemory();
    }

    const double total_interactions = static_cast<double>(state.iterations()) * (N * (N - 1) / 2) * STEPS;
    state.SetItemsProcessed(total_interactions);
    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9,
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}


static void BM_Baseline_Handcoded_SoA_Scalar(benchmark::State& state) {
    const int N_DIM = state.range(0);
    const int STEPS = state.range(1);
    const size_t N = N_DIM * N_DIM * N_DIM;

    const double off_x = -0.5 * (N_DIM - 1) * A;
    const double off_y = -0.5 * (N_DIM - 1) * A;
    const double off_z = -0.5 * (N_DIM - 1) * A;


    for (auto _ : state) {
        state.PauseTiming();

        // Rebuild pristine state
        baseline::StateSoA p(N);
        size_t idx = 0;
        for (int k = 0; k < N_DIM; ++k) {
            for (int j = 0; j < N_DIM; ++j) {
                for (int i = 0; i < N_DIM; ++i) {
                    p.x[idx] = i * A + off_x; p.y[idx] = j * A + off_y; p.z[idx] = k * A + off_z;
                    idx++;
                }
            }
        }

        state.ResumeTiming();

        // Execute Workload
        for (int step = 0; step < STEPS; ++step) {
            // first half pick
            for (size_t i = 0; i < N; ++i) {
                p.ox[i] = p.x[i];
                p.oy[i] = p.y[i];
                p.oz[i] = p.z[i];

                p.vx[i] += (DT / 2.0) * (p.fx[i] / MASS);
                p.vy[i] += (DT / 2.0) * (p.fy[i] / MASS);
                p.vz[i] += (DT / 2.0) * (p.fz[i] / MASS);

                p.x[i] += DT * p.vx[i];
                p.y[i] += DT * p.vy[i];
                p.z[i] += DT * p.vz[i];
            }

            for (size_t i = 0; i < N; ++i) {
                p.fx[i] = 0.0;
                p.fy[i] = 0.0;
                p.fz[i] = 0.0;
            }

            // force accumualtion
            for (size_t i = 0; i < N; ++i) {
                // Local accumulators for particle i
                double fi_x = 0.0;
                double fi_y = 0.0;
                double fi_z = 0.0;

                for (size_t j = i + 1; j < N; ++j) {
                    const double dx = p.x[j] - p.x[i];
                    const double dy = p.y[j] - p.y[i];
                    const double dz = p.z[j] - p.z[i];

                    const double r2 = (dx * dx) + (dy * dy) + (dz * dz);
                    if (r2 < r_cut2) {
                        const double inv_r2 = 1.0 / r2;
                        const double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                        const double mag = (c12_scalar * inv_r6 - c6_scalar) * inv_r6 * inv_r2;

                        const double fx = -mag * dx;
                        const double fy = -mag * dy;
                        const double fz = -mag * dz;

                        // Update local accumulator for i (Register access)
                        fi_x += fx;
                        fi_y += fy;
                        fi_z += fz;

                        // Update j in memory (Direct write-back)
                        p.fx[j] -= fx;
                        p.fy[j] -= fy;
                        p.fz[j] -= fz;
                    }
                }

                // Final write-back for particle i (One store per outer loop iteration)
                p.fx[i] += fi_x;
                p.fy[i] += fi_y;
                p.fz[i] += fi_z;
            }

            // second half pick
            for (size_t i = 0; i < N; ++i) {
                p.vx[i] += (DT / 2.0) * (p.fx[i] / MASS);
                p.vy[i] += (DT / 2.0) * (p.fy[i] / MASS);
                p.vz[i] += (DT / 2.0) * (p.fz[i] / MASS);
            }
        }
    }

    const double total_interactions = static_cast<double>(state.iterations()) * (N * (N - 1) / 2) * STEPS;
    state.SetItemsProcessed(total_interactions);
    state.counters["ns/interaction"] = benchmark::Counter(total_interactions / 1e9, benchmark::Counter::kIsRate | benchmark::Counter::kInvert);
}



// NOTICE: NO DISABLE_VECTORIZATION_FUNC. Let xsimd optimize freely.
static void BM_Baseline_Handcoded_SoA_2D_SIMD(benchmark::State& state) {

    using packed_double = april::simd::internal::xsimd::Packed<double>;

    const int N_DIM = state.range(0);
    const int STEPS = state.range(1);
    const size_t N = N_DIM * N_DIM * N_DIM;

    const double off_x = -0.5 * (N_DIM - 1) * A;
    const double off_y = -0.5 * (N_DIM - 1) * A;
    const double off_z = -0.5 * (N_DIM - 1) * A;

    const packed_double v_c6 = c6_scalar;
    const packed_double v_c12 = c12_scalar;
    const packed_double v_one = 1.0;
    const packed_double v_rcut2 = r_cut2;
    constexpr size_t V = packed_double::size();


    if ((N % V) != 0) {
        state.SkipWithError("Requires N to be a multiple of SIMD width.");
        return;
    }
    const size_t N_body = N - (N % V);

    for (auto _ : state) {
        state.PauseTiming();

        baseline::StateSoA p(N);
        size_t idx = 0;
        for (int k = 0; k < N_DIM; ++k) {
            for (int j = 0; j < N_DIM; ++j) {
                for (int i = 0; i < N_DIM; ++i) {
                    p.x[idx] = i * A + off_x; p.y[idx] = j * A + off_y; p.z[idx] = k * A + off_z;
                    idx++;
                }
            }
        }

        const packed_double zero = 0.0;
        state.ResumeTiming();

        for (int step = 0; step < STEPS; ++step) {
            // first half pick
            for (size_t i = 0; i < N; i += V) {
                packed_double v_vx = packed_double::load_unaligned(&p.vx[i]);
                packed_double v_vy = packed_double::load_unaligned(&p.vy[i]);
                packed_double v_vz = packed_double::load_unaligned(&p.vz[i]);

                packed_double v_fx = packed_double::load_unaligned(&p.fx[i]);
                packed_double v_fy = packed_double::load_unaligned(&p.fy[i]);
                packed_double v_fz = packed_double::load_unaligned(&p.fz[i]);

                v_vx += DT / 2.0 / MASS * v_fx;
                v_vy += DT / 2.0 / MASS * v_fy;
                v_vz += DT / 2.0 / MASS * v_fz;

                v_vx.store_unaligned(&p.vx[i]);
                v_vy.store_unaligned(&p.vy[i]);
                v_vz.store_unaligned(&p.vz[i]);

                packed_double v_x = packed_double::load_unaligned(&p.x[i]);
                packed_double v_y = packed_double::load_unaligned(&p.y[i]);
                packed_double v_z = packed_double::load_unaligned(&p.z[i]);

                v_x += DT * v_vx;
                v_y += DT * v_vy;
                v_z += DT * v_vz;

                v_x.store_unaligned(&p.x[i]);
                v_y.store_unaligned(&p.y[i]);
                v_z.store_unaligned(&p.z[i]);

                zero.store_unaligned(&p.fx[i]);
                zero.store_unaligned(&p.fy[i]);
                zero.store_unaligned(&p.fz[i]);
            }

            // force accumulation
            for (size_t i = 0; i < N_body; i += V) {
                packed_double v_xi = packed_double::load_unaligned(&p.x[i]);
                packed_double v_yi = packed_double::load_unaligned(&p.y[i]);
                packed_double v_zi = packed_double::load_unaligned(&p.z[i]);
                packed_double v_fxi = packed_double::load_unaligned(&p.fx[i]);
                packed_double v_fyi = packed_double::load_unaligned(&p.fy[i]);
                packed_double v_fzi = packed_double::load_unaligned(&p.fz[i]);

                // INTRA-BLOCK SIMD (SIMD block self-interaction)
                {
                    packed_double v_xj = v_xi;
                    packed_double v_yj = v_yi;
                    packed_double v_zj = v_zi;
                    packed_double acc_fxj = 0.0;
                    packed_double acc_fyj = 0.0;
                    packed_double acc_fzj = 0.0;

                    // Fractional rotation (V/2 - 1)
                    APRIL_UNROLL_LOOP()
                    for (size_t k = 0; k < V / 2 - 1; ++k) {
                        v_xj = v_xj.rotate_right();
                        v_yj = v_yj.rotate_right();
                        v_zj = v_zj.rotate_right();

                        // Rotate accumulators with the j-particles
                        acc_fxj = acc_fxj.rotate_right();
                        acc_fyj = acc_fyj.rotate_right();
                        acc_fzj = acc_fzj.rotate_right();

                        const packed_double dx = v_xj - v_xi;
                        const packed_double dy = v_yj - v_yi;
                        const packed_double dz = v_zj - v_zi;

                        const packed_double r2 = (dx * dx) + (dy * dy) + (dz * dz);
                        const auto outside = r2 > v_rcut2;

                        if (!all(outside)) {
                         const packed_double inv_r2 = v_one / r2;
                         const packed_double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                         const packed_double mag = select(outside, packed_double(0.0), (v_c12 * inv_r6 - v_c6) * inv_r6 * inv_r2);

                         const packed_double fx = -mag * dx;
                         const packed_double fy = -mag * dy;
                         const packed_double fz = -mag * dz;

                         v_fxi += fx; v_fyi += fy; v_fzi += fz;
                         acc_fxj -= fx; acc_fyj -= fy; acc_fzj -= fz;
                        }
                    }

                    // Revert the j-accumulators to native lanes
                    acc_fxj = acc_fxj.template rotate_left<V / 2 - 1>();
                    acc_fyj = acc_fyj.template rotate_left<V / 2 - 1>();
                    acc_fzj = acc_fzj.template rotate_left<V / 2 - 1>();

                    v_fxi += acc_fxj;
                    v_fyi += acc_fyj;
                    v_fzi += acc_fzj;

                    // The 180-Degree Scoping Trick (Exactly V/2)
                    v_xj = v_xj.rotate_right();
                    v_yj = v_yj.rotate_right();
                    v_zj = v_zj.rotate_right();

                    packed_double dx = v_xj - v_xi;
                    packed_double dy = v_yj - v_yi;
                    packed_double dz = v_zj - v_zi;

                    packed_double r2 = (dx * dx) + (dy * dy) + (dz * dz);
                    auto outside = r2 > v_rcut2;

                    if (!all(outside)) {
                        packed_double inv_r2 = v_one / r2;
                        packed_double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                        packed_double mag = select(outside, packed_double(0.0), (v_c12 * inv_r6 - v_c6) * inv_r6 * inv_r2);

                        packed_double fx = -mag * dx;
                        packed_double fy = -mag * dy;
                        packed_double fz = -mag * dz;

                        v_fxi += fx; v_fyi += fy; v_fzi += fz;
                        // j-accumulator is intentionally dropped here to avoid double counting!
                    }
                }

                // ----------------------------------------------------
                // INTER-BLOCK SIMD
                // ----------------------------------------------------
                for (size_t j = i + V; j < N_body; j += V) {
                    packed_double v_xj = packed_double::load_unaligned(&p.x[j]);
                    packed_double v_yj = packed_double::load_unaligned(&p.y[j]);
                    packed_double v_zj = packed_double::load_unaligned(&p.z[j]);
                    packed_double v_fxj = packed_double::load_unaligned(&p.fx[j]);
                    packed_double v_fyj = packed_double::load_unaligned(&p.fy[j]);
                    packed_double v_fzj = packed_double::load_unaligned(&p.fz[j]);

                    APRIL_UNROLL_LOOP()
                    for (size_t k = 0; k < packed_double::size(); ++k) {
                        const packed_double dx = v_xj - v_xi;
                        const packed_double dy = v_yj - v_yi;
                        const packed_double dz = v_zj - v_zi;

                        const packed_double r2 = (dx * dx) + (dy * dy) + (dz * dz);
                        const auto outside = r2 > v_rcut2;

                        if (!all(outside)) {
                            const packed_double inv_r2 = v_one / r2;
                            const packed_double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                            const packed_double mag = select(outside, packed_double(0.0), (v_c12 * inv_r6 - v_c6) * inv_r6 * inv_r2);

                            const packed_double fx = -mag * dx;
                            const packed_double fy = -mag * dy;
                            const packed_double fz = -mag * dz;

                            v_fxi += fx; v_fyi += fy; v_fzi += fz;
                            v_fxj -= fx; v_fyj -= fy; v_fzj -= fz;
                        }

                        v_xj = v_xj.rotate_right();
                        v_yj = v_yj.rotate_right();
                        v_zj = v_zj.rotate_right();
                        v_fxj = v_fxj.rotate_right();
                        v_fyj = v_fyj.rotate_right();
                        v_fzj = v_fzj.rotate_right();
                    }

                    v_fxj.store_unaligned(&p.fx[j]);
                    v_fyj.store_unaligned(&p.fy[j]);
                    v_fzj.store_unaligned(&p.fz[j]);
                }

                v_fxi.store_unaligned(&p.fx[i]);
                v_fyi.store_unaligned(&p.fy[i]);
                v_fzi.store_unaligned(&p.fz[i]);
            }

            // second half kick
            for (size_t i = 0; i < N; i += V) {
                packed_double v_vx = packed_double::load_unaligned(&p.vx[i]);
                packed_double v_vy = packed_double::load_unaligned(&p.vy[i]);
                packed_double v_vz = packed_double::load_unaligned(&p.vz[i]);

                packed_double v_fx = packed_double::load_unaligned(&p.fx[i]);
                packed_double v_fy = packed_double::load_unaligned(&p.fy[i]);
                packed_double v_fz = packed_double::load_unaligned(&p.fz[i]);

                v_vx += (DT / 2.0 / MASS) * v_fx;
                v_vy += (DT / 2.0 / MASS) * v_fy;
                v_vz += (DT / 2.0 / MASS) * v_fz;

                v_vx.store_unaligned(&p.vx[i]);
                v_vy.store_unaligned(&p.vy[i]);
                v_vz.store_unaligned(&p.vz[i]);
            }
        }

        benchmark::DoNotOptimize(p.fx.data());
        benchmark::ClobberMemory();
    }

    const double total_interactions = static_cast<double>(state.iterations()) * (N * (N - 1) / 2) * STEPS;
    state.SetItemsProcessed(total_interactions);
    state.counters["ns/interaction"] = benchmark::Counter(total_interactions / 1e9, benchmark::Counter::kIsRate | benchmark::Counter::kInvert);
}


// use broadcast-reduce
static void BM_Baseline_Handcoded_SoA_1D_SIMD(benchmark::State& state) {
    using packed_double = april::simd::internal::xsimd::Packed<double>;

    const int N_DIM = state.range(0);
    const int STEPS = state.range(1);
    const size_t N = N_DIM * N_DIM * N_DIM;

    const double off_x = -0.5 * (N_DIM - 1) * A;
    const double off_y = -0.5 * (N_DIM - 1) * A;
    const double off_z = -0.5 * (N_DIM - 1) * A;

    const packed_double v_c6 = c6_scalar;
    const packed_double v_c12 = c12_scalar;
    const packed_double v_one = 1.0;
    const packed_double v_rcut2 = r_cut2;
    constexpr size_t V = packed_double::size();

    for (auto _ : state) {
        state.PauseTiming();

        baseline::StateSoA p(N);
        size_t idx = 0;
        for (int k = 0; k < N_DIM; ++k) {
            for (int j = 0; j < N_DIM; ++j) {
                for (int i = 0; i < N_DIM; ++i) {
                    p.x[idx] = i * A + off_x; p.y[idx] = j * A + off_y; p.z[idx] = k * A + off_z;
                    idx++;
                }
            }
        }

        const packed_double zero = 0.0;
        state.ResumeTiming();

        for (int step = 0; step < STEPS; ++step) {
            // first half pick
            for (size_t i = 0; i < N; i += V) {
                packed_double v_vx = packed_double::load_unaligned(&p.vx[i]);
                packed_double v_vy = packed_double::load_unaligned(&p.vy[i]);
                packed_double v_vz = packed_double::load_unaligned(&p.vz[i]);

                packed_double v_fx = packed_double::load_unaligned(&p.fx[i]);
                packed_double v_fy = packed_double::load_unaligned(&p.fy[i]);
                packed_double v_fz = packed_double::load_unaligned(&p.fz[i]);

                v_vx += DT / 2.0 / MASS * v_fx;
                v_vy += DT / 2.0 / MASS * v_fy;
                v_vz += DT / 2.0 / MASS * v_fz;

                v_vx.store_unaligned(&p.vx[i]);
                v_vy.store_unaligned(&p.vy[i]);
                v_vz.store_unaligned(&p.vz[i]);

                packed_double v_x = packed_double::load_unaligned(&p.x[i]);
                packed_double v_y = packed_double::load_unaligned(&p.y[i]);
                packed_double v_z = packed_double::load_unaligned(&p.z[i]);

                v_x += DT * v_vx;
                v_y += DT * v_vy;
                v_z += DT * v_vz;

                v_x.store_unaligned(&p.x[i]);
                v_y.store_unaligned(&p.y[i]);
                v_z.store_unaligned(&p.z[i]);

                zero.store_unaligned(&p.fx[i]);
                zero.store_unaligned(&p.fy[i]);
                zero.store_unaligned(&p.fz[i]);
            }

            // force accumulation (Broadcast-Reduce)
            for (size_t i = 0; i < N; ++i) {
                // 1. Broadcast the scalar particle 'i' to all SIMD lanes
                const packed_double v_xi = p.x[i];
                const packed_double v_yi = p.y[i];
                const packed_double v_zi = p.z[i];

                // SIMD accumulators for particle i
                packed_double v_ax = 0.0;
                packed_double v_ay = 0.0;
                packed_double v_az = 0.0;

                size_t j = i + 1;

                // SIMD Inner Loop
                for (; j + V <= N; j += V) {
                    packed_double v_xj = packed_double::load_unaligned(&p.x[j]);
                    packed_double v_yj = packed_double::load_unaligned(&p.y[j]);
                    packed_double v_zj = packed_double::load_unaligned(&p.z[j]);

                    packed_double dx = v_xj - v_xi;
                    packed_double dy = v_yj - v_yi;
                    packed_double dz = v_zj - v_zi;

                    packed_double r2 = (dx * dx) + (dy * dy) + (dz * dz);
                    auto outside = r2 > v_rcut2;

                    // Early exit mask check
                    if (!all(outside)) {
                        packed_double inv_r2 = v_one / r2;
                        packed_double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                        packed_double mag = select(outside, packed_double(0.0), (v_c12 * inv_r6 - v_c6) * inv_r6 * inv_r2);

                        packed_double fx = -mag * dx;
                        packed_double fy = -mag * dy;
                        packed_double fz = -mag * dz;

                        // Accumulate locally for i
                        v_ax += fx;
                        v_ay += fy;
                        v_az += fz;

                        // Load, subtract, and store for j block
                        packed_double f_xj = packed_double::load_unaligned(&p.fx[j]);
                        packed_double f_yj = packed_double::load_unaligned(&p.fy[j]);
                        packed_double f_zj = packed_double::load_unaligned(&p.fz[j]);

                        (f_xj - fx).store_unaligned(&p.fx[j]);
                        (f_yj - fy).store_unaligned(&p.fy[j]);
                        (f_zj - fz).store_unaligned(&p.fz[j]);
                    }
                }

                // Horizontal Reduction
                // Collapse the SIMD accumulators into scalars and apply to p.fx[i]
                double ax = v_ax.reduce_add();
                double ay = v_ay.reduce_add();
                double az = v_az.reduce_add();

                // Scalar Tail Loop
                for (; j < N; ++j) {
                    double dx = p.x[j] - p.x[i];
                    double dy = p.y[j] - p.y[i];
                    double dz = p.z[j] - p.z[i];

                    double r2 = (dx * dx) + (dy * dy) + (dz * dz);
                    if (r2 < r_cut2) {
                        double inv_r2 = 1.0 / r2;
                        double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                        double mag = (c12_scalar * inv_r6 - c6_scalar) * inv_r6 * inv_r2;

                        double fx = -mag * dx;
                        double fy = -mag * dy;
                        double fz = -mag * dz;

                        ax += fx; ay += fy; az += fz;
                        p.fx[j] -= fx; p.fy[j] -= fy; p.fz[j] -= fz;
                    }
                }

                // store the reduced forces back to memory
                p.fx[i] += ax;
                p.fy[i] += ay;
                p.fz[i] += az;
            }

            // second half kick
            for (size_t i = 0; i < N; i += V) {
                packed_double v_vx = packed_double::load_unaligned(&p.vx[i]);
                packed_double v_vy = packed_double::load_unaligned(&p.vy[i]);
                packed_double v_vz = packed_double::load_unaligned(&p.vz[i]);

                packed_double v_fx = packed_double::load_unaligned(&p.fx[i]);
                packed_double v_fy = packed_double::load_unaligned(&p.fy[i]);
                packed_double v_fz = packed_double::load_unaligned(&p.fz[i]);

                v_vx += (DT / 2.0 / MASS) * v_fx;
                v_vy += (DT / 2.0 / MASS) * v_fy;
                v_vz += (DT / 2.0 / MASS) * v_fz;

                v_vx.store_unaligned(&p.vx[i]);
                v_vy.store_unaligned(&p.vy[i]);
                v_vz.store_unaligned(&p.vz[i]);
            }
        }

        benchmark::DoNotOptimize(p.fx.data());
        benchmark::ClobberMemory();
    }

    const double total_interactions = static_cast<double>(state.iterations()) * (N * (N - 1) / 2) * STEPS;
    state.SetItemsProcessed(total_interactions);
    state.counters["ns/interaction"] = benchmark::Counter(total_interactions / 1e9, benchmark::Counter::kIsRate | benchmark::Counter::kInvert);
}


// ============================================================================
// APRIL ENGINE
// ============================================================================
template <typename LayoutType, VectorPolicy VPol>
static void BM_April_DirectSum(benchmark::State& state) {
    const int N_DIM = state.range(0);
    const int STEPS = state.range(1);
    const size_t N = N_DIM * N_DIM * N_DIM;

    // Inject the template parameter into the compile-time config
    const struct Cfg :
        RunTimeConfig<exec::SequentialExecutor>,
        CompileTimeConfig<ParallelPolicy::Serial, VPol>
    {} cfg;

    for (auto _ : state) {
        state.PauseTiming();

        // Rebuild pristine state
        const vec3 box = {(N_DIM - 1) * A, (N_DIM - 1) * A, (N_DIM - 1) * A};
        ParticleCuboid grid = ParticleCuboid{}
        .at(-0.5 * box)
        .velocity({0, 0, 0})
        .count({static_cast<size_t>(N_DIM), static_cast<size_t>(N_DIM), static_cast<size_t>(N_DIM)})
        .mass(MASS)
        .spacing(A)
        .type(0);

        Environment env(forces<LennardJones>, boundaries<OpenBoundary>);
        env.add_particles(grid);
        env.add_force(LennardJones(EPSILON, SIGMA, R_CUT), to_type(0));
        env.set_boundaries(OpenBoundary(), all_faces);

        // Inject the layout parameter into the container
        auto container = DirectSum<LayoutType>();
        auto system = build_system(env, container, cfg);
        VelocityVerlet integrator(system);

        state.ResumeTiming();

        // Execute workload
        integrator.run_for_steps(DT, STEPS);

        benchmark::DoNotOptimize(integrator);
        benchmark::ClobberMemory();
    }

    const double total_interactions = static_cast<double>(state.iterations()) * (N * (N - 1) / 2) * STEPS;
    state.SetItemsProcessed(total_interactions);
    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9,
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}





// ------------
// REGISTRATION
// ------------
constexpr  size_t N = 16;
constexpr  size_t STEPS = 500;
BENCHMARK_TEMPLATE(BM_April_DirectSum, Layout::AoS, VectorPolicy::Scalar)->Args({N, STEPS})->Unit(benchmark::kMillisecond);
BENCHMARK_TEMPLATE(BM_April_DirectSum, Layout::SoA, VectorPolicy::Scalar)->Args({N, STEPS})->Unit(benchmark::kMillisecond);
BENCHMARK_TEMPLATE(BM_April_DirectSum, Layout::AoSoA<>, VectorPolicy::Scalar)->Args({N, STEPS})->Unit(benchmark::kMillisecond);

BENCHMARK_TEMPLATE(BM_April_DirectSum, Layout::SoA, VectorPolicy::Auto)->Args({N, STEPS})->Unit(benchmark::kMillisecond);
BENCHMARK_TEMPLATE(BM_April_DirectSum, Layout::AoSoA<>, VectorPolicy::Auto)->Args({N, STEPS})->Unit(benchmark::kMillisecond);
BENCHMARK_TEMPLATE(BM_April_DirectSum, Layout::AoSoA<16>, VectorPolicy::Auto)->Args({N, STEPS})->Unit(benchmark::kMillisecond);
BENCHMARK_TEMPLATE(BM_April_DirectSum, Layout::AoSoA<32>, VectorPolicy::Auto)->Args({N, STEPS})->Unit(benchmark::kMillisecond);

BENCHMARK(BM_Baseline_Handcoded_AoS_Scalar)->Args({N, STEPS})->Unit(benchmark::kMillisecond);
BENCHMARK(BM_Baseline_Handcoded_SoA_Scalar)->Args({N, STEPS})->Unit(benchmark::kMillisecond);
BENCHMARK(BM_Baseline_Handcoded_SoA_2D_SIMD)->Args({N, STEPS})->Unit(benchmark::kMillisecond);
BENCHMARK(BM_Baseline_Handcoded_SoA_1D_SIMD)->Args({N, STEPS})->Unit(benchmark::kMillisecond);


BENCHMARK_MAIN();