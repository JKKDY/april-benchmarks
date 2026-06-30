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
        vec3 force = {};
        vec3 velocity = {};
        vec3 old_position = {};

        double mass {};			// mass of the particle.
        ParticleState state {};	// state of the particle.
        ParticleID id {};		// id of the particle.
        ParticleType type {};	// type of the particle.
    };

    struct StateSoA {
        std::vector<double> x, y, z;
        std::vector<double> fx, fy, fz;
        std::vector<double> vx, vy, vz;
        std::vector<double> ox, oy, oz;

        StateSoA(size_t N) {
            x.resize(N, 0.0);  y.resize(N, 0.0);  z.resize(N, 0.0);
            vx.resize(N, 0.0); vy.resize(N, 0.0); vz.resize(N, 0.0);
            fx.resize(N, 0.0); fy.resize(N, 0.0); fz.resize(N, 0.0);
            ox.resize(N, 0.0); oy.resize(N, 0.0); oz.resize(N, 0.0);
        }
    };

    struct BlockRange {
        size_t start = 0;
        size_t stop = 0;

        [[nodiscard]] bool empty() const {
            return start >= stop;
        }
    };

    static std::vector<BlockRange> make_fixed_blocks(size_t N, size_t block_size) {
        std::vector<BlockRange> blocks;

        if (block_size == 0) {
            block_size = N;
        }

        for (size_t start = 0; start < N; start += block_size) {
            const size_t stop = std::min(N, start + block_size);
            blocks.push_back({start, stop});
        }

        // April's symmetric schedule makes the number of blocks even for
        // round-robin off-diagonal scheduling.
        if (blocks.size() % 2 != 0) {
            blocks.push_back({N, N});
        }

        return blocks;
    }

    static void for_each_symmetric_block_phase(
        const std::vector<BlockRange>& blocks,
        auto&& diagonal_func,
        auto&& offdiag_func)
    {
        const size_t B = blocks.size();
        if (B == 0) return;

        // Phase 0: diagonal blocks.
        for (size_t b = 0; b < B; ++b) {
            if (!blocks[b].empty()) {
                diagonal_func(blocks[b]);
            }
        }

        // Phases 1..B-1: round-robin off-diagonal block pairs.
        std::vector<size_t> circle(B);
        std::iota(circle.begin(), circle.end(), 0);

        for (size_t phase = 0; phase < B - 1; ++phase) {
            for (size_t q = 0; q < B / 2; ++q) {
                const size_t b1_raw = circle[q];
                const size_t b2_raw = circle[B - 1 - q];

                const size_t b1 = std::min(b1_raw, b2_raw);
                const size_t b2 = std::max(b1_raw, b2_raw);

                if (!blocks[b1].empty() && !blocks[b2].empty()) {
                    offdiag_func(blocks[b1], blocks[b2]);
                }
            }

            // Same rotation as April's make_symmetric_schedule:
            // keep index 0 fixed, rotate the rest right.
            const size_t last = circle.back();
            for (size_t i = B - 1; i > 1; --i) {
                circle[i] = circle[i - 1];
            }
            circle[1] = last;
        }
    }

    APRIL_FORCE_INLINE void apply_lj_pair_aos(
        Particle& p1,
        Particle& p2)
    {
        const vec3 r = p2.position - p1.position;
        const double r2 = r.x * r.x + r.y * r.y + r.z * r.z;

        if (r2 < r_cut2) {
            const double inv_r2 = 1.0 / r2;
            const double inv_r6 = inv_r2 * inv_r2 * inv_r2;
            const double mag =
                (c12_scalar * inv_r6 - c6_scalar) * inv_r6 * inv_r2;

            const vec3 f = r * -mag;

            p1.force += f;
            p2.force -= f;
        }
    }

}



static void BM_Baseline_Handcoded_AoS_Scalar_Batched(benchmark::State& state) {
    const int N_DIM = state.range(0);
    const int STEPS = state.range(1);
    const size_t BLOCK = static_cast<size_t>(state.range(2));
    const size_t N = static_cast<size_t>(N_DIM) * N_DIM * N_DIM;

    const double off_x = -0.5 * (N_DIM - 1) * A;
    const double off_y = -0.5 * (N_DIM - 1) * A;
    const double off_z = -0.5 * (N_DIM - 1) * A;

    const auto blocks = baseline::make_fixed_blocks(N, BLOCK);

    for (auto _ : state) {
        state.PauseTiming();

        std::vector<baseline::Particle> particles(N);

        size_t idx = 0;
        for (int k = 0; k < N_DIM; ++k) {
            for (int j = 0; j < N_DIM; ++j) {
                for (int i = 0; i < N_DIM; ++i) {
                    particles[idx].position = {
                        i * A + off_x,
                        j * A + off_y,
                        k * A + off_z
                    };
                    particles[idx].force = {};
                    particles[idx].velocity = {};
                    particles[idx].old_position = {};
                    ++idx;
                }
            }
        }

        state.ResumeTiming();

        for (int step = 0; step < STEPS; ++step) {
            // First half kick + drift + force reset.
            for (auto& p : particles) {
                p.old_position = p.position;
                p.velocity += (DT / 2.0) * (p.force / MASS);
                p.position += DT * p.velocity;
                p.force = {};
            }

            baseline::for_each_symmetric_block_phase(
                blocks,

                // Diagonal block: upper triangle within one block.
                [&](const baseline::BlockRange& block) {
                    for (size_t i = block.start; i < block.stop; ++i) {
                        auto& p1 = particles[i];

                        for (size_t j = i + 1; j < block.stop; ++j) {
                            auto& p2 = particles[j];
                            baseline::apply_lj_pair_aos(p1, p2);
                        }
                    }
                },

                // Off-diagonal block pair: full rectangle.
                [&](const baseline::BlockRange& block1,
                    const baseline::BlockRange& block2) {
                    for (size_t i = block1.start; i < block1.stop; ++i) {
                        auto& p1 = particles[i];

                        for (size_t j = block2.start; j < block2.stop; ++j) {
                            auto& p2 = particles[j];
                            baseline::apply_lj_pair_aos(p1, p2);
                        }
                    }
                }
            );

            // Second half kick.
            for (auto& p : particles) {
                p.velocity += (DT / 2.0) * (p.force / MASS);
            }
        }

        double checksum = 0.0;
        for (const auto& p : particles) {
            checksum += p.position.x + p.position.y + p.position.z;
            checksum += p.velocity.x + p.velocity.y + p.velocity.z;
            checksum += p.force.x + p.force.y + p.force.z;
        }

        benchmark::DoNotOptimize(checksum);
        benchmark::DoNotOptimize(particles.data());
        benchmark::ClobberMemory();
    }

    const double total_interactions =
        static_cast<double>(state.iterations()) * (N * (N - 1) / 2) * STEPS;

    state.SetItemsProcessed(total_interactions);
    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9,
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}


