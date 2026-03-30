#!/usr/bin/env python3
"""TraCI stress test client for refactoring verification.

Connects to SUMO via TraCI, steps through the simulation, and queries
getSpeed and getPosition for every vehicle at every time step.
Results are written to traci_output.csv.

Usage:
    python traci_client.py [--sumo-binary SUMO_BINARY] [--output OUTPUT_FILE]

The script can be run standalone (it will start SUMO as a subprocess)
or integrated into a test harness.
"""
import argparse
import csv
import os
import sys
from pathlib import Path

# Locate the SUMO tools directory relative to this repo
SUMO_HOME = str(Path(__file__).resolve().parents[4])
TOOLS_DIR = os.path.join(SUMO_HOME, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import traci  # noqa: E402


def run_traci_queries(
    sumo_binary: str = None,
    config_file: str = None,
    output_file: str = None,
) -> dict:
    """Run SUMO with TraCI, querying vehicle states at every step.

    Args:
        sumo_binary: Path to the sumo binary. Defaults to
            {SUMO_HOME}/bin/sumo.
        config_file: Path to .sumocfg. Defaults to
            traci_queries.sumocfg in this directory.
        output_file: Path to write CSV results. Defaults to
            traci_output.csv in this directory.

    Returns:
        dict with keys:
            total_steps: number of simulation steps executed
            total_queries: total number of vehicle queries performed
            vehicles_seen: set of all vehicle IDs observed
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    if sumo_binary is None:
        sumo_binary = os.path.join(SUMO_HOME, "bin", "sumo")
    if config_file is None:
        config_file = os.path.join(script_dir, "traci_queries.sumocfg")
    if output_file is None:
        output_file = os.path.join(script_dir, "traci_output.csv")

    sumo_cmd = [sumo_binary, "-c", config_file]

    traci.start(sumo_cmd)

    total_steps = 0
    total_queries = 0
    vehicles_seen = set()

    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "vehicle_id", "speed", "x", "y"])

        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            current_time = traci.simulation.getTime()
            total_steps += 1

            vehicle_ids = traci.vehicle.getIDList()
            for vid in vehicle_ids:
                speed = traci.vehicle.getSpeed(vid)
                x, y = traci.vehicle.getPosition(vid)
                writer.writerow([
                    f"{current_time:.1f}",
                    vid,
                    f"{speed:.4f}",
                    f"{x:.4f}",
                    f"{y:.4f}",
                ])
                total_queries += 1
                vehicles_seen.add(vid)

    traci.close()

    stats = {
        "total_steps": total_steps,
        "total_queries": total_queries,
        "vehicles_seen": vehicles_seen,
    }

    print(f"TraCI stress test complete:")
    print(f"  Steps executed:   {total_steps}")
    print(f"  Total queries:    {total_queries}")
    print(f"  Unique vehicles:  {len(vehicles_seen)}")
    print(f"  Output written:   {output_file}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="TraCI stress test for refactoring verification"
    )
    parser.add_argument(
        "--sumo-binary",
        default=None,
        help="Path to SUMO binary (default: {SUMO_HOME}/bin/sumo)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output CSV file path (default: traci_output.csv)",
    )
    args = parser.parse_args()

    run_traci_queries(
        sumo_binary=args.sumo_binary,
        output_file=args.output,
    )


if __name__ == "__main__":
    main()
