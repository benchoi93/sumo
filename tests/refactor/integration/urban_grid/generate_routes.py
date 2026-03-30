#!/usr/bin/env python3
"""Generate random routes on the urban grid network using SUMO's randomTrips.

Run: python generate_routes.py [--sumo-home path]
Produces: routes.rou.xml with 2000 vehicles.
"""
import subprocess
import sys
import os

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sumo_home = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SUMO_HOME", "")
    random_trips = os.path.join(sumo_home, "tools", "randomTrips.py") if sumo_home else "randomTrips.py"

    net_file = os.path.join(script_dir, "net.net.xml")
    route_file = os.path.join(script_dir, "routes.rou.xml")
    trip_file = os.path.join(script_dir, "trips.trips.xml")

    if not os.path.exists(net_file):
        print(f"ERROR: {net_file} not found. Run generate_network.py first.")
        sys.exit(1)

    # Generate random trips
    cmd = [
        sys.executable, random_trips,
        "-n", net_file,
        "-o", trip_file,
        "-r", route_file,
        "--seed", "42",
        "--period", "0.9",  # ~2000 vehicles over 1800s
        "-b", "0",
        "-e", "1800",
        "--fringe-factor", "5",  # prefer starting from grid edges
        "--trip-attributes", 'departLane="best" departSpeed="max"',
        "--vehicle-class", "passenger",
        "--validate",
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAILED: {result.stderr}")
        # Try without validate flag
        cmd.remove("--validate")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"FAILED again: {result.stderr}")
            sys.exit(1)
    print(f"Routes written to {route_file}")

if __name__ == "__main__":
    main()
