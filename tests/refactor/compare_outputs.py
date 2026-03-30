#!/usr/bin/env python3
"""Compare SUMO simulation outputs against reference files.

Supports FCD XML, tripinfo XML, lanechanges XML, and summary XML.
Uses 1.01% relative tolerance for floating-point values, exact match for strings/IDs.

Usage:
    python compare_outputs.py --ref-dir <ref> --new-dir <new> --outputs fcd,tripinfo,lanechanges
"""

import argparse
import os
import sys
import xml.etree.ElementTree as ET

# Relative tolerance: 1.01%
REL_TOL = 0.0101
# Absolute tolerance for near-zero values
ABS_EPS = 1e-9


def _is_float(s):
    """Check if a string represents a floating-point number."""
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def _floats_close(a, b, rel_tol=REL_TOL):
    """Check if two floats are within relative tolerance."""
    fa, fb = float(a), float(b)
    if fa == fb:
        return True
    if fa == 0.0 or fb == 0.0:
        return abs(fa - fb) < ABS_EPS
    return abs(fa - fb) / max(abs(fa), abs(fb)) <= rel_tol


def _compare_attribs(ref_attribs, new_attribs, context, float_keys=None, id_keys=None):
    """Compare two attribute dicts. Returns list of mismatch descriptions.

    Parameters
    ----------
    ref_attribs : dict
        Reference attributes.
    new_attribs : dict
        New attributes to compare against reference.
    context : str
        Description of where in the XML this comparison occurs.
    float_keys : set or None
        Keys known to be floats. If None, auto-detect.
    id_keys : set or None
        Keys that must match exactly (IDs, strings).
    """
    mismatches = []
    if id_keys is None:
        id_keys = set()
    if float_keys is None:
        float_keys = set()

    all_keys = set(ref_attribs.keys()) | set(new_attribs.keys())

    for key in sorted(all_keys):
        ref_val = ref_attribs.get(key)
        new_val = new_attribs.get(key)

        if ref_val is None:
            mismatches.append(f"  {context}: key '{key}' missing in reference, present in new (value={new_val})")
            continue
        if new_val is None:
            mismatches.append(f"  {context}: key '{key}' present in reference (value={ref_val}), missing in new")
            continue

        if key in id_keys or not (_is_float(ref_val) and _is_float(new_val)):
            # Exact string match
            if ref_val != new_val:
                mismatches.append(f"  {context}: key '{key}' differs: ref='{ref_val}' vs new='{new_val}'")
        else:
            # Float comparison
            if not _floats_close(ref_val, new_val):
                mismatches.append(
                    f"  {context}: key '{key}' differs beyond tolerance: "
                    f"ref={ref_val} vs new={new_val} "
                    f"(diff={abs(float(ref_val) - float(new_val)):.6e})"
                )

    return mismatches


def compare_fcd(ref_path, new_path):
    """Compare FCD XML files timestep-by-timestep, vehicle-by-vehicle.

    Returns
    -------
    int
        Number of mismatches found.
    """
    print(f"  Comparing FCD: {os.path.basename(ref_path)} vs {os.path.basename(new_path)}")

    if not os.path.isfile(ref_path):
        print(f"    WARNING: Reference file missing: {ref_path}")
        return 0
    if not os.path.isfile(new_path):
        print(f"    ERROR: New output file missing: {new_path}")
        return 1

    ref_tree = ET.parse(ref_path)
    new_tree = ET.parse(new_path)

    ref_timesteps = {ts.get("time"): ts for ts in ref_tree.getroot().findall("timestep")}
    new_timesteps = {ts.get("time"): ts for ts in new_tree.getroot().findall("timestep")}

    all_times = sorted(set(ref_timesteps.keys()) | set(new_timesteps.keys()), key=lambda t: float(t))
    mismatches = []

    for t in all_times:
        if t not in ref_timesteps:
            mismatches.append(f"    Timestep {t}: present in new but missing in reference")
            continue
        if t not in new_timesteps:
            mismatches.append(f"    Timestep {t}: present in reference but missing in new")
            continue

        ref_vehicles = {v.get("id"): v.attrib for v in ref_timesteps[t].findall("vehicle")}
        new_vehicles = {v.get("id"): v.attrib for v in new_timesteps[t].findall("vehicle")}

        all_veh_ids = sorted(set(ref_vehicles.keys()) | set(new_vehicles.keys()))

        for vid in all_veh_ids:
            if vid not in ref_vehicles:
                mismatches.append(f"    Timestep {t}, vehicle '{vid}': in new but not in reference")
                continue
            if vid not in new_vehicles:
                mismatches.append(f"    Timestep {t}, vehicle '{vid}': in reference but not in new")
                continue

            ctx = f"Timestep {t}, vehicle '{vid}'"
            mismatches.extend(
                _compare_attribs(
                    ref_vehicles[vid], new_vehicles[vid], ctx,
                    id_keys={"id", "type", "lane", "edge", "route"}
                )
            )

    if mismatches:
        print(f"    FCD mismatches ({len(mismatches)}):")
        for m in mismatches[:50]:
            print(f"    {m}")
        if len(mismatches) > 50:
            print(f"    ... and {len(mismatches) - 50} more")
    else:
        print("    FCD: OK")

    return len(mismatches)


def compare_tripinfo(ref_path, new_path):
    """Compare tripinfo XML files.

    Compares depart, arrival, duration, routeLength, timeLoss for each trip.

    Returns
    -------
    int
        Number of mismatches found.
    """
    print(f"  Comparing tripinfo: {os.path.basename(ref_path)} vs {os.path.basename(new_path)}")

    if not os.path.isfile(ref_path):
        print(f"    WARNING: Reference file missing: {ref_path}")
        return 0
    if not os.path.isfile(new_path):
        print(f"    ERROR: New output file missing: {new_path}")
        return 1

    ref_tree = ET.parse(ref_path)
    new_tree = ET.parse(new_path)

    key_attribs = {"depart", "arrival", "duration", "routeLength", "timeLoss",
                   "departDelay", "waitingTime", "waitingCount", "rerouteNo",
                   "vType", "speedFactor"}
    id_attribs = {"id", "vType"}

    ref_trips = {trip.get("id"): trip.attrib for trip in ref_tree.getroot().findall("tripinfo")}
    new_trips = {trip.get("id"): trip.attrib for trip in new_tree.getroot().findall("tripinfo")}

    all_ids = sorted(set(ref_trips.keys()) | set(new_trips.keys()))
    mismatches = []

    for tid in all_ids:
        if tid not in ref_trips:
            mismatches.append(f"    Trip '{tid}': in new but not in reference")
            continue
        if tid not in new_trips:
            mismatches.append(f"    Trip '{tid}': in reference but not in new")
            continue

        ctx = f"Trip '{tid}'"
        # Only compare known key attributes
        ref_subset = {k: v for k, v in ref_trips[tid].items() if k in key_attribs}
        new_subset = {k: v for k, v in new_trips[tid].items() if k in key_attribs}
        mismatches.extend(_compare_attribs(ref_subset, new_subset, ctx, id_keys=id_attribs))

    if mismatches:
        print(f"    Tripinfo mismatches ({len(mismatches)}):")
        for m in mismatches[:50]:
            print(f"    {m}")
        if len(mismatches) > 50:
            print(f"    ... and {len(mismatches) - 50} more")
    else:
        print("    Tripinfo: OK")

    return len(mismatches)


def compare_lanechanges(ref_path, new_path):
    """Compare lane change event XML files.

    Returns
    -------
    int
        Number of mismatches found.
    """
    print(f"  Comparing lanechanges: {os.path.basename(ref_path)} vs {os.path.basename(new_path)}")

    if not os.path.isfile(ref_path):
        print(f"    WARNING: Reference file missing: {ref_path}")
        return 0
    if not os.path.isfile(new_path):
        print(f"    ERROR: New output file missing: {new_path}")
        return 1

    ref_tree = ET.parse(ref_path)
    new_tree = ET.parse(new_path)

    # Lane change events may be top-level <change> elements or nested under <timestep>
    ref_changes = []
    new_changes = []

    # Try flat structure first
    for elem in ref_tree.getroot().iter("change"):
        ref_changes.append(elem.attrib)
    for elem in new_tree.getroot().iter("change"):
        new_changes.append(elem.attrib)

    # Sort both lists by (time, id) so comparison is order-independent.
    def _lc_sort_key(attribs):
        t = attribs.get("time", "0")
        try:
            t = float(t)
        except ValueError:
            t = 0.0
        return (t, attribs.get("id", ""))

    ref_changes.sort(key=_lc_sort_key)
    new_changes.sort(key=_lc_sort_key)

    mismatches = []

    if len(ref_changes) != len(new_changes):
        mismatches.append(
            f"    Lane change count differs: ref={len(ref_changes)} vs new={len(new_changes)}"
        )

    id_keys = {"id", "type", "from", "to", "dir", "reason"}
    min_len = min(len(ref_changes), len(new_changes))

    for i in range(min_len):
        ctx = f"LaneChange #{i} (time={ref_changes[i].get('time', '?')}, id={ref_changes[i].get('id', '?')})"
        mismatches.extend(_compare_attribs(ref_changes[i], new_changes[i], ctx, id_keys=id_keys))

    if mismatches:
        print(f"    Lanechange mismatches ({len(mismatches)}):")
        for m in mismatches[:50]:
            print(f"    {m}")
        if len(mismatches) > 50:
            print(f"    ... and {len(mismatches) - 50} more")
    else:
        print("    Lanechanges: OK")

    return len(mismatches)


