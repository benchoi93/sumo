#!/usr/bin/env python3
"""Generate a 5x5 signalized grid network using SUMO's netgenerate.

Run: python generate_network.py [--netgenerate-binary path]
Produces: net.net.xml in the same directory.
"""
import subprocess
import sys
import os

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    netgen = sys.argv[1] if len(sys.argv) > 1 else "netgenerate"
    output = os.path.join(script_dir, "net.net.xml")

    cmd = [
        netgen,
        "--grid",
        "--grid.x-number", "5",
        "--grid.y-number", "5",
        "--grid.x-length", "300",
        "--grid.y-length", "300",
        "--grid.attach-length", "200",
        "--default.lanenumber", "2",
        "--default.speed", "13.89",
        "--tls.guess", "true",
        "--output-file", output,
        "--no-turnarounds",
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAILED: {result.stderr}")
        sys.exit(1)
    print(f"Network written to {output}")

if __name__ == "__main__":
    main()