static void BM_Baseline_Handcoded_SoA_Scalar_Batched(benchmark::State& state) {
    const int N_DIM = state.range(0);
    const int STEPS = state.range(1);
    const size_t BLOCK = static_cast<size_t>(state.range(2));
    const size_t N = static_cast<size_t>(N_DIM) * N_DIM * N_DIM;

    const double off_x = -0.5 * (N_DIM - 1) * A;
    const double off_y = -0.5 * (N_DIM - 1) * A;
    const double off_z = -0.5 * (N_DIM - 1) * A;

    const double half_dt_over_mass = (DT / 2.0) / MASS;

    const auto blocks = baseline::make_fixed_blocks(N, BLOCK);

    for (auto _ : state) {
        state.PauseTiming();

        baseline::StateSoA p(N);

        size_t idx = 0;
        for (int k = 0; k < N_DIM; ++k) {
            for (int j = 0; j < N_DIM; ++j) {
                for (int i = 0; i < N_DIM; ++i) {
                    p.x[idx] = i * A + off_x;
                    p.y[idx] = j * A + off_y;
                    p.z[idx] = k * A + off_z;
                    ++idx;
                }
            }
        }

        state.ResumeTiming();

        for (int step = 0; step < STEPS; ++step) {
            // First half kick + drift + force reset.
            for (size_t i = 0; i < N; ++i) {
                p.ox[i] = p.x[i];
                p.oy[i] = p.y[i];
                p.oz[i] = p.z[i];

                p.vx[i] += half_dt_over_mass * p.fx[i];
                p.vy[i] += half_dt_over_mass * p.fy[i];
                p.vz[i] += half_dt_over_mass * p.fz[i];

                p.x[i] += DT * p.vx[i];
                p.y[i] += DT * p.vy[i];
                p.z[i] += DT * p.vz[i];

                p.fx[i] = 0.0;
                p.fy[i] = 0.0;
                p.fz[i] = 0.0;
            }

            baseline::for_each_symmetric_block_phase(
                blocks,

                // Diagonal block: upper triangle inside one block.
                [&](const baseline::BlockRange& block) {
                    for (size_t i = block.start; i < block.stop; ++i) {
                        for (size_t j = i + 1; j < block.stop; ++j) {
                            const double dx = p.x[j] - p.x[i];
                            const double dy = p.y[j] - p.y[i];
                            const double dz = p.z[j] - p.z[i];

                            const double r2 = dx * dx + dy * dy + dz * dz;

                            if (r2 < r_cut2) {
                                const double inv_r2 = 1.0 / r2;
                                const double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                                const double mag =
                                    (c12_scalar * inv_r6 - c6_scalar) * inv_r6 * inv_r2;

                                const double fx = -mag * dx;
                                const double fy = -mag * dy;
                                const double fz = -mag * dz;

                                p.fx[i] += fx;
                                p.fy[i] += fy;
                                p.fz[i] += fz;

                                p.fx[j] -= fx;
                                p.fy[j] -= fy;
                                p.fz[j] -= fz;
                            }
                        }
                    }
                },

                // Off-diagonal block pair: full rectangle.
                [&](const baseline::BlockRange& block1,
                    const baseline::BlockRange& block2) {
                    for (size_t i = block1.start; i < block1.stop; ++i) {
                        for (size_t j = block2.start; j < block2.stop; ++j) {
                            const double dx = p.x[j] - p.x[i];
                            const double dy = p.y[j] - p.y[i];
                            const double dz = p.z[j] - p.z[i];

                            const double r2 = dx * dx + dy * dy + dz * dz;

                            if (r2 < r_cut2) {
                                const double inv_r2 = 1.0 / r2;
                                const double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                                const double mag =
                                    (c12_scalar * inv_r6 - c6_scalar) * inv_r6 * inv_r2;

                                const double fx = -mag * dx;
                                const double fy = -mag * dy;
                                const double fz = -mag * dz;

                                p.fx[i] += fx;
                                p.fy[i] += fy;
                                p.fz[i] += fz;

                                p.fx[j] -= fx;
                                p.fy[j] -= fy;
                                p.fz[j] -= fz;
                            }
                        }
                    }
                }
            );

            // Second half kick.
            for (size_t i = 0; i < N; ++i) {
                p.vx[i] += half_dt_over_mass * p.fx[i];
                p.vy[i] += half_dt_over_mass * p.fy[i];
                p.vz[i] += half_dt_over_mass * p.fz[i];
            }
        }

        double checksum = 0.0;
        for (size_t i = 0; i < N; ++i) {
            checksum += p.x[i] + p.y[i] + p.z[i];
            checksum += p.vx[i] + p.vy[i] + p.vz[i];
            checksum += p.fx[i] + p.fy[i] + p.fz[i];
        }

        benchmark::DoNotOptimize(checksum);
        benchmark::DoNotOptimize(p.fx.data());
        benchmark::DoNotOptimize(p.fy.data());
        benchmark::DoNotOptimize(p.fz.data());
        benchmark::ClobberMemory();
    }

    const double total_interactions =
        static_cast<double>(state.iterations()) * (N * (N - 1) / 2) * STEPS;

    state.SetItemsProcessed(total_interactions);
    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9,
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}



static void BM_Baseline_Handcoded_SoA_Scalar_BatchedLocalAcc(benchmark::State& state) {
    const int N_DIM = state.range(0);
    const int STEPS = state.range(1);
    const size_t BLOCK = static_cast<size_t>(state.range(2));
    const size_t N = static_cast<size_t>(N_DIM) * N_DIM * N_DIM;

    const double off_x = -0.5 * (N_DIM - 1) * A;
    const double off_y = -0.5 * (N_DIM - 1) * A;
    const double off_z = -0.5 * (N_DIM - 1) * A;

    const double half_dt_over_mass = (DT / 2.0) / MASS;

    const auto blocks = baseline::make_fixed_blocks(N, BLOCK);

    for (auto _ : state) {
        state.PauseTiming();

        baseline::StateSoA p(N);

        size_t idx = 0;
        for (int k = 0; k < N_DIM; ++k) {
            for (int j = 0; j < N_DIM; ++j) {
                for (int i = 0; i < N_DIM; ++i) {
                    p.x[idx] = i * A + off_x;
                    p.y[idx] = j * A + off_y;
                    p.z[idx] = k * A + off_z;
                    ++idx;
                }
            }
        }

        state.ResumeTiming();

        for (int step = 0; step < STEPS; ++step) {
            // First half kick + drift + force reset.
            for (size_t i = 0; i < N; ++i) {
                p.ox[i] = p.x[i];
                p.oy[i] = p.y[i];
                p.oz[i] = p.z[i];

                p.vx[i] += half_dt_over_mass * p.fx[i];
                p.vy[i] += half_dt_over_mass * p.fy[i];
                p.vz[i] += half_dt_over_mass * p.fz[i];

                p.x[i] += DT * p.vx[i];
                p.y[i] += DT * p.vy[i];
                p.z[i] += DT * p.vz[i];

                p.fx[i] = 0.0;
                p.fy[i] = 0.0;
                p.fz[i] = 0.0;
            }

            baseline::for_each_symmetric_block_phase(
                blocks,

                // Diagonal block: upper triangle inside the block.
                // Local accumulation is scoped to this diagonal batch.
                [&](const baseline::BlockRange& block) {
                    for (size_t i = block.start; i < block.stop; ++i) {
                        const double xi = p.x[i];
                        const double yi = p.y[i];
                        const double zi = p.z[i];

                        double fix = 0.0;
                        double fiy = 0.0;
                        double fiz = 0.0;

                        for (size_t j = i + 1; j < block.stop; ++j) {
                            const double dx = p.x[j] - xi;
                            const double dy = p.y[j] - yi;
                            const double dz = p.z[j] - zi;

                            const double r2 = dx * dx + dy * dy + dz * dz;

                            if (r2 < r_cut2) {
                                const double inv_r2 = 1.0 / r2;
                                const double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                                const double mag =
                                    (c12_scalar * inv_r6 - c6_scalar) * inv_r6 * inv_r2;

                                const double fx = -mag * dx;
                                const double fy = -mag * dy;
                                const double fz = -mag * dz;

                                fix += fx;
                                fiy += fy;
                                fiz += fz;

                                p.fx[j] -= fx;
                                p.fy[j] -= fy;
                                p.fz[j] -= fz;
                            }
                        }

                        p.fx[i] += fix;
                        p.fy[i] += fiy;
                        p.fz[i] += fiz;
                    }
                },

                // Off-diagonal block pair: full rectangle.
                // Local accumulation is scoped to this block-pair batch.
                [&](const baseline::BlockRange& block1,
                    const baseline::BlockRange& block2) {
                    for (size_t i = block1.start; i < block1.stop; ++i) {
                        const double xi = p.x[i];
                        const double yi = p.y[i];
                        const double zi = p.z[i];

                        double fix = 0.0;
                        double fiy = 0.0;
                        double fiz = 0.0;

                        for (size_t j = block2.start; j < block2.stop; ++j) {
                            const double dx = p.x[j] - xi;
                            const double dy = p.y[j] - yi;
                            const double dz = p.z[j] - zi;

                            const double r2 = dx * dx + dy * dy + dz * dz;

                            if (r2 < r_cut2) {
                                const double inv_r2 = 1.0 / r2;
                                const double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                                const double mag =
                                    (c12_scalar * inv_r6 - c6_scalar) * inv_r6 * inv_r2;

                                const double fx = -mag * dx;
                                const double fy = -mag * dy;
                                const double fz = -mag * dz;

                                fix += fx;
                                fiy += fy;
                                fiz += fz;

                                p.fx[j] -= fx;
                                p.fy[j] -= fy;
                                p.fz[j] -= fz;
                            }
                        }

                        p.fx[i] += fix;
                        p.fy[i] += fiy;
                        p.fz[i] += fiz;
                    }
                }
            );

            // Second half kick.
            for (size_t i = 0; i < N; ++i) {
                p.vx[i] += half_dt_over_mass * p.fx[i];
                p.vy[i] += half_dt_over_mass * p.fy[i];
                p.vz[i] += half_dt_over_mass * p.fz[i];
            }
        }

        double checksum = 0.0;
        for (size_t i = 0; i < N; ++i) {
            checksum += p.x[i] + p.y[i] + p.z[i];
            checksum += p.vx[i] + p.vy[i] + p.vz[i];
            checksum += p.fx[i] + p.fy[i] + p.fz[i];
        }

        benchmark::DoNotOptimize(checksum);
        benchmark::DoNotOptimize(p.fx.data());
        benchmark::DoNotOptimize(p.fy.data());
        benchmark::DoNotOptimize(p.fz.data());
        benchmark::ClobberMemory();
    }

    const double total_interactions =
        static_cast<double>(state.iterations()) * (N * (N - 1) / 2) * STEPS;

    state.SetItemsProcessed(total_interactions);
    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9,
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
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
            for (auto& p : particles) {
                p.old_position = p.position;
                p.velocity += (DT / 2.0) * (p.force / MASS);
                p.position += DT * p.velocity;
                p.force = {};
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


static void BM_Baseline_Handcoded_SoA_Scalar_LocalAcc(benchmark::State& state) {
    const int N_DIM = state.range(0);
    const int STEPS = state.range(1);
    const size_t N = N_DIM * N_DIM * N_DIM;

    const double off_x = -0.5 * (N_DIM - 1) * A;
    const double off_y = -0.5 * (N_DIM - 1) * A;
    const double off_z = -0.5 * (N_DIM - 1) * A;

    for (auto _ : state) {
        state.PauseTiming();

        baseline::StateSoA p(N);

        size_t idx = 0;
        for (int k = 0; k < N_DIM; ++k) {
            for (int j = 0; j < N_DIM; ++j) {
                for (int i = 0; i < N_DIM; ++i) {
                    p.x[idx] = i * A + off_x;
                    p.y[idx] = j * A + off_y;
                    p.z[idx] = k * A + off_z;
                    ++idx;
                }
            }
        }

        state.ResumeTiming();

        for (int step = 0; step < STEPS; ++step) {
            // First half kick + drift + force reset.
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

                p.fx[i] = 0.0;
                p.fy[i] = 0.0;
                p.fz[i] = 0.0;
            }

            // Force accumulation with local accumulator for particle i.
            for (size_t i = 0; i < N; ++i) {
                const double xi = p.x[i];
                const double yi = p.y[i];
                const double zi = p.z[i];

                double fi_x = 0.0;
                double fi_y = 0.0;
                double fi_z = 0.0;

                for (size_t j = i + 1; j < N; ++j) {
                    const double dx = p.x[j] - xi;
                    const double dy = p.y[j] - yi;
                    const double dz = p.z[j] - zi;

                    const double r2 = dx * dx + dy * dy + dz * dz;

                    if (r2 < r_cut2) {
                        const double inv_r2 = 1.0 / r2;
                        const double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                        const double mag =
                            (c12_scalar * inv_r6 - c6_scalar) * inv_r6 * inv_r2;

                        const double fx = -mag * dx;
                        const double fy = -mag * dy;
                        const double fz = -mag * dz;

                        // Accumulate i locally in registers.
                        fi_x += fx;
                        fi_y += fy;
                        fi_z += fz;

                        // j still updates memory directly.
                        p.fx[j] -= fx;
                        p.fy[j] -= fy;
                        p.fz[j] -= fz;
                    }
                }

                // One writeback for particle i.
                p.fx[i] += fi_x;
                p.fy[i] += fi_y;
                p.fz[i] += fi_z;
            }

            // Second half kick.
            for (size_t i = 0; i < N; ++i) {
                p.vx[i] += (DT / 2.0) * (p.fx[i] / MASS);
                p.vy[i] += (DT / 2.0) * (p.fy[i] / MASS);
                p.vz[i] += (DT / 2.0) * (p.fz[i] / MASS);
            }
        }

        benchmark::DoNotOptimize(p.fx.data());
        benchmark::DoNotOptimize(p.fy.data());
        benchmark::DoNotOptimize(p.fz.data());
        benchmark::ClobberMemory();
    }

    const double total_interactions =
        static_cast<double>(state.iterations()) * (N * (N - 1) / 2) * STEPS;

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

        baseline::StateSoA p(N);
        size_t idx = 0;
        for (int k = 0; k < N_DIM; ++k) {
            for (int j = 0; j < N_DIM; ++j) {
                for (int i = 0; i < N_DIM; ++i) {
                    p.x[idx] = i * A + off_x;
                    p.y[idx] = j * A + off_y;
                    p.z[idx] = k * A + off_z;
                    idx++;
                }
            }
        }

        state.ResumeTiming();

        for (int step = 0; step < STEPS; ++step) {
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

                p.fx[i] = 0.0;
                p.fy[i] = 0.0;
                p.fz[i] = 0.0;
            }

            for (size_t i = 0; i < N; ++i) {
                for (size_t j = i + 1; j < N; ++j) {
                    const double dx = p.x[j] - p.x[i];
                    const double dy = p.y[j] - p.y[i];
                    const double dz = p.z[j] - p.z[i];

                    const double r2 = dx * dx + dy * dy + dz * dz;

                    if (r2 < r_cut2) {
                        const double inv_r2 = 1.0 / r2;
                        const double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                        const double mag = (c12_scalar * inv_r6 - c6_scalar) * inv_r6 * inv_r2;

                        const double fx = -mag * dx;
                        const double fy = -mag * dy;
                        const double fz = -mag * dz;

                        p.fx[i] += fx;
                        p.fy[i] += fy;
                        p.fz[i] += fz;

                        p.fx[j] -= fx;
                        p.fy[j] -= fy;
                        p.fz[j] -= fz;
                    }
                }
            }

            for (size_t i = 0; i < N; ++i) {
                p.vx[i] += (DT / 2.0) * (p.fx[i] / MASS);
                p.vy[i] += (DT / 2.0) * (p.fy[i] / MASS);
                p.vz[i] += (DT / 2.0) * (p.fz[i] / MASS);
            }
        }

        benchmark::DoNotOptimize(p.fx.data());
        benchmark::DoNotOptimize(p.fy.data());
        benchmark::DoNotOptimize(p.fz.data());
        benchmark::ClobberMemory();
    }

    const double total_interactions =
        static_cast<double>(state.iterations()) * (N * (N - 1) / 2) * STEPS;

    state.SetItemsProcessed(total_interactions);
    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9,
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}


static void BM_Baseline_Handcoded_SoA_Scalar_Restrict(benchmark::State& state) {
    const int N_DIM = state.range(0);
    const int STEPS = state.range(1);
    const size_t N = static_cast<size_t>(N_DIM) * N_DIM * N_DIM;

    const double off_x = -0.5 * (N_DIM - 1) * A;
    const double off_y = -0.5 * (N_DIM - 1) * A;
    const double off_z = -0.5 * (N_DIM - 1) * A;

    const double half_dt_over_mass = (DT / 2.0) / MASS;

    for (auto _ : state) {
        state.PauseTiming();

        baseline::StateSoA p(N);

        size_t idx = 0;
        for (int k = 0; k < N_DIM; ++k) {
            for (int j = 0; j < N_DIM; ++j) {
                for (int i = 0; i < N_DIM; ++i) {
                    p.x[idx] = i * A + off_x;
                    p.y[idx] = j * A + off_y;
                    p.z[idx] = k * A + off_z;
                    ++idx;
                }
            }
        }

        double* APRIL_RESTRICT x  = p.x.data();
        double* APRIL_RESTRICT y  = p.y.data();
        double* APRIL_RESTRICT z  = p.z.data();

        double* APRIL_RESTRICT fx_arr = p.fx.data();
        double* APRIL_RESTRICT fy_arr = p.fy.data();
        double* APRIL_RESTRICT fz_arr = p.fz.data();

        double* APRIL_RESTRICT vx = p.vx.data();
        double* APRIL_RESTRICT vy = p.vy.data();
        double* APRIL_RESTRICT vz = p.vz.data();

        double* APRIL_RESTRICT ox = p.ox.data();
        double* APRIL_RESTRICT oy = p.oy.data();
        double* APRIL_RESTRICT oz = p.oz.data();

        state.ResumeTiming();

        for (int step = 0; step < STEPS; ++step) {
            for (size_t i = 0; i < N; ++i) {
                ox[i] = x[i];
                oy[i] = y[i];
                oz[i] = z[i];

                vx[i] += half_dt_over_mass * fx_arr[i];
                vy[i] += half_dt_over_mass * fy_arr[i];
                vz[i] += half_dt_over_mass * fz_arr[i];

                x[i] += DT * vx[i];
                y[i] += DT * vy[i];
                z[i] += DT * vz[i];

                fx_arr[i] = 0.0;
                fy_arr[i] = 0.0;
                fz_arr[i] = 0.0;
            }

            for (size_t i = 0; i < N; ++i) {
                for (size_t j = i + 1; j < N; ++j) {
                    [[assume(i != j)]]; // C++23 standard
                    __builtin_assume(i != j);
                    const double dx = x[j] - x[i];
                    const double dy = y[j] - y[i];
                    const double dz = z[j] - z[i];

                    const double r2 = dx * dx + dy * dy + dz * dz;

                    if (r2 < r_cut2) {
                        const double inv_r2 = 1.0 / r2;
                        const double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                        const double mag =
                            (c12_scalar * inv_r6 - c6_scalar) * inv_r6 * inv_r2;

                        const double fx = -mag * dx;
                        const double fy = -mag * dy;
                        const double fz = -mag * dz;

                        fx_arr[i] += fx;
                        fy_arr[i] += fy;
                        fz_arr[i] += fz;

                        fx_arr[j] -= fx;
                        fy_arr[j] -= fy;
                        fz_arr[j] -= fz;
                    }
                }
            }

            for (size_t i = 0; i < N; ++i) {
                vx[i] += half_dt_over_mass * fx_arr[i];
                vy[i] += half_dt_over_mass * fy_arr[i];
                vz[i] += half_dt_over_mass * fz_arr[i];
            }
        }

        benchmark::DoNotOptimize(x);
        benchmark::DoNotOptimize(y);
        benchmark::DoNotOptimize(z);
        benchmark::DoNotOptimize(fx_arr);
        benchmark::DoNotOptimize(fy_arr);
        benchmark::DoNotOptimize(fz_arr);
        benchmark::ClobberMemory();
    }

    const double total_interactions =
        static_cast<double>(state.iterations()) * (N * (N - 1) / 2) * STEPS;

    state.SetItemsProcessed(total_interactions);
    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9,
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}