def compare_summary(ref_path, new_path):
    """Compare summary XML files.

    Returns
    -------
    int
        Number of mismatches found.
    """
    print(f"  Comparing summary: {os.path.basename(ref_path)} vs {os.path.basename(new_path)}")

    if not os.path.isfile(ref_path):
        print(f"    WARNING: Reference file missing: {ref_path}")
        return 0
    if not os.path.isfile(new_path):
        print(f"    ERROR: New output file missing: {new_path}")
        return 1

    ref_tree = ET.parse(ref_path)
    new_tree = ET.parse(new_path)

    # 'duration' is wall-clock time per step (non-deterministic), exclude from comparison
    SKIP_KEYS = {"duration"}

    ref_steps = {s.get("time"): {k: v for k, v in s.attrib.items() if k not in SKIP_KEYS}
                 for s in ref_tree.getroot().findall("step")}
    new_steps = {s.get("time"): {k: v for k, v in s.attrib.items() if k not in SKIP_KEYS}
                 for s in new_tree.getroot().findall("step")}

    all_times = sorted(set(ref_steps.keys()) | set(new_steps.keys()), key=lambda t: float(t))
    mismatches = []

    for t in all_times:
        if t not in ref_steps:
            mismatches.append(f"    Step time={t}: in new but not in reference")
            continue
        if t not in new_steps:
            mismatches.append(f"    Step time={t}: in reference but not in new")
            continue

        ctx = f"Summary step time={t}"
        mismatches.extend(_compare_attribs(ref_steps[t], new_steps[t], ctx, id_keys={"time"}))

    if mismatches:
        print(f"    Summary mismatches ({len(mismatches)}):")
        for m in mismatches[:50]:
            print(f"    {m}")
        if len(mismatches) > 50:
            print(f"    ... and {len(mismatches) - 50} more")
    else:
        print("    Summary: OK")

    return len(mismatches)


# Mapping from output type name to (comparison function, file suffix)
OUTPUT_TYPES = {
    "fcd": (compare_fcd, "fcd.xml"),
    "tripinfo": (compare_tripinfo, "tripinfo.xml"),
    "lanechanges": (compare_lanechanges, "lanechanges.xml"),
    "summary": (compare_summary, "summary.xml"),
}


def compare_directories(ref_dir, new_dir, output_types):
    """Compare all specified output types between two directories.

    Parameters
    ----------
    ref_dir : str
        Path to the reference output directory.
    new_dir : str
        Path to the new output directory.
    output_types : list of str
        Which output types to compare (e.g., ["fcd", "tripinfo"]).

    Returns
    -------
    int
        Total number of mismatches across all output types.
    """
    total_mismatches = 0

    for otype in output_types:
        if otype not in OUTPUT_TYPES:
            print(f"  WARNING: Unknown output type '{otype}', skipping")
            continue

        cmp_func, suffix = OUTPUT_TYPES[otype]
        ref_path = os.path.join(ref_dir, suffix)
        new_path = os.path.join(new_dir, suffix)
        total_mismatches += cmp_func(ref_path, new_path)

    return total_mismatches


def main():
    parser = argparse.ArgumentParser(
        description="Compare SUMO simulation outputs against reference files."
    )
    parser.add_argument(
        "--ref-dir", required=True,
        help="Path to the reference output directory."
    )
    parser.add_argument(
        "--new-dir", required=True,
        help="Path to the new output directory."
    )
    parser.add_argument(
        "--outputs", default="fcd,tripinfo,lanechanges,summary",
        help="Comma-separated list of output types to compare (default: fcd,tripinfo,lanechanges,summary)."
    )
    args = parser.parse_args()

    if not os.path.isdir(args.ref_dir):
        print(f"ERROR: Reference directory does not exist: {args.ref_dir}")
        sys.exit(1)
    if not os.path.isdir(args.new_dir):
        print(f"ERROR: New output directory does not exist: {args.new_dir}")
        sys.exit(1)

    output_types = [o.strip() for o in args.outputs.split(",")]
    total = compare_directories(args.ref_dir, args.new_dir, output_types)

    print(f"\nTotal mismatches: {total}")
    sys.exit(0 if total == 0 else 1)


if __name__ == "__main__":
    main()
