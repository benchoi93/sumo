#!/usr/bin/env python3
"""Performance benchmarking for SUMO refactoring test scenarios.

Runs each scenario multiple times, takes median wall time, and optionally
collects perf stat data (cache misses) if available.

Usage:
    python benchmark.py [--sumo-binary path] [--output results.csv] [--scenarios-dir path]
"""

import argparse
import csv
import os
import shutil
import statistics
import subprocess
import sys
import time


def find_scenarios(scenarios_dir):
    """Find all .sumocfg files under the given directory.

    Parameters
    ----------
    scenarios_dir : str
        Directory to search for .sumocfg files.

    Returns
    -------
    list of tuple
        Each tuple is (scenario_name, sumocfg_path, scenario_dir).
    """
    scenarios = []

    if not os.path.isdir(scenarios_dir):
        print(f"WARNING: Scenarios directory not found: {scenarios_dir}")
        return scenarios

    for root, dirs, files in os.walk(scenarios_dir):
        for f in files:
            if f.endswith(".sumocfg"):
                cfg_path = os.path.join(root, f)
                rel = os.path.relpath(root, scenarios_dir)
                scenario_name = f"{rel}/{os.path.splitext(f)[0]}"
                scenarios.append((scenario_name, cfg_path, root))

    return sorted(scenarios, key=lambda x: x[0])


def has_perf():
    """Check if the `perf` command is available."""
    return shutil.which("perf") is not None


def run_benchmark(sumo_binary, sumocfg_path, scenario_dir, num_runs=3, use_perf=False):
    """Benchmark a single scenario.

    Parameters
    ----------
    sumo_binary : str
        Path to the SUMO binary.
    sumocfg_path : str
        Path to the .sumocfg file.
    scenario_dir : str
        Directory containing the scenario files.
    num_runs : int
        Number of times to run the scenario.
    use_perf : bool
        Whether to use perf stat for cache miss data.

    Returns
    -------
    dict or None
        Dictionary with benchmark results, or None if the scenario failed.
    """
    # Discard outputs to /dev/null equivalent
    devnull = "/dev/null"

    base_cmd = [
        sumo_binary,
        "-c", sumocfg_path,
        "--seed", "42",
        "--default.speeddev", "0",
        "--fcd-output", devnull,
        "--tripinfo-output", devnull,
        "--no-warnings", "true",
    ]

    times = []
    perf_data = {}

    for i in range(num_runs):
        if use_perf:
            cmd = [
                "perf", "stat", "-e", "cache-misses,cache-references,instructions,cycles",
                "--"
            ] + base_cmd
        else:
            cmd = base_cmd

        try:
            start = time.perf_counter()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                cwd=scenario_dir,
            )
            elapsed = time.perf_counter() - start

            if result.returncode != 0:
                # SUMO returns 0 on success; treat any non-zero as a failure
                # regardless of whether perf wrapping is in use.
                print(f"    SUMO failed (exit {result.returncode}): {result.stderr[:200]}")
                return None

            times.append(elapsed)

            # Parse perf stat output from stderr (last run)
            if use_perf and i == num_runs - 1 and result.stderr:
                for line in result.stderr.split("\n"):
                    line = line.strip()
                    if "cache-misses" in line:
                        parts = line.split()
                        if parts:
                            perf_data["cache_misses"] = parts[0].replace(",", "")
                    elif "cache-references" in line:
                        parts = line.split()
                        if parts:
                            perf_data["cache_references"] = parts[0].replace(",", "")
                    elif "instructions" in line and "insn" not in line:
                        parts = line.split()
                        if parts:
                            perf_data["instructions"] = parts[0].replace(",", "")

        except subprocess.TimeoutExpired:
            return None
        except FileNotFoundError:
            return None
        except Exception:
            return None

    if not times:
        return None

    return {
        "median_time_s": statistics.median(times),
        "min_time_s": min(times),
        "max_time_s": max(times),
        "num_runs": len(times),
        **perf_data,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Performance benchmarking for SUMO test scenarios."
    )
    parser.add_argument(
        "--sumo-binary", default="sumo",
        help="Path to the SUMO binary (default: 'sumo' from PATH)."
    )
    parser.add_argument(
        "--output", default="benchmark_results.csv",
        help="Output CSV file path (default: benchmark_results.csv)."
    )
    parser.add_argument(
        "--scenarios-dir", default=None,
        help="Directory containing scenarios. Defaults to the directory containing this script."
    )
    parser.add_argument(
        "--num-runs", type=int, default=3,
        help="Number of runs per scenario (default: 3)."
    )
    parser.add_argument(
        "--perf", action="store_true",
        help="Use perf stat for cache miss data (requires Linux perf)."
    )
    args = parser.parse_args()

    if args.scenarios_dir is None:
        args.scenarios_dir = os.path.dirname(os.path.abspath(__file__))

    use_perf = args.perf and has_perf()
    if args.perf and not use_perf:
        print("WARNING: --perf requested but 'perf' command not found. Skipping perf stat.")

    print("=" * 60)
    print("Performance Benchmark")
    print("=" * 60)
    print(f"  SUMO binary:   {args.sumo_binary}")
    print(f"  Scenarios dir: {args.scenarios_dir}")
    print(f"  Runs per test: {args.num_runs}")
    print(f"  Using perf:    {use_perf}")
    print(f"  Output:        {args.output}")
    print()

    scenarios = find_scenarios(args.scenarios_dir)

    if not scenarios:
        print("No scenarios found!")
        sys.exit(1)

    print(f"Found {len(scenarios)} scenario(s):\n")

    results = []
    fieldnames = ["scenario", "median_time_s", "min_time_s", "max_time_s"]
    if use_perf:
        fieldnames.extend(["cache_misses", "cache_references", "instructions"])

    for scenario_name, sumocfg_path, scenario_dir in scenarios:
        print(f"  Benchmarking: {scenario_name} ...", end="", flush=True)

        bench = run_benchmark(
            args.sumo_binary, sumocfg_path, scenario_dir,
            num_runs=args.num_runs, use_perf=use_perf
        )

        if bench is None:
            print(" FAIL")
            results.append({
                "scenario": scenario_name,
                "median_time_s": "FAIL",
                "min_time_s": "FAIL",
                "max_time_s": "FAIL",
            })
        else:
            print(f" {bench['median_time_s']:.4f}s (median)")
            row = {
                "scenario": scenario_name,
                "median_time_s": f"{bench['median_time_s']:.6f}",
                "min_time_s": f"{bench['min_time_s']:.6f}",
                "max_time_s": f"{bench['max_time_s']:.6f}",
            }
            if use_perf:
                row["cache_misses"] = bench.get("cache_misses", "N/A")
                row["cache_references"] = bench.get("cache_references", "N/A")
                row["instructions"] = bench.get("instructions", "N/A")
            results.append(row)

    # Write CSV
    output_path = args.output
    if not os.path.isabs(output_path):
        output_path = os.path.join(args.scenarios_dir, output_path)

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults written to: {output_path}")


if __name__ == "__main__":
    main()
