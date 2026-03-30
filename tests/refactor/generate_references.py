#!/usr/bin/env python3
"""Generate reference outputs for all component and integration test scenarios.

Finds all .sumocfg files under tests/refactor/component/ and tests/refactor/integration/,
runs SUMO on each with --seed 42 --default.speeddev 0, and captures FCD, tripinfo,
lanechanges, and summary outputs to a reference/ subdirectory.

Usage:
    python generate_references.py [--sumo-binary path] [--scenarios component|integration|all]
"""

import argparse
import os
import subprocess
import sys


def find_scenarios(base_dir, scenario_filter="all"):
    """Find all .sumocfg files under the specified scenario directories.

    Parameters
    ----------
    base_dir : str
        Base directory containing component/ and integration/ subdirectories.
    scenario_filter : str
        One of 'component', 'integration', or 'all'.

    Returns
    -------
    list of tuple
        Each tuple is (scenario_name, sumocfg_path, scenario_dir).
    """
    scenarios = []
    subdirs = []

    if scenario_filter in ("component", "all"):
        comp_dir = os.path.join(base_dir, "component")
        if os.path.isdir(comp_dir):
            subdirs.append(("component", comp_dir))
        else:
            print(f"WARNING: Component directory not found: {comp_dir}")

    if scenario_filter in ("integration", "all"):
        integ_dir = os.path.join(base_dir, "integration")
        if os.path.isdir(integ_dir):
            subdirs.append(("integration", integ_dir))
        else:
            print(f"WARNING: Integration directory not found: {integ_dir}")

    for category, sdir in subdirs:
        for root, dirs, files in os.walk(sdir):
            for f in files:
                if f.endswith(".sumocfg"):
                    cfg_path = os.path.join(root, f)
                    # Scenario name: relative path from base_dir
                    rel = os.path.relpath(root, base_dir)
                    scenario_name = f"{rel}/{os.path.splitext(f)[0]}"
                    scenarios.append((scenario_name, cfg_path, root))

    return sorted(scenarios, key=lambda x: x[0])


def run_scenario(sumo_binary, scenario_name, sumocfg_path, scenario_dir):
    """Run SUMO on a single scenario and save outputs to reference/ subdirectory.

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
        True if the scenario ran successfully, False otherwise.
    """
    ref_dir = os.path.join(scenario_dir, "reference")
    os.makedirs(ref_dir, exist_ok=True)

    fcd_out = os.path.join(ref_dir, "fcd.xml")
    tripinfo_out = os.path.join(ref_dir, "tripinfo.xml")
    lanechanges_out = os.path.join(ref_dir, "lanechanges.xml")
    summary_out = os.path.join(ref_dir, "summary.xml")

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
            timeout=300,
            cwd=scenario_dir,
        )
        if result.returncode != 0:
            print(f"  FAIL: {scenario_name}")
            print(f"    SUMO exited with code {result.returncode}")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[:10]:
                    print(f"    stderr: {line}")
            return False

        print(f"  OK:   {scenario_name}")
        return True

    except subprocess.TimeoutExpired:
        print(f"  FAIL: {scenario_name} (timeout after 300s)")
        return False
    except FileNotFoundError:
        print(f"  FAIL: {scenario_name} (SUMO binary not found: {sumo_binary})")
        return False
    except Exception as e:
        print(f"  FAIL: {scenario_name} ({e})")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate reference outputs for SUMO refactoring test scenarios."
    )
    parser.add_argument(
        "--sumo-binary", default="sumo",
        help="Path to the SUMO binary (default: 'sumo' from PATH)."
    )
    parser.add_argument(
        "--scenarios", choices=["component", "integration", "all"], default="all",
        help="Which scenario categories to generate references for (default: all)."
    )
    parser.add_argument(
        "--base-dir", default=None,
        help="Base directory for test scenarios. Defaults to the directory containing this script."
    )
    args = parser.parse_args()

    if args.base_dir is None:
        args.base_dir = os.path.dirname(os.path.abspath(__file__))

    print(f"Generating reference outputs...")
    print(f"  SUMO binary: {args.sumo_binary}")
    print(f"  Base dir:    {args.base_dir}")
    print(f"  Scenarios:   {args.scenarios}")
    print()

    scenarios = find_scenarios(args.base_dir, args.scenarios)

    if not scenarios:
        print("No scenarios found!")
        sys.exit(1)

    print(f"Found {len(scenarios)} scenario(s):\n")

    ok_count = 0
    fail_count = 0

    for scenario_name, sumocfg_path, scenario_dir in scenarios:
        success = run_scenario(args.sumo_binary, scenario_name, sumocfg_path, scenario_dir)
        if success:
            ok_count += 1
        else:
            fail_count += 1

    print(f"\nResults: {ok_count} OK, {fail_count} FAIL out of {len(scenarios)} scenarios")
    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
