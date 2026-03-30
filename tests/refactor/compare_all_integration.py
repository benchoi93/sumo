#!/usr/bin/env python3
"""Run all integration tests and compare against reference outputs.

Finds all integration scenarios under tests/refactor/integration/, runs SUMO on each,
saves outputs to current/ subdirectory, and compares current/ vs reference/ using
the compare_outputs module.

Usage:
    python compare_all_integration.py [--sumo-binary path]
"""

import argparse
import os
import subprocess
import sys

# Ensure this script's directory is on the path so we can import compare_outputs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare_outputs import compare_directories


def find_integration_scenarios(base_dir):
    """Find all .sumocfg files under the integration/ subdirectory.

    Parameters
    ----------
    base_dir : str
        Base directory containing the integration/ subdirectory.

    Returns
    -------
    list of tuple
        Each tuple is (scenario_name, sumocfg_path, scenario_dir).
    """
    scenarios = []
    integ_dir = os.path.join(base_dir, "integration")

    if not os.path.isdir(integ_dir):
        print(f"WARNING: Integration directory not found: {integ_dir}")
        return scenarios

    for root, dirs, files in os.walk(integ_dir):
        for f in files:
            if f.endswith(".sumocfg"):
                cfg_path = os.path.join(root, f)
                rel = os.path.relpath(root, base_dir)
                scenario_name = f"{rel}/{os.path.splitext(f)[0]}"
                scenarios.append((scenario_name, cfg_path, root))

    return sorted(scenarios, key=lambda x: x[0])


def run_and_compare(sumo_binary, scenario_name, sumocfg_path, scenario_dir):
    """Run SUMO on a scenario and compare outputs against reference.

    Parameters
    ----------
    sumo_binary : str
        Path to the SUMO binary.
    scenario_name : str
        Human-readable scenario name.
    sumocfg_path : str
        Path to the .sumocfg file.
    scenario_dir : str
        Directory containing the scenario files.

    Returns
    -------
    bool
        True if outputs match reference, False otherwise.
    """
    ref_dir = os.path.join(scenario_dir, "reference")
    cur_dir = os.path.join(scenario_dir, "current")

    if not os.path.isdir(ref_dir):
        print(f"  SKIP: {scenario_name} (no reference/ directory)")
        return True

    os.makedirs(cur_dir, exist_ok=True)

    fcd_out = os.path.join(cur_dir, "fcd.xml")
    tripinfo_out = os.path.join(cur_dir, "tripinfo.xml")
    lanechanges_out = os.path.join(cur_dir, "lanechanges.xml")
    summary_out = os.path.join(cur_dir, "summary.xml")

    cmd = [
        sumo_binary,
        "-c", sumocfg_path,
        "--seed", "42",
        "--default.speeddev", "0",
        "--fcd-output", fcd_out,
        "--tripinfo-output", tripinfo_out,
        "--lanechange-output", lanechanges_out,
        "--summary-output", summary_out,
        "--no-warnings", "true",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=scenario_dir,
        )
        if result.returncode != 0:
            print(f"  FAIL: {scenario_name} (SUMO exited with code {result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[:5]:
                    print(f"    stderr: {line}")
            return False

    except subprocess.TimeoutExpired:
        print(f"  FAIL: {scenario_name} (timeout after 600s)")
        return False
    except FileNotFoundError:
        print(f"  FAIL: {scenario_name} (SUMO binary not found: {sumo_binary})")
        return False
    except Exception as e:
        print(f"  FAIL: {scenario_name} ({e})")
        return False

    # Compare outputs
    print(f"  Comparing: {scenario_name}")
    output_types = ["fcd", "tripinfo", "lanechanges", "summary"]
    mismatches = compare_directories(ref_dir, cur_dir, output_types)

    if mismatches == 0:
        print(f"  PASS: {scenario_name}")
        return True
    else:
        print(f"  FAIL: {scenario_name} ({mismatches} mismatches)")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run all integration tests and compare against references."
    )
    parser.add_argument(
        "--sumo-binary", default="sumo",
        help="Path to the SUMO binary (default: 'sumo' from PATH)."
    )
    parser.add_argument(
        "--base-dir", default=None,
        help="Base directory for test scenarios. Defaults to the directory containing this script."
    )
    args = parser.parse_args()

    if args.base_dir is None:
        args.base_dir = os.path.dirname(os.path.abspath(__file__))

    print("=" * 60)
    print("Integration Tests")
    print("=" * 60)
    print(f"  SUMO binary: {args.sumo_binary}")
    print(f"  Base dir:    {args.base_dir}")
    print()

    scenarios = find_integration_scenarios(args.base_dir)

    if not scenarios:
        print("No integration scenarios found!")
        sys.exit(1)

    print(f"Found {len(scenarios)} integration scenario(s):\n")

    pass_count = 0
    fail_count = 0
    skip_count = 0

    for scenario_name, sumocfg_path, scenario_dir in scenarios:
        ref_dir = os.path.join(scenario_dir, "reference")
        if not os.path.isdir(ref_dir):
            print(f"  SKIP: {scenario_name} (no reference/ directory)")
            skip_count += 1
            continue

        success = run_and_compare(args.sumo_binary, scenario_name, sumocfg_path, scenario_dir)
        if success:
            pass_count += 1
        else:
            fail_count += 1

    print()
    print("=" * 60)
    print(f"Integration Test Results: {pass_count} PASS, {fail_count} FAIL, {skip_count} SKIP")
    print("=" * 60)

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
