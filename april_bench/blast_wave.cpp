#include <april/april.hpp>
#include <april/exec/executors/native_spin_executor.hpp>
#include <cmath>
#include <iostream>

#include "utils.hpp"
using namespace april;

auto create_blast_wave_environment(const size_t n_core_dim, const double rho, const double expansion_ratio = 125.0) {
    constexpr double epsilon = 1.0;
    constexpr double sigma = 1.0;
    constexpr double r_cut = 2.5 * sigma;
    constexpr int TYPE_BLAST = 0;

    const double core_density = rho; // Over-packed to induce extreme repulsive forces
    constexpr double temperature = 1.0;

    const size_t total_particles = n_core_dim * n_core_dim * n_core_dim;
    const double core_volume = static_cast<double>(total_particles) / core_density;
    const double L_core = std::cbrt(core_volume);
    const double spacing = L_core / static_cast<double>(n_core_dim);

    const double total_volume = core_volume * expansion_ratio;
    const double L_domain = std::cbrt(total_volume);
    const auto extent = vec3{L_domain, L_domain, L_domain};

    const double offset = (L_domain - L_core) / 2.0;
    const vec3 origin = {offset + spacing / 2.0, offset + spacing / 2.0, offset + spacing / 2.0};

    const auto blast_core = ParticleCuboid()
        .at(origin)
        .count({n_core_dim, n_core_dim, n_core_dim})
        .mass(1.0)
        .spacing(spacing)
        .type(TYPE_BLAST)
        .thermal([](vec3 /*pos*/) {
            return math::maxwell_boltzmann_velocity(temperature);
        });

    return Environment(forces<LennardJones>, boundaries<ReflectiveBoundary>)
        .with_extent(extent)
        .with_particles(blast_core)
        .with_force(LennardJones(epsilon, sigma, r_cut), to_type(TYPE_BLAST))
        .with_boundaries(ReflectiveBoundary(), all_faces);
}


auto argon_block = []<typename Layout, typename ExecutorType>(
    int argc, char* argv[], const ExecutionArgs& args, auto schedule)
{
    const int n = std::stoi(argv[1]);
    const double rho = std::stoi(argv[2]);
    const double expansion = std::stod(argv[3]);

    auto env = create_blast_wave_environment(n, rho, expansion);

    auto container = LinkedCells<Layout>()
        .with_absolute_skin(0.3)
        .with_block_size(args.block_size)
        .with_scheduling(schedule)
        .with_cell_ordering(hilbert_order);

    struct:
        RunTimeConfig<ExecutorType>,
        CompileTimeConfig<ParallelPolicy::Threaded, VectorPolicy::Auto>
    {} cfg;
    cfg.executer_config.n_threads = args.t;

    auto bench = run_simulation(env, container, cfg, args.steps / 10, args.steps, args.dt);

    std::string label = std::format("BlastWave_n{}_rho{}_expansion{}_{}_{}_{}_{}x{}x{}",
        n, rho, expansion, args.layout, args.executor, args.schedule,
        args.block_size.x, args.block_size.y, args.block_size.z);

    const fs::path root_dir = fs::path(PROJECT_SOURCE_DIR) / "april_bench/results/blast_wave";
    if (!fs::exists(root_dir)) fs::create_directories(root_dir);

    save_bench_to_csv(root_dir / "blast_wave.csv", label, args.t, bench);
};



int main(const int argc, char* argv[]) {
    run_benchmark(argc, argv, 3, argon_block);
    return 0;
}

