#include <april/april.hpp>
#include <april/exec/executors/native_spin_executor.hpp>
#include <cmath>
#include <iostream>

#include "utils.hpp"
using namespace april;


auto create_argon_environment(const size_t n_dim, const double density = 0.8442) {
    // Standard LJ liquid parameters
    constexpr double temperature = 1.0;
    constexpr double epsilon = 1.0;
    constexpr double sigma = 1.0;
    constexpr double r_cut = 2.5 * sigma;
    constexpr int TYPE_ARGON = 0;

    // Calculate Dimensions
    const size_t total_particles = n_dim * n_dim * n_dim;
    const double volume = static_cast<double>(total_particles) / density;
    double L = std::cbrt(volume);
    const double spacing = L / static_cast<double>(n_dim);
    L = L + spacing/2;

    const vec3 origin = {-L / 2.0, -L / 2.0, -L / 2.0};
    const auto extent = vec3{L, L, L};

    // Generate particles
    const auto particle_grid = ParticleCuboid()
        .at(origin)
        .count({n_dim, n_dim, n_dim})
        .mass(1.0)
        .spacing(spacing)
        .type(TYPE_ARGON)
        .thermal([](vec3 /*pos*/) {
            return math::maxwell_boltzmann_velocity(temperature);
        });

    // Build the environment
    return Environment(forces<LennardJones>, boundaries<PeriodicBoundary>)
        .with_extent(extent)
        .with_particles(particle_grid)
        .with_force(LennardJones(epsilon, sigma, r_cut), to_type(TYPE_ARGON))
        .with_boundaries(PeriodicBoundary(), all_faces);
}



struct Experiment {
    double rho;
    size_t n;
    size_t t;
    size_t steps;
    std::string label;
};


std::vector<Experiment> plan_benchmarks(const double target_runtime_sec = 10.0, const double expected_mups_per_core = 1) {
    const std::vector densities = {
        // 0.2,
        0.8,
        // 1.1
    };
    const std::vector<size_t> sizes = {
        // 40,
        // 60,
        // 80,
        100,
        // 140,
        // 170,
        // 200
    }; // 64k - 8M
    const std::vector<size_t> threads = generate_scaling_sequence(32);
    // const std::vector<size_t> threads = {1,2,4,8,12,16,24,32};

    std::vector<Experiment> experiments;

    for (const double rho : densities) {
        for (const size_t size : sizes) {
            for (const size_t n_threads : threads) {

                const size_t n_particles = size * size * size;

                const double updates_per_sec = expected_mups_per_core * 1e6 * n_threads;
                size_t steps = static_cast<size_t>((target_runtime_sec * updates_per_sec) / n_particles);

                // We need at least some number of steps to ensure the Verlet Skin actually triggers
                // a few rebuilds. If we run 5 steps, we aren't testing the full engine.
                if (steps < 30) steps = 30;    // Floor
                if (steps > 5000) steps = 5000;  // Ceiling (prevents tiny systems from running forever)

                // Skip serial/low-thread runs for massive systems
                const double expected_run_time = steps * n_particles / updates_per_sec;
                // if (expected_run_time > 4 * target_runtime_sec) continue;

                // Create experiment label
                const std::string label = "rho" + std::to_string(rho).substr(0, 4) +
                                    "_n" + std::to_string(size) + "_t" + std::to_string(n_threads);

                experiments.push_back({rho, size, n_threads, steps, label});
            }
        }
    }
    return experiments;
}




void run_argon_bench_suiteOMP(const std::vector<Experiment>& experiments) {
    namespace fs = std::filesystem;

    // file system setup
    const fs::path root_dir = fs::path(PROJECT_SOURCE_DIR) / "bench_results/argon_sweep";
    const fs::path suite_dir = get_next_run_directory(root_dir);
    const fs::path master_csv = suite_dir / "master_results.csv";
    fs::create_directories(suite_dir);

    std::cout << "packed size: " << std::to_string(sizeof(april::packed)) << std::endl;

    std::cout << "================================================\n";
    std::cout << " SOA SUITE STARTING: " << suite_dir.string() << "\n";
    std::cout << " RUNNING " << experiments.size() << " EXPERIMENTS\n";
    std::cout << "================================================\n";


    for (size_t i = 0; i < experiments.size(); ++i) {
        const auto& [rho, n, t, steps, label] = experiments[i];

        std::cout << "[" << i + 1 << "/" << experiments.size() << "] "
                  << label << " (N=" << n << ", T=" << t << ", Steps=" << steps << ")" << std::endl;

        // setup
        ExecutionConfig cfg;
        cfg.executer_config.n_threads = t;

        auto env = create_argon_environment(n, rho);
        auto container = LinkedCells<Layout::SoA>().with_absolute_skin(0.3);

        // run
        auto result = run_simulation(
            env,
            container,
            cfg,
            steps / 10, // warmup
            steps, // bench
            0.005
        );

        // save results
        save_bench_to_csv(master_csv, label, t, result);
    }

    std::cout << "================================================\n";
    std::cout << " SUITE COMPLETE -> " << master_csv.string() << "\n";
    std::cout << "================================================\n";
}


void run_argon_bench_suiteNative(const std::vector<Experiment>& experiments) {
    namespace fs = std::filesystem;

    // file system setup
    const fs::path root_dir = fs::path(PROJECT_SOURCE_DIR) / "bench_results/argon_sweep";
    const fs::path suite_dir = get_next_run_directory(root_dir);
    const fs::path master_csv = suite_dir / "master_results.csv";
    fs::create_directories(suite_dir);

    std::cout << "packed size: " << std::to_string(sizeof(april::packed)) << std::endl;

    std::cout << "================================================\n";
    std::cout << " SOA SUITE STARTING: " << suite_dir.string() << "\n";
    std::cout << " RUNNING " << experiments.size() << " EXPERIMENTS\n";
    std::cout << "================================================\n";


    for (size_t i = 0; i < experiments.size(); ++i) {
        const auto& [rho, n, t, steps, label] = experiments[i];

        std::cout << "[" << i + 1 << "/" << experiments.size() << "] "
                  << label << " (N=" << n << ", T=" << t << ", Steps=" << steps << ")" << std::endl;

        // setup
        struct :
			RunTimeConfig<exec::NativeSpinExecutor>,
			CompileTimeConfig<ParallelPolicy::Threaded, VectorPolicy::Auto>
		{} cfg;
        cfg.executer_config.n_threads = t;

        auto env = create_argon_environment(n, rho);
        auto container = LinkedCells<Layout::SoA>().with_absolute_skin(0.3);

        // run
        auto result = run_simulation(
            env,
            container,
            cfg,
            steps / 10, // warmup
            steps, // bench
            0.005
        );

        // save results
        save_bench_to_csv(master_csv, label, t, result);
    }

    std::cout << "================================================\n";
    std::cout << " SUITE COMPLETE -> " << master_csv.string() << "\n";
    std::cout << "================================================\n";
}



int main() {
    const auto plan = plan_benchmarks();
    run_argon_bench_suiteOMP(plan);
    run_argon_bench_suiteNative(plan);

   //  ExecutionConfig cfg;
   //  cfg.executer_config.n_threads = 6;
   //
   //  auto env = create_argon_environment(40, 1.1);
   //  auto container = LinkedCells<Layout::AoSoA<>>().with_absolute_skin(0.3);
   //  // auto container = DirectSum();
   //
   //   run_simulation(
   //     std::move(env),
   //     std::move(container),
   //     cfg,
   //     25, // warmup
   //     5000, // bench
   //     0.005, // d
   //     false, // No binary output during benchmark
   //     "/mnt/d/Dev/april/animation/output"
   // );
}