#include <benchmark/benchmark.h>
#include <april/april.hpp>
#include <vector>

#include "april/exec/executors/sequential_executor.hpp"

using namespace april;
constexpr double SIGMA = 1.0;
constexpr double EPSILON = 3.0;
constexpr double DT = 0.00001;



struct LJ {
    LJ(const double epsilon_, const double sigma_) : epsilon(epsilon_), sigma(sigma_) {
        const vec3::type sigma2 = sigma * sigma;
        const vec3::type sigma6 = sigma2 * sigma2 * sigma2;
        const vec3::type sigma12 = sigma6 * sigma6;
        c6_force = 24.0 * epsilon * sigma6;
        c12_force = 48.0 * epsilon * sigma12;
    }

    [[nodiscard]] vec3 eval(const vec3& r) const noexcept {
        const vec3::type inv_r2 = static_cast<vec3::type>(1.0) / (r.x*r.x + r.y*r.y + r.z * r.z);
        const vec3::type inv_r6 = inv_r2 * inv_r2 * inv_r2;
        const vec3::type magnitude = (c12_force * inv_r6 - c6_force) * inv_r6 * inv_r2;
        return -magnitude * r;
    }
private:
    vec3::type c12_force, c6_force;
    double epsilon, sigma;
};

struct LJ_AoS {
    LJ_AoS(const double epsilon_, const double sigma_) : epsilon(epsilon_), sigma(sigma_) {
        const vec3::type sigma2 = sigma * sigma;
        const vec3::type sigma6 = sigma2 * sigma2 * sigma2;
        const vec3::type sigma12 = sigma6 * sigma6;
        c6_force = 24.0 * epsilon * sigma6;
        c12_force = 48.0 * epsilon * sigma12;
    }

    [[nodiscard]] auto eval(double x, double y, double z) const noexcept {
        const vec3::type inv_r2 = static_cast<vec3::type>(1.0) / (x*x + y*y + z * z);
        const vec3::type inv_r6 = inv_r2 * inv_r2 * inv_r2;
        const vec3::type magnitude = (c12_force * inv_r6 - c6_force) * inv_r6 * inv_r2;
        return std::array{-magnitude * x,  -magnitude * y,  -magnitude * z};
    }
private:
    vec3::type c12_force, c6_force;
    double epsilon, sigma;
};



// Helper to calculate exact number of pairwise interactions (N * (N-1) / 2)
constexpr size_t calc_interactions(size_t n, size_t steps) {
    return (n * (n - 1) / 2) * steps;
}






//----------------------------
// April DIRECT SUM Benchmarks
//----------------------------
static auto create_bench_env(size_t N) {
    auto force = LennardJones(EPSILON, SIGMA, interactions::no_cutoff);
    Environment env(forces<LennardJones>, boundaries<ReflectiveBoundary>);
    env.add_force(force, to_type(0));
    env.set_boundaries(ReflectiveBoundary(), all_faces);

    for (size_t i = 0; i < N; i++) {
        env.add_particle(Particle().at(static_cast<double>(i), 0, 0).with_mass(1.0));
    }
    return env;
}

// Full Integration Benchmark
template <typename LayoutType, VectorPolicy VPol>
static void BM_DirectSum_FullIntegration(benchmark::State& state) {
    const size_t N = state.range(0);
    const size_t steps = state.range(1);

    auto env = create_bench_env(N);

    const struct:
        RunTimeConfig<exec::SequentialExecutor>,
        CompileTimeConfig<ParallelPolicy::Serial, VPol>
    {} cfg;

    auto container = DirectSum<LayoutType>();
    auto system = build_system(env, container, cfg);
    VelocityVerlet integrator(system);

    for (auto _ : state) {
        integrator.run_for_steps(DT, steps);
    }

    const double total_interactions = static_cast<double>(state.iterations() * calc_interactions(N, steps));
    state.SetItemsProcessed(total_interactions);

    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9, // Divide by 1e9 to shift the unit from Seconds to Nanoseconds
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}

// Force Update Benchmark
template <typename LayoutType, VectorPolicy VPol>
static void BM_DirectSum_UpdateForcesOnly(benchmark::State& state) {
    const size_t N = state.range(0);
    const size_t steps = state.range(1);

    auto env = create_bench_env(N);

    const struct:
        RunTimeConfig<exec::SequentialExecutor>,
        CompileTimeConfig<ParallelPolicy::Serial, VPol>
    {} cfg;

    auto container = DirectSum<LayoutType>();
    auto system = build_system(env, container, cfg);

    for (auto _ : state) {
        for (size_t i = 0; i < steps; i++) {
            system.update_forces();
        }
    }

    const double total_interactions = static_cast<double>(state.iterations() * calc_interactions(N, steps));
    state.SetItemsProcessed(total_interactions);

    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9, // Divide by 1e9 to shift the unit from Seconds to Nanoseconds
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}

//------------------------------
// April LINKED CELLS Benchmarks
//------------------------------

struct LJNoCutoff : LennardJones {
    using LennardJones::LennardJones;

    // cutoff2 (which should return the cutoff^2 is used for the distance check in the force update function
    // we hijack it to return a large value such that the distance check never succeeds
    // thus causing the system to evaluate the force between every particle pair regardless of actual distance
    [[nodiscard]] double cutoff2() const {
       return 1e100;
    }

    // dummy mixing method
    [[nodiscard]] LJNoCutoff mix(LJNoCutoff const&) const noexcept {
       return {0,0,0};
    }
};

static auto create_lc_bench_env(const size_t N_DIM) {
    constexpr double a = 1.1225;
    constexpr double sigma = 1.0;
    constexpr double epsilon = 3.0;
    constexpr double r_cut = 3.0 * sigma;

    // Grid physical span
    const double Lx = (N_DIM - 1) * a;
    const double Ly = (N_DIM - 1) * a;
    const double Lz = (N_DIM - 1) * a;
    const vec3 box = {Lx, Ly, Lz};

    ParticleCuboid grid = ParticleCuboid{}
       .at(-0.5 * box)
       .velocity({0,0,0})
       .count({N_DIM, N_DIM, N_DIM})
       .mass(1.0)
       .spacing(a)
       .type(0);

    // Box with margin >= r_cut around grid
    const vec3 extent = 1.5 * box;
    const vec3 origin = -0.5 * extent;

    Environment env(forces<LJNoCutoff>, boundaries<ReflectiveBoundary>);
    env.add_particles(grid);
    env.set_origin(origin);
    env.set_extent(extent);
    env.add_force(LJNoCutoff(epsilon, sigma, r_cut), to_type(0));
    env.set_boundaries(ReflectiveBoundary(), all_faces);

    return env;
}


template <typename LayoutType, VectorPolicy VPol>
static void BM_LinkedCells_UpdateForcesOnly(benchmark::State& state) {
    const size_t n_dim = state.range(0);
    const size_t steps = state.range(1);

    auto env = create_lc_bench_env(n_dim);

    const struct:
        RunTimeConfig<exec::SequentialExecutor>,
        CompileTimeConfig<ParallelPolicy::Serial, VPol>
    {} cfg;

    auto container = LinkedCells<LayoutType>()
        .with_abs_cell_size(3.0)
        .with_cell_ordering(hilbert_order);

    auto system = build_system(env, container, cfg);

    // Calculate exact interactions per step *outside* the timed loop
    size_t interactions_per_step = 0;
    system.for_each_interaction_pair(scalar_kernel(
        [&](auto, auto) { interactions_per_step++; }
    ));

    for (auto _ : state) {
        for (size_t i = 0; i < steps; i++) {
            system.update_forces();
        }
    }

    const double total_interactions = static_cast<double>(state.iterations() * interactions_per_step * steps);
    state.SetItemsProcessed(total_interactions);

    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9, // Divide by 1e9 to shift the unit from Seconds to Nanoseconds
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}


template <typename LayoutType, VectorPolicy VPol>
static void BM_LinkedCells_FullIntegration(benchmark::State& state) {
    const size_t n_dim = state.range(0);
    const size_t steps = state.range(1);

    auto env = create_lc_bench_env(n_dim);

    const struct:
        RunTimeConfig<exec::SequentialExecutor>,
        CompileTimeConfig<ParallelPolicy::Serial, VPol>
    {} cfg;

    auto container = LinkedCells<LayoutType>()
        .with_abs_cell_size(3.0)
        .with_cell_ordering(hilbert_order);

    auto system = build_system(env, container, cfg);
    VelocityVerlet integrator(system);

    size_t interactions_per_step = 0;
    system.for_each_interaction_pair(scalar_kernel(
        [&](auto, auto) { interactions_per_step++; }
    ));

    for (auto _ : state) {
        integrator.run_for_steps(0.000001, steps);
    }

    const double total_interactions = static_cast<double>(state.iterations() * interactions_per_step * steps);
    state.SetItemsProcessed(total_interactions);

    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9, // Divide by 1e9 to shift the unit from Seconds to Nanoseconds
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}









// ----------------------
// Manual Loop Benchmarks
// ----------------------

static void BM_Manual_AbsoluteMaxPerf(benchmark::State& state) {
    const size_t interactions_per_step = state.range(0);
    auto lj = LJ(EPSILON, SIGMA);

    for (auto _ : state) {
        vec3 acc{};
        for (size_t i = 1; i <= interactions_per_step; i++) {
            vec3 f = lj.eval(vec3{static_cast<double>(i)});
            acc += f;
        }
        benchmark::DoNotOptimize(acc); // Prevents compiler from dropping the loop
    }

    const double total_interactions = static_cast<double>(state.iterations() * interactions_per_step);
    state.SetItemsProcessed(total_interactions);

    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9, // Divide by 1e9 to shift the unit from Seconds to Nanoseconds
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}

static void BM_Manual_RealisticVectorRead(benchmark::State& state) {
    const size_t N = state.range(0);
    auto lj = LJ(EPSILON, SIGMA);

    std::vector<vec3> pos(N);
    for (size_t i = 0; i < N; i++) {
        pos[i] = vec3{0.0001 * static_cast<double>(i + 1)};
    }

    for (auto _ : state) {
        vec3 acc{};
        for (size_t i = 0; i < N; i++) {
            vec3 f = lj.eval(pos[i]);
            acc += f;
        }
        benchmark::DoNotOptimize(acc);
    }
    const double total_interactions = static_cast<double>(state.iterations() * N);
    state.SetItemsProcessed(total_interactions);

    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9, // Divide by 1e9 to shift the unit from Seconds to Nanoseconds
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}

static void BM_Manual_TriangleAoS(benchmark::State& state) {
    const size_t N = state.range(0);
    const size_t steps = state.range(1);
    auto lj = LJ(EPSILON, SIGMA);

    std::vector<vec3> pos1(N);
    std::vector<vec3> f1(N, vec3{0});

    for (size_t i = 0; i < N; i++) {
        pos1[i] = vec3{0.0001 * static_cast<double>(i + 1)};
    }

    for (auto _ : state) {
        for (size_t k = 0; k < steps; k++) {
            for (size_t i = 0; i < N; i++) {
                vec3 a{};
                for (size_t j = i + 1; j < N; j++) {
                    vec3 f = lj.eval(pos1[i] - pos1[j]);
                    a += f;
                    f1[j] -= f;
                }
                f1[i] += a;
            }
        }
        benchmark::DoNotOptimize(f1);
    }
    const double total_interactions = static_cast<double>(state.iterations() * calc_interactions(N, steps));
    state.SetItemsProcessed(total_interactions);

    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9, // Divide by 1e9 to shift the unit from Seconds to Nanoseconds
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}

static void BM_Manual_TriangleSoA(benchmark::State& state) {
    const size_t N = state.range(0);
    const size_t steps = state.range(1);
    auto lj = LJ_AoS(EPSILON, SIGMA);

    std::vector<double> posx(N), posy(N), posz(N);
    std::vector<double> fx(N, 0), fy(N, 0), fz(N, 0);

    for (size_t i = 0; i < N; i++) {
        posx[i] = posy[i] = posz[i] = 0.0001 * static_cast<double>(i + 1);
    }

    for (auto _ : state) {
        for (size_t k = 0; k < steps; k++) {
            for (size_t i = 0; i < N; i++) {
                double ax = 0, ay = 0, az = 0;

                for (size_t j = i + 1; j < N; j++) {
                    auto [x, y, z] = lj.eval(
                        posx[j] - posx[i],
                        posy[j] - posy[i],
                        posz[j] - posz[i]
                    );
                    ax += x; ay += y; az += z;
                    fx[j] -= x; fy[j] -= y; fz[j] -= z;
                }

                fx[i] += ax; fy[i] += ay; fz[i] += az;
            }
        }

        benchmark::DoNotOptimize(fx);
        benchmark::DoNotOptimize(fy);
        benchmark::DoNotOptimize(fz);
    }
    const double total_interactions = static_cast<double>(state.iterations() * calc_interactions(N, steps));
    state.SetItemsProcessed(total_interactions);

    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9, // Divide by 1e9 to shift the unit from Seconds to Nanoseconds
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}

// Keep the scalar disable macro so the tail loop doesn't get auto-vectorized
static void BM_Manual_TriangleSoA_ExplicitSIMD(benchmark::State& state) {
    using batch_d = simd::Packed<double>;
    const size_t N = state.range(0);
    const size_t steps = state.range(1);

    // Precompute scalars
    constexpr double sigma2 = SIGMA * SIGMA;
    constexpr double sigma6 = sigma2 * sigma2 * sigma2;
    constexpr double sigma12 = sigma6 * sigma6;
    constexpr double c6_scalar = 24.0 * EPSILON * sigma6;
    constexpr double c12_scalar = 48.0 * EPSILON * sigma12;

    // Broadcast constants
    const batch_d v_c6 = c6_scalar;
    const batch_d v_c12 = c12_scalar;
    const batch_d v_one = 1.0;
    constexpr size_t V = batch_d::size();

    std::vector<double> posx(N), posy(N), posz(N);
    std::vector<double> fx(N, 0), fy(N, 0), fz(N, 0);

    for (size_t i = 0; i < N; i++) {
        posx[i] = posy[i] = posz[i] = 0.0001 * static_cast<double>(i + 1);
    }

    for (auto _ : state) {
        for (size_t k = 0; k < steps; k++) {
            for (size_t i = 0; i < N; i++) {

                // Outer particle scalar position broadcasted to SIMD
                const batch_d v_xi = posx[i];
                const batch_d v_yi = posy[i];
                const batch_d v_zi = posz[i];

                // SIMD Force accumulators for particle i
                batch_d v_ax = 0.0;
                batch_d v_ay = 0.0;
                batch_d v_az = 0.0;

                size_t j = i + 1;

                // --------------------------------------------------
                // MAIN SIMD LOOP (Processes V particles at a time)
                // --------------------------------------------------
                for (; j + V <= N; j += V) {
                    // Load j positions
                    batch_d v_xj = batch_d::load_unaligned(&posx[j]);
                    batch_d v_yj = batch_d::load_unaligned(&posy[j]);
                    batch_d v_zj = batch_d::load_unaligned(&posz[j]);

                    // dx = posx[j] - posx[i]
                    batch_d dx = v_xj - v_xi;
                    batch_d dy = v_yj - v_yi;
                    batch_d dz = v_zj - v_zi;

                    batch_d r2 = (dx * dx) + (dy * dy) + (dz * dz);
                    batch_d inv_r2 = v_one / r2;
                    batch_d inv_r6 = inv_r2 * inv_r2 * inv_r2;

                    // magnitude = (c12 * inv_r6 - c6) * inv_r6 * inv_r2
                    batch_d mag = (v_c12 * inv_r6 - v_c6) * inv_r6 * inv_r2;

                    // eval() returned std::array{-magnitude * x, ...}
                    batch_d x_eval = -mag * dx;
                    batch_d y_eval = -mag * dy;
                    batch_d z_eval = -mag * dz;

                    // ax += x
                    v_ax += x_eval;
                    v_ay += y_eval;
                    v_az += z_eval;

                    // Load j forces, fx[j] -= x, store j forces
                    batch_d f_xj = batch_d::load_unaligned(&fx[j]);
                    batch_d f_yj = batch_d::load_unaligned(&fy[j]);
                    batch_d f_zj = batch_d::load_unaligned(&fz[j]);

                    f_xj -= x_eval;
                    f_yj -= y_eval;
                    f_zj -= z_eval;

                    f_xj.store_unaligned(&fx[j]);
                    f_yj.store_unaligned(&fy[j]);
                    f_zj.store_unaligned(&fz[j]);
                }

                // --------------------------------------------------
                // HORIZONTAL REDUCTION
                // --------------------------------------------------
                // Sum the lanes of the SIMD accumulators into scalar values
                double ax = v_ax.reduce_add();
                double ay = v_ay.reduce_add();
                double az = v_az.reduce_add();

                // --------------------------------------------------
                // SCALAR TAIL LOOP (Handles the remaining j < V)
                // --------------------------------------------------
                for (; j < N; j++) {
                    double dx = posx[i] - posx[j];
                    double dy = posy[i] - posy[j];
                    double dz = posz[i] - posz[j];

                    double r2 = (dx * dx) + (dy * dy) + (dz * dz);
                    double inv_r2 = 1.0 / r2;
                    double inv_r6 = inv_r2 * inv_r2 * inv_r2;
                    double mag = (c12_scalar * inv_r6 - c6_scalar) * inv_r6 * inv_r2;

                    double x_eval = -mag * dx;
                    double y_eval = -mag * dy;
                    double z_eval = -mag * dz;

                    ax += x_eval;
                    ay += y_eval;
                    az += z_eval;

                    fx[j] -= x_eval;
                    fy[j] -= y_eval;
                    fz[j] -= z_eval;
                }

                // Apply accumulated forces to i
                fx[i] -= ax;
                fy[i] -= ay;
                fz[i] -= az;
            }
        }
        benchmark::DoNotOptimize(fx);
        benchmark::DoNotOptimize(fy);
        benchmark::DoNotOptimize(fz);
    }
    const double total_interactions = static_cast<double>(state.iterations() * calc_interactions(N, steps));
    state.SetItemsProcessed(total_interactions);

    state.counters["ns/interaction"] = benchmark::Counter(
        total_interactions / 1e9, // Divide by 1e9 to shift the unit from Seconds to Nanoseconds
        benchmark::Counter::kIsRate | benchmark::Counter::kInvert
    );
}





// ------------
// REGISTRATION
// ------------

// LINKED CELLS
// N_DIM = 50 (125k particles), Steps = 25

// Array of Structures
BENCHMARK_TEMPLATE(BM_LinkedCells_UpdateForcesOnly, Layout::AoS, VectorPolicy::Scalar)->Args({50, 25})->Unit(benchmark::kMillisecond);
BENCHMARK_TEMPLATE(BM_LinkedCells_FullIntegration, Layout::AoS, VectorPolicy::Scalar)->Args({50, 25})->Unit(benchmark::kMillisecond);

// Structure of Arrays
BENCHMARK_TEMPLATE(BM_LinkedCells_UpdateForcesOnly, Layout::SoA, VectorPolicy::Scalar)->Args({50, 25})->Unit(benchmark::kMillisecond);
BENCHMARK_TEMPLATE(BM_LinkedCells_UpdateForcesOnly, Layout::SoA, VectorPolicy::Auto)->Args({50, 25})->Unit(benchmark::kMillisecond);

// Array of Structures of Arrays
BENCHMARK_TEMPLATE(BM_LinkedCells_UpdateForcesOnly, Layout::AoSoA<>, VectorPolicy::Auto)->Args({50, 25})->Unit(benchmark::kMillisecond);
BENCHMARK_TEMPLATE(BM_LinkedCells_FullIntegration, Layout::AoSoA<>, VectorPolicy::Auto)->Args({50, 25})->Unit(benchmark::kMillisecond);


// DIRECT SUM
// N = 4000, Steps = 200

// Array of Structures (Auto)
BENCHMARK_TEMPLATE(BM_DirectSum_FullIntegration, Layout::AoS, VectorPolicy::Scalar)->Args({4000, 200})->Unit(benchmark::kMillisecond);
BENCHMARK_TEMPLATE(BM_DirectSum_UpdateForcesOnly, Layout::AoS, VectorPolicy::Scalar)->Args({4000, 200})->Unit(benchmark::kMillisecond);

// Structure of Arrays (Scalar)
BENCHMARK_TEMPLATE(BM_DirectSum_FullIntegration, Layout::SoA, VectorPolicy::Scalar)->Args({4000, 200})->Unit(benchmark::kMillisecond);
BENCHMARK_TEMPLATE(BM_DirectSum_UpdateForcesOnly, Layout::SoA, VectorPolicy::Scalar)->Args({4000, 200})->Unit(benchmark::kMillisecond);

// Structure of Arrays (Auto)
BENCHMARK_TEMPLATE(BM_DirectSum_FullIntegration, Layout::SoA, VectorPolicy::Auto)->Args({4000, 200})->Unit(benchmark::kMillisecond);
BENCHMARK_TEMPLATE(BM_DirectSum_UpdateForcesOnly, Layout::SoA, VectorPolicy::Auto)->Args({4000, 200})->Unit(benchmark::kMillisecond);

// Array of Structures of Arrays (Auto)
BENCHMARK_TEMPLATE(BM_DirectSum_FullIntegration, Layout::AoSoA<>, VectorPolicy::Auto)->Args({4000, 200})->Unit(benchmark::kMillisecond);
BENCHMARK_TEMPLATE(BM_DirectSum_UpdateForcesOnly, Layout::AoSoA<>, VectorPolicy::Auto)->Args({4000, 200})->Unit(benchmark::kMillisecond);


// HARDCODED INTERACTION LOOPS
// For the MaxPerf benchmark, range is total interactions per step
BENCHMARK(BM_Manual_AbsoluteMaxPerf)->Arg(4000 * 3999 / 2)->Unit(benchmark::kMillisecond);
BENCHMARK(BM_Manual_RealisticVectorRead)->Arg(4000 * 3999 / 2)->Unit(benchmark::kMillisecond);

BENCHMARK(BM_Manual_TriangleAoS)->Args({4000, 200})->Unit(benchmark::kMillisecond);
BENCHMARK(BM_Manual_TriangleSoA)->Args({4000, 200})->Unit(benchmark::kMillisecond);

BENCHMARK(BM_Manual_TriangleSoA_ExplicitSIMD)->Args({4000, 200})->Unit(benchmark::kMillisecond);
BENCHMARK_MAIN();