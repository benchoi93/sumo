#!/usr/bin/env python3
"""Compare two performance benchmark CSV files.

Takes a baseline CSV and a current CSV, reports per-scenario speedup/regression,
and warns if any scenario regressed more than 5%.

Usage:
    python compare_perf.py baseline.csv current.csv
"""

import argparse
import csv
import os
import sys


def load_benchmark_csv(csv_path):
    """Load a benchmark CSV file into a dict keyed by scenario name.

    Parameters
    ----------
    csv_path : str
        Path to the CSV file.

    Returns
    -------
    dict
        Mapping from scenario name to dict of values.
    """
    data = {}
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scenario = row["scenario"]
            data[scenario] = row
    return data


def main():
    parser = argparse.ArgumentParser(
        description="Compare two performance benchmark CSV files."
    )
    parser.add_argument(
        "baseline",
        help="Path to the baseline benchmark CSV file."
    )
    parser.add_argument(
        "current",
        help="Path to the current benchmark CSV file."
    )
    parser.add_argument(
        "--threshold", type=float, default=5.0,
        help="Regression warning threshold in percent (default: 5.0)."
    )
    args = parser.parse_args()

    if not os.path.isfile(args.baseline):
        print(f"ERROR: Baseline CSV not found: {args.baseline}")
        sys.exit(1)
    if not os.path.isfile(args.current):
        print(f"ERROR: Current CSV not found: {args.current}")
        sys.exit(1)

    baseline = load_benchmark_csv(args.baseline)
    current = load_benchmark_csv(args.current)

    all_scenarios = sorted(set(baseline.keys()) | set(current.keys()))

    print("=" * 78)
    print("Performance Comparison: Baseline vs Current")
    print("=" * 78)
    print(f"  Baseline: {args.baseline}")
    print(f"  Current:  {args.current}")
    print(f"  Regression threshold: {args.threshold}%")
    print()

    header = f"{'Scenario':<45} {'Baseline(s)':>12} {'Current(s)':>12} {'Change':>10}"
    print(header)
    print("-" * len(header))

    regressions = []
    improvements = []

    for scenario in all_scenarios:
        if scenario not in baseline:
            print(f"{scenario:<45} {'N/A':>12} {current[scenario].get('median_time_s', '?'):>12} {'NEW':>10}")
            continue
        if scenario not in current:
            print(f"{scenario:<45} {baseline[scenario].get('median_time_s', '?'):>12} {'N/A':>12} {'MISSING':>10}")
            continue

        base_val = baseline[scenario].get("median_time_s", "FAIL")
        curr_val = current[scenario].get("median_time_s", "FAIL")

        if base_val == "FAIL" or curr_val == "FAIL":
            status = "FAIL"
            print(f"{scenario:<45} {base_val:>12} {curr_val:>12} {status:>10}")
            continue

        try:
            base_time = float(base_val)
            curr_time = float(curr_val)
        except ValueError:
            print(f"{scenario:<45} {base_val:>12} {curr_val:>12} {'PARSE_ERR':>10}")
            continue

        if base_time == 0.0:
            pct_change = 0.0
        else:
            pct_change = ((curr_time - base_time) / base_time) * 100.0

        if pct_change > 0:
            change_str = f"+{pct_change:.1f}%"
        else:
            change_str = f"{pct_change:.1f}%"

        # Mark regressions
        marker = ""
        if pct_change > args.threshold:
            marker = " *** REGRESSION ***"
            regressions.append((scenario, base_time, curr_time, pct_change))
        elif pct_change < -args.threshold:
            marker = " (improved)"
            improvements.append((scenario, base_time, curr_time, pct_change))

        print(f"{scenario:<45} {base_time:>12.6f} {curr_time:>12.6f} {change_str:>10}{marker}")

    print()
    print("=" * 78)

    if improvements:
        print(f"\nImprovements (>{args.threshold}% faster):")
        for scenario, base_t, curr_t, pct in improvements:
            print(f"  {scenario}: {base_t:.4f}s -> {curr_t:.4f}s ({pct:+.1f}%)")

    if regressions:
        print(f"\nWARNING: Regressions detected (>{args.threshold}% slower):")
        for scenario, base_t, curr_t, pct in regressions:
            print(f"  {scenario}: {base_t:.4f}s -> {curr_t:.4f}s ({pct:+.1f}%)")
        print()
        sys.exit(1)
    else:
        print("\nNo regressions detected.")
        sys.exit(0)


if __name__ == "__main__":
    main()