static void BM_Baseline_Handcoded_SoA_Scalar_RestrictLocalAcc(benchmark::State& state) {
    const int N_DIM = state.range(0);
    const int STEPS = state.range(1);
    const size_t N = static_cast<size_t>(N_DIM) * N_DIM * N_DIM;

    const double off_x = -0.5 * (N_DIM - 1) * A;
    const double off_y = -0.5 * (N_DIM - 1) * A;
    const double off_z = -0.5 * (N_DIM - 1) * A;

    const double half_dt_over_mass = (DT / 2.0) / MASS;

    for (auto _ : state) {
        state.PauseTiming();

        baseline::StateSoA p(N);

        size_t idx = 0;
        for (int k = 0; k < N_DIM; ++k) {
            for (int j = 0; j < N_DIM; ++j) {
                for (int i = 0; i < N_DIM; ++i) {
                    p.x[idx] = i * A + off_x;
                    p.y[idx] = j * A + off_y;
                    p.z[idx] = k * A + off_z;
                    ++idx;
                }
            }
        }

        double* APRIL_RESTRICT x  = p.x.data();
        double* APRIL_RESTRICT y  = p.y.data();
        double* APRIL_RESTRICT z  = p.z.data();

        double* APRIL_RESTRICT fx_arr = p.fx.data();
        double* APRIL_RESTRICT fy_arr = p.fy.data();
        double* APRIL_RESTRICT fz_arr = p.fz.data();

        double* APRIL_RESTRICT vx = p.vx.data();
        double* APRIL_RESTRICT vy = p.vy.data();
        double* APRIL_RESTRICT vz = p.vz.data();

        double* APRIL_RESTRICT ox = p.ox.data();
        double* APRIL_RESTRICT oy = p.oy.data();
        double* APRIL_RESTRICT oz = p.oz.data();

        state.ResumeTiming();

        for (int step = 0; step < STEPS; ++step) {
            for (size_t i = 0; i < N; ++i) {
                ox[i] = x[i];
                oy[i] = y[i];
                oz[i] = z[i];

                vx[i] += half_dt_over_mass * fx_arr[i];
                vy[i] += half_dt_over_mass * fy_arr[i];
                vz[i] += half_dt_over_mass * fz_arr[i];

                x[i] += DT * vx[i];
                y[i] += DT * vy[i];
                z[i] += DT * vz[i];

                fx_arr[i] = 0.0;
                fy_arr[i] = 0.0;
                fz_arr[i] = 0.0;
            }

            for (size_t i = 0; i < N; ++i) {
                const double xi = x[i];
                const double yi = y[i];
                const double zi = z[i];

                double fix = 0.0;
                double fiy = 0.0;
                double fiz = 0.0;

                for (size_t j = i + 1; j < N; ++j) {

                     [[assume(i != j)]]; // C++23 standard
                    __builtin_assume(i != j);
                    
                    const double dx = x[j] - xi;
                    const double dy = y[j] - yi;
                    const double dz = z[j] - zi;

                    const double r2 = dx * dx + dy * dy + dz * dz;

                    if (r2 < r_cut2) {
                        const double inv_r2 = 1.0 / r2;
                        const double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                        const double mag =
                            (c12_scalar * inv_r6 - c6_scalar) * inv_r6 * inv_r2;

                        const double fx = -mag * dx;
                        const double fy = -mag * dy;
                        const double fz = -mag * dz;

                        fix += fx;
                        fiy += fy;
                        fiz += fz;

                        fx_arr[j] -= fx;
                        fy_arr[j] -= fy;
                        fz_arr[j] -= fz;
                    }
                }

                fx_arr[i] += fix;
                fy_arr[i] += fiy;
                fz_arr[i] += fiz;
            }

            for (size_t i = 0; i < N; ++i) {
                vx[i] += half_dt_over_mass * fx_arr[i];
                vy[i] += half_dt_over_mass * fy_arr[i];
                vz[i] += half_dt_over_mass * fz_arr[i];
            }
        }

        benchmark::DoNotOptimize(x);
        benchmark::DoNotOptimize(y);
        benchmark::DoNotOptimize(z);
        benchmark::DoNotOptimize(fx_arr);
        benchmark::DoNotOptimize(fy_arr);
        benchmark::DoNotOptimize(fz_arr);
        benchmark::ClobberMemory();
    }

    const double total_interactions =
        static_cast<double>(state.iterations()) * (N * (N - 1) / 2) * STEPS;

    state.SetItemsProcessed(total_interactions);
    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9,
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}


static void BM_Baseline_Handcoded_SoA_Rotate_SIMD(benchmark::State& state) {

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


static void BM_Baseline_Handcoded_SoA_Rotate_SIMD_Batched(benchmark::State& state) {
    using packed_double = april::simd::internal::xsimd::Packed<double>;

    const int N_DIM = state.range(0);
    const int STEPS = state.range(1);
    const size_t BATCH = static_cast<size_t>(state.range(2));
    const size_t N = static_cast<size_t>(N_DIM) * N_DIM * N_DIM;

    constexpr size_t V = packed_double::size();

    if ((N % V) != 0) {
        state.SkipWithError("Requires N to be a multiple of SIMD width.");
        return;
    }

    if ((BATCH % V) != 0) {
        state.SkipWithError("Requires BATCH to be a multiple of SIMD width.");
        return;
    }

    if ((N % BATCH) != 0) {
        state.SkipWithError("This simple batched SIMD benchmark requires N % BATCH == 0.");
        return;
    }

    const double off_x = -0.5 * (N_DIM - 1) * A;
    const double off_y = -0.5 * (N_DIM - 1) * A;
    const double off_z = -0.5 * (N_DIM - 1) * A;

    const packed_double v_c6 = c6_scalar;
    const packed_double v_c12 = c12_scalar;
    const packed_double v_one = 1.0;
    const packed_double v_rcut2 = r_cut2;

    const auto blocks = baseline::make_fixed_blocks(N, BATCH);

    for (auto _ : state) {
        state.PauseTiming();

        baseline::StateSoA p(N);

        size_t idx = 0;
        for (int k = 0; k < N_DIM; ++k) {
            for (int j = 0; j < N_DIM; ++j) {
                for (int i = 0; i < N_DIM; ++i) {
                    p.x[idx] = i * A + off_x;
                    p.y[idx] = j * A + off_y;
                    p.z[idx] = k * A + off_z;
                    ++idx;
                }
            }
        }

        const packed_double zero = 0.0;

        state.ResumeTiming();

        for (int step = 0; step < STEPS; ++step) {
            // First half kick + drift + force reset.
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

            baseline::for_each_symmetric_block_phase(
                blocks,

                // ----------------------------------------------------
                // Diagonal batch: interactions inside one 512-particle block.
                // ----------------------------------------------------
                [&](const baseline::BlockRange& block) {
                    for (size_t i = block.start; i < block.stop; i += V) {
                        packed_double v_xi = packed_double::load_unaligned(&p.x[i]);
                        packed_double v_yi = packed_double::load_unaligned(&p.y[i]);
                        packed_double v_zi = packed_double::load_unaligned(&p.z[i]);

                        packed_double v_fxi = packed_double::load_unaligned(&p.fx[i]);
                        packed_double v_fyi = packed_double::load_unaligned(&p.fy[i]);
                        packed_double v_fzi = packed_double::load_unaligned(&p.fz[i]);

                        // Intra-vector self-interaction.
                        {
                            packed_double v_xj = v_xi;
                            packed_double v_yj = v_yi;
                            packed_double v_zj = v_zi;

                            packed_double acc_fxj = 0.0;
                            packed_double acc_fyj = 0.0;
                            packed_double acc_fzj = 0.0;

                            APRIL_UNROLL_LOOP()
                            for (size_t k = 0; k < V / 2 - 1; ++k) {
                                v_xj = v_xj.rotate_right();
                                v_yj = v_yj.rotate_right();
                                v_zj = v_zj.rotate_right();

                                acc_fxj = acc_fxj.rotate_right();
                                acc_fyj = acc_fyj.rotate_right();
                                acc_fzj = acc_fzj.rotate_right();

                                const packed_double dx = v_xj - v_xi;
                                const packed_double dy = v_yj - v_yi;
                                const packed_double dz = v_zj - v_zi;

                                const packed_double r2 = dx * dx + dy * dy + dz * dz;
                                const auto outside = r2 > v_rcut2;

                                if (!all(outside)) {
                                    const packed_double inv_r2 = v_one / r2;
                                    const packed_double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                                    const packed_double mag = select(
                                        outside,
                                        packed_double(0.0),
                                        (v_c12 * inv_r6 - v_c6) * inv_r6 * inv_r2
                                    );

                                    const packed_double fx = -mag * dx;
                                    const packed_double fy = -mag * dy;
                                    const packed_double fz = -mag * dz;

                                    v_fxi += fx;
                                    v_fyi += fy;
                                    v_fzi += fz;

                                    acc_fxj -= fx;
                                    acc_fyj -= fy;
                                    acc_fzj -= fz;
                                }
                            }

                            acc_fxj = acc_fxj.template rotate_left<V / 2 - 1>();
                            acc_fyj = acc_fyj.template rotate_left<V / 2 - 1>();
                            acc_fzj = acc_fzj.template rotate_left<V / 2 - 1>();

                            v_fxi += acc_fxj;
                            v_fyi += acc_fyj;
                            v_fzi += acc_fzj;

                            // 180-degree case.
                            v_xj = v_xj.rotate_right();
                            v_yj = v_yj.rotate_right();
                            v_zj = v_zj.rotate_right();

                            const packed_double dx = v_xj - v_xi;
                            const packed_double dy = v_yj - v_yi;
                            const packed_double dz = v_zj - v_zi;

                            const packed_double r2 = dx * dx + dy * dy + dz * dz;
                            const auto outside = r2 > v_rcut2;

                            if (!all(outside)) {
                                const packed_double inv_r2 = v_one / r2;
                                const packed_double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                                const packed_double mag = select(
                                    outside,
                                    packed_double(0.0),
                                    (v_c12 * inv_r6 - v_c6) * inv_r6 * inv_r2
                                );

                                const packed_double fx = -mag * dx;
                                const packed_double fy = -mag * dy;
                                const packed_double fz = -mag * dz;

                                v_fxi += fx;
                                v_fyi += fy;
                                v_fzi += fz;
                            }
                        }

                        // Inter-vector interactions within the same 512-particle block.
                        for (size_t j = i + V; j < block.stop; j += V) {
                            packed_double v_xj = packed_double::load_unaligned(&p.x[j]);
                            packed_double v_yj = packed_double::load_unaligned(&p.y[j]);
                            packed_double v_zj = packed_double::load_unaligned(&p.z[j]);

                            packed_double v_fxj = packed_double::load_unaligned(&p.fx[j]);
                            packed_double v_fyj = packed_double::load_unaligned(&p.fy[j]);
                            packed_double v_fzj = packed_double::load_unaligned(&p.fz[j]);

                            APRIL_UNROLL_LOOP_N(V)
                            for (size_t k = 0; k < V; ++k) {
                                const packed_double dx = v_xj - v_xi;
                                const packed_double dy = v_yj - v_yi;
                                const packed_double dz = v_zj - v_zi;

                                const packed_double r2 = dx * dx + dy * dy + dz * dz;
                                const auto outside = r2 > v_rcut2;

                                if (!all(outside)) {
                                    const packed_double inv_r2 = v_one / r2;
                                    const packed_double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                                    const packed_double mag = select(
                                        outside,
                                        packed_double(0.0),
                                        (v_c12 * inv_r6 - v_c6) * inv_r6 * inv_r2
                                    );

                                    const packed_double fx = -mag * dx;
                                    const packed_double fy = -mag * dy;
                                    const packed_double fz = -mag * dz;

                                    v_fxi += fx;
                                    v_fyi += fy;
                                    v_fzi += fz;

                                    v_fxj -= fx;
                                    v_fyj -= fy;
                                    v_fzj -= fz;
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
                },

                // ----------------------------------------------------
                // Off-diagonal batch: full rectangle block1 x block2.
                // ----------------------------------------------------
                [&](const baseline::BlockRange& block1,
                    const baseline::BlockRange& block2) {
                    for (size_t i = block1.start; i < block1.stop; i += V) {
                        packed_double v_xi = packed_double::load_unaligned(&p.x[i]);
                        packed_double v_yi = packed_double::load_unaligned(&p.y[i]);
                        packed_double v_zi = packed_double::load_unaligned(&p.z[i]);

                        packed_double v_fxi = packed_double::load_unaligned(&p.fx[i]);
                        packed_double v_fyi = packed_double::load_unaligned(&p.fy[i]);
                        packed_double v_fzi = packed_double::load_unaligned(&p.fz[i]);

                        for (size_t j = block2.start; j < block2.stop; j += V) {
                            packed_double v_xj = packed_double::load_unaligned(&p.x[j]);
                            packed_double v_yj = packed_double::load_unaligned(&p.y[j]);
                            packed_double v_zj = packed_double::load_unaligned(&p.z[j]);

                            packed_double v_fxj = packed_double::load_unaligned(&p.fx[j]);
                            packed_double v_fyj = packed_double::load_unaligned(&p.fy[j]);
                            packed_double v_fzj = packed_double::load_unaligned(&p.fz[j]);

                            APRIL_UNROLL_LOOP_N(V)
                            for (size_t k = 0; k < V; ++k) {
                                const packed_double dx = v_xj - v_xi;
                                const packed_double dy = v_yj - v_yi;
                                const packed_double dz = v_zj - v_zi;

                                const packed_double r2 = dx * dx + dy * dy + dz * dz;
                                const auto outside = r2 > v_rcut2;

                                if (!all(outside)) {
                                    const packed_double inv_r2 = v_one / r2;
                                    const packed_double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                                    const packed_double mag = select(
                                        outside,
                                        packed_double(0.0),
                                        (v_c12 * inv_r6 - v_c6) * inv_r6 * inv_r2
                                    );

                                    const packed_double fx = -mag * dx;
                                    const packed_double fy = -mag * dy;
                                    const packed_double fz = -mag * dz;

                                    v_fxi += fx;
                                    v_fyi += fy;
                                    v_fzi += fz;

                                    v_fxj -= fx;
                                    v_fyj -= fy;
                                    v_fzj -= fz;
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
                }
            );

            // Second half kick.
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

        double checksum = 0.0;
        for (size_t i = 0; i < N; ++i) {
            checksum += p.x[i] + p.y[i] + p.z[i];
            checksum += p.vx[i] + p.vy[i] + p.vz[i];
            checksum += p.fx[i] + p.fy[i] + p.fz[i];
        }

        benchmark::DoNotOptimize(checksum);
        benchmark::DoNotOptimize(p.fx.data());
        benchmark::ClobberMemory();
    }

    const double total_interactions =
        static_cast<double>(state.iterations()) * (N * (N - 1) / 2) * STEPS;

    state.SetItemsProcessed(total_interactions);
    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9,
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}


// use broadcast-reduce
static void BM_Baseline_Handcoded_SoA_Reduce_Broadcast_SIMD(benchmark::State& state) {
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
constexpr size_t BATCH = 512;
BENCHMARK_TEMPLATE(BM_April_DirectSum, Layout::AoS, VectorPolicy::Scalar)->Args({N, STEPS})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);
BENCHMARK_TEMPLATE(BM_April_DirectSum, Layout::SoA, VectorPolicy::Scalar)->Args({N, STEPS})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);
BENCHMARK_TEMPLATE(BM_April_DirectSum, Layout::AoSoA<>, VectorPolicy::Scalar)->Args({N, STEPS})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);

BENCHMARK_TEMPLATE(BM_April_DirectSum, Layout::SoA, VectorPolicy::Auto)->Args({N, STEPS})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);
BENCHMARK_TEMPLATE(BM_April_DirectSum, Layout::AoSoA<>, VectorPolicy::Auto)->Args({N, STEPS})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);
BENCHMARK_TEMPLATE(BM_April_DirectSum, Layout::AoSoA<16>, VectorPolicy::Auto)->Args({N, STEPS})->Unit(benchmark::kMillisecond);
BENCHMARK_TEMPLATE(BM_April_DirectSum, Layout::AoSoA<32>, VectorPolicy::Auto)->Args({N, STEPS})->Unit(benchmark::kMillisecond);

BENCHMARK(BM_Baseline_Handcoded_AoS_Scalar)->Args({N, STEPS})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);
BENCHMARK(BM_Baseline_Handcoded_SoA_Scalar)->Args({N, STEPS})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);

BENCHMARK(BM_Baseline_Handcoded_SoA_Scalar_Restrict)->Args({N, STEPS})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);
BENCHMARK(BM_Baseline_Handcoded_SoA_Scalar_LocalAcc)->Args({N, STEPS})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);
BENCHMARK(BM_Baseline_Handcoded_SoA_Scalar_RestrictLocalAcc)->Args({N, STEPS})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);

BENCHMARK(BM_Baseline_Handcoded_AoS_Scalar_Batched)->Args({N, STEPS, BATCH})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);
BENCHMARK(BM_Baseline_Handcoded_SoA_Scalar_Batched)->Args({N, STEPS, BATCH})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);
BENCHMARK(BM_Baseline_Handcoded_SoA_Scalar_BatchedLocalAcc)->Args({N, STEPS, BATCH})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);

BENCHMARK(BM_Baseline_Handcoded_SoA_Rotate_SIMD)->Args({N, STEPS})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);
BENCHMARK(BM_Baseline_Handcoded_SoA_Rotate_SIMD_Batched)->Args({N, STEPS})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);
BENCHMARK(BM_Baseline_Handcoded_SoA_Reduce_Broadcast_SIMD)->Args({N, STEPS})->Unit(benchmark::kMillisecond)->MinWarmUpTime(2.0)->MinTime(5.0);


BENCHMARK_MAIN();