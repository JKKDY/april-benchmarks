#pragma once
#include <filesystem>
#include <fstream>
#include <set>
#include <april/april.hpp>

namespace fs = std::filesystem;
using namespace april;

template<
    typename Env, 
    typename Container,
    typename ExecConfig>

Benchmark::BenchmarkResult run_simulation(
    Env&& env, 
    Container&& container, 
    ExecConfig && exec_config,
    size_t warmup_steps, 
    size_t bench_steps,
    double dt = 0.001,
    const bool enable_output = false,
    const fs::path& output_path = ""
) {
    auto system = build_system(std::forward<Env>(env), std::forward<Container>(container), exec_config);

    // Warm-up (Silent)
    VelocityVerlet warmup_integrator(system, monitors<>);
    warmup_integrator.run_for_steps(0.005, warmup_steps);

    // Benchmark Preparation
    Benchmark::BenchmarkResult res;
    // We include all potential monitors in the static pack
    VelocityVerlet bench_integrator(system, monitors<Benchmark, BinaryOutput, ProgressBar>);
    
    // Always add the benchmark collector
    bench_integrator.add_monitor(Benchmark(&res));

    // Runtime toggle for expensive IO/Visualization
    if (enable_output && !output_path.empty()) {
        if (!fs::exists(output_path)) fs::create_directories(output_path);
        fs::remove_all(output_path);
        bench_integrator.add_monitor(BinaryOutput(Trigger::every(50), output_path.string()));
        bench_integrator.add_monitor(ProgressBar(Trigger::every(bench_steps / 100)));
    }

    // Execution
    bench_integrator.run_for_steps(dt, bench_steps);

    return res;
}


inline void save_bench_to_csv(const fs::path& csv_path, const std::string& label, size_t threads, const Benchmark::BenchmarkResult& res) {
    const bool is_new = !fs::exists(csv_path);
    std::ofstream csv(csv_path, std::ios::app);

    auto sorted_timings = res.timings;
    std::ranges::sort(sorted_timings);
    double p99 = sorted_timings[static_cast<size_t>(sorted_timings.size() * 0.99)];
    double p05 = sorted_timings[static_cast<size_t>(sorted_timings.size() * 0.05)];


    if (is_new) {
        csv << "Label,Particles,Threads,Steps,Integration_s,MUPS,Avg_s,Median_s,P05_s,P99_s,StdDev_s\n";
    }

    csv << label << ","
         << res.total_updates / res.steps << ","
         << threads << ","
         << res.steps << ","
         << res.integration_time_s << ","
         << res.mups << ","
         << res.avg_step_sec << ","
         << res.median_step_sec << ","
         << p05 << ","
         << p99 << ","
         << res.std_dev_sec << "\n";
}


inline fs::path get_next_run_directory(const fs::path& base_dir) {
    if (!fs::exists(base_dir)) {
        fs::create_directories(base_dir);
        return base_dir / "1";
    }

    int max_id = 0;
    for (const auto& entry : fs::directory_iterator(base_dir)) {
        if (entry.is_directory()) {
            try {
                // Attempt to convert folder name to integer
                int current_id = std::stoi(entry.path().filename().string());
                max_id = std::max(max_id, current_id);
            } catch (...) {}
        }
    }

    return base_dir / std::to_string(max_id + 1);
}


inline std::vector<size_t> generate_scaling_sequence(const size_t max_val) {
    std::set<size_t> unique_threads;

    // We iterate by 0.5 to get the "in-between" powers of 2
    for (double expo = 0; ; expo += 0.5) {
        size_t val = static_cast<size_t>(std::round(std::pow(2.0, expo)));

        if (val > max_val) break;
        unique_threads.insert(val);
    }

    return {unique_threads.begin(), unique_threads.end()};
}