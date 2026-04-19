#pragma once
#include <filesystem>
#include <fstream>
#include <chrono>
#include <format>
#include <set>
#include <april/april.hpp>

#include <april/exec/executors/native_spin_executor.hpp>
#include <april/exec/executors/omp_executor.hpp>
#include <april/exec/executors/native_barrier_executor.hpp>

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

    VelocityVerlet warmup_integrator(system, monitors<>);
    warmup_integrator.run_for_steps(0.005, warmup_steps);

    Benchmark::BenchmarkResult res;
    VelocityVerlet bench_integrator(system, monitors<Benchmark, BinaryOutput, ProgressBar>);
    bench_integrator.add_monitor(Benchmark(&res));

    // Runtime toggle for IO
    if (enable_output && !output_path.empty()) {
        if (!fs::exists(output_path)) fs::create_directories(output_path);
        fs::remove_all(output_path);
        bench_integrator.add_monitor(BinaryOutput(Trigger::every(50), output_path.string()));
        bench_integrator.add_monitor(ProgressBar(Trigger::every(bench_steps / 100)));
    }

    // run
    bench_integrator.run_for_steps(dt, bench_steps);
    return res;
}


inline void save_bench_to_csv(
    const fs::path& csv_path,
    const std::string& label,
    size_t threads,
    const Benchmark::BenchmarkResult& res
) {
    const bool is_new = !fs::exists(csv_path);
    std::ofstream csv(csv_path, std::ios::app);

    auto sorted_timings = res.timings;
    std::ranges::sort(sorted_timings);
    const double p99 = sorted_timings[static_cast<size_t>(sorted_timings.size() * 0.99)];
    const double p05 = sorted_timings[static_cast<size_t>(sorted_timings.size() * 0.05)];

    // Get current system time and format it
    const auto now = std::chrono::system_clock::now();
    const std::string timestamp = std::format("{:%Y-%m-%d %H:%M:%S}", now);

    if (is_new) {
        csv << "Timestamp,Label,Particles,Threads,Steps,Integration_s,MUPS,Avg_s,Median_s,P05_s,P99_s,StdDev_s\n";
    }

    csv << timestamp << ","
         << label << ","
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


struct ExecutionArgs {
    double dt;
    int t;
    int steps;
    uint3 block_size;
    std::string layout;
    std::string executor;
    std::string schedule;
};

void run_benchmark(const int argc, char* argv[], int n_args, auto run_sim) {
    if (argc < n_args + 4) {
        std::cerr << "Usage: [env_args...] dt t steps [bx by bz] [sched] [layout] [exec]" << std::endl;
        return;
    }

    ExecutionArgs args;
    args.dt    = std::stod(argv[n_args + 1]);
    args.t     = std::stoi(argv[n_args + 2]);
    args.steps = std::stoi(argv[n_args + 3]);

    args.block_size = {2, 2, 2};
    if (argc > n_args + 6) {
        args.block_size.x = std::stoul(argv[n_args + 4]);
        args.block_size.y = std::stoul(argv[n_args + 5]);
        args.block_size.z = std::stoul(argv[n_args + 6]);
    }

    args.schedule = "C08";
    auto schedule = C08_schedule;
    if (argc > n_args + 7) {
        args.schedule = argv[n_args + 7];
        if (args.schedule == "C01")      schedule = C01_schedule;
        else if (args.schedule == "C08") schedule = C08_schedule;
        else if (args.schedule == "C18") schedule = C18_schedule;
        else if (args.schedule == "C27") schedule = C27_schedule;
        else if (args.schedule == "C64") schedule = C64_schedule;
        else if (args.schedule == "C02_Z")  schedule = C02_Z_schedule;
        else if (args.schedule == "C04_XY") schedule = C04_XY_schedule;
    }

    args.layout = (argc > n_args + 8) ? argv[n_args + 8] : "SoA";
    args.executor = (argc > n_args + 9) ? argv[n_args + 9] : "NativeSpinExecutor";

    auto dispatch_executor = [&]<typename L>() {
        if (args.executor == "NativeSpinExecutor")
            run_sim.template operator()<L, exec::NativeSpinExecutor>(argc, argv, args, schedule);
        else if (args.executor == "NativeBarrierExecutor")
            run_sim.template operator()<L, exec::NativeBarrierExecutor>(argc, argv, args, schedule);
        else if (args.executor == "OmpExecutor")
            run_sim.template operator()<L, exec::OmpExecutor>(argc, argv, args, schedule);
        else
            std::cerr << "Unknown Executor: " << args.executor << std::endl;
    };

    if (args.layout == "SoA")        dispatch_executor.template operator()<Layout::SoA>();
    else if (args.layout == "AoS")   dispatch_executor.template operator()<Layout::AoS>();
    else if (args.layout == "AoSoA") dispatch_executor.template operator()<Layout::AoSoA<>>();
    else                            std::cerr << "Unknown Layout: " << args.layout << std::endl;
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