#include <april/april.hpp>
#include <cmath>
#include <iostream>
#include <string>
#include "utils.hpp"

namespace april::exec {
    class NativeBarrierExecutor;
}

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
    const double L = std::cbrt(volume);
    const double spacing = L / static_cast<double>(n_dim);

    const vec3 origin = vec3{-L / 2.0} + vec3{spacing / 2.0};
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



auto argon_block = []<typename Layout, typename ExecutorType>(
    int argc, char* argv[], const ExecutionArgs& args, auto schedule)
{
    const int n = std::stoi(argv[1]);
    const double rho = std::stod(argv[2]);

    auto env = create_argon_environment(n, rho);

    auto container = LinkedCells<Layout>()
        .with_absolute_skin(0.3)
        .with_block_size(args.block_size)
        .with_scheduling(schedule);

    if (args.ordering == "hilbert") {
        container.with_cell_ordering(hilbert_order);
    } else if (args.ordering == "morton") {
        container.with_cell_ordering(morton_order);
    } else if (args.ordering == "none") {
        // leave container as-is
    } else {
        throw std::runtime_error("Unknown ordering: " + args.ordering);
    }

    struct :
        RunTimeConfig<ExecutorType>,
        CompileTimeConfig<ParallelPolicy::Threaded, VectorPolicy::Auto>
    {} cfg;
    cfg.executer_config.n_threads = args.t;

    auto bench = run_simulation(env, container, cfg, args.steps / 10, args.steps, args.dt);

    std::string label = std::format("Argon_n{}_rho{}_{}_{}_{}_{}_{}x{}x{}",
        n, rho, args.layout, args.executor, args.schedule, args.ordering,
        args.block_size.x, args.block_size.y, args.block_size.z);

    std::string safe_tag = args.tag;
    std::ranges::replace(safe_tag, ' ', '_');
    std::ranges::replace(safe_tag, '/', '_');

    const fs::path root_dir = fs::path(PROJECT_SOURCE_DIR) / "results/april";
    if (!fs::exists(root_dir)) fs::create_directories(root_dir);

    const fs::path csv_path = root_dir / std::format("argon_block_{}.csv", safe_tag);
    save_bench_to_csv(csv_path, label, args.t, bench);
};



int main(const int argc, char* argv[]) {
    run_benchmark(argc, argv, 2, argon_block);
    return 0;
}


