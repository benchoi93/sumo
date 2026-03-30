# SUMO Performance Refactoring Plan

## Context

SUMO's microsimulator has well-documented performance bottlenecks: string-keyed `std::map` lookups, virtual dispatch in hot loops, AoS memory layout with scattered heap objects, deep 4-level inheritance, and mostly single-threaded execution. This plan refactors SUMO incrementally for performance while maintaining behavioral correctness, using NextSim (https://github.com/AIxMobility/NextSim.git) as architectural reference.

**Key constraint**: SUMO's existing TextTest infrastructure compares FCD/tripinfo/lanechange XML output against reference files with 1.01% floating-point tolerance. Every refactoring PR must produce bit-identical (or within-tolerance) output.

---

## Part 1: Multi-Level Test Framework for Behavioral Verification

Before any refactoring, we create a **4-level verification pyramid** that gates every PR.

### Level 1: Unit Tests (per-function correctness)

**Location**: `tests/refactor/unit/`

Create GTest-based unit tests for each function we touch:

| Test File | What It Verifies |
|-----------|-----------------|
| `test_map_lookup.cpp` | `MSEdge::dictionary()`, `MSVehicleControl::getVehicle()` return identical results with `unordered_map` vs `std::map` |
| `test_leader_info.cpp` | `MSLeaderInfo` pooled reuse produces same `getSubLaneBorders()`, `addLeader()`, `clear()` behavior as fresh allocation |
| `test_active_lanes.cpp` | `MSEdgeControl` active-lane iteration order (neighbors-first invariant) preserved with `std::vector` replacement |
| `test_drive_items.cpp` | `DriveItemVector` swap vs copy produces identical `myLFLinkLanesPrev` contents |
| `test_cf_dispatch.cpp` | Krauss fast-path `static_cast` dispatch produces same `followSpeed()`, `stopSpeed()`, `finalizeSpeed()` as virtual dispatch for all parameter combinations |
| `test_globals_policy.cpp` | Template-specialized `planMovements<Euler,Sublane>` produces same results as runtime-branched version for all 4 flag combinations |

**Implementation pattern**: Each test captures the output of the **old** code path and compares against the **new** code path within the same binary using a compile-time or runtime switch.

```cpp
// Pattern: dual-path comparison test
TEST(MapLookup, UnorderedMapMatchesStdMap) {
    // Build both containers with same data
    std::map<std::string, MSEdge*> oldDict;
    std::unordered_map<std::string, MSEdge*> newDict;
    // ... populate with test edges ...

    // Verify all lookups return identical results
    for (const auto& id : testIDs) {
        EXPECT_EQ(oldDict.at(id), newDict.at(id));
    }
    // Verify iteration produces same set (order may differ)
    std::set<std::string> oldKeys, newKeys;
    for (auto& [k,v] : oldDict) oldKeys.insert(k);
    for (auto& [k,v] : newDict) newKeys.insert(k);
    EXPECT_EQ(oldKeys, newKeys);
}
```

### Level 2: Component Tests (per-module behavioral equivalence)

**Location**: `tests/refactor/component/`

Isolated simulation scenarios that exercise ONE subsystem intensively. Each produces FCD + tripinfo + lanechanges output compared against pre-recorded reference.

| Test Scenario | Config File | What It Stresses | Outputs Compared |
|--------------|-------------|-----------------|------------------|
| `cf_krauss_platoon` | `cf_krauss_platoon.sumocfg` | 50 vehicles, single lane, Krauss CF, 600s | FCD (position, speed per step) |
| `cf_idm_platoon` | `cf_idm_platoon.sumocfg` | 50 vehicles, single lane, IDM CF, 600s | FCD |
| `cf_eidm_platoon` | `cf_eidm_platoon.sumocfg` | 50 vehicles, single lane, EIDM CF, 600s | FCD |
| `cf_mixed_models` | `cf_mixed.sumocfg` | 100 vehicles, 3 CF models on same road | FCD + tripinfos |
| `lc_highway_merge` | `lc_merge.sumocfg` | 200 vehicles, 3-to-2 lane merge, LC2013 | FCD + lanechanges |
| `lc_sublane_weave` | `lc_sublane.sumocfg` | 100 vehicles, sublane model (SL2015), weaving | FCD + lanechanges |
| `junction_signalized` | `junction_signal.sumocfg` | 4-leg signalized intersection, 500 veh | FCD + tripinfos |
| `junction_priority` | `junction_prio.sumocfg` | Priority intersection with yielding | FCD + tripinfos |
| `insertion_heavy` | `insertion.sumocfg` | 10K vehicles departing in 100s burst | tripinfos (departure delays) |
| `traci_queries` | `traci_stress.sumocfg` | 100 vehicles + Python TraCI client doing per-step getSpeed/getPosition | testclient_out |

**Network files**: Use existing SUMO test networks from `tests/sumo/cf_model/` and `tests/sumo/lc_model/` to avoid creating new ones.

**Reference generation script** (`tests/refactor/generate_references.py`):
```python
#!/usr/bin/env python3
"""Run all component tests with UNMODIFIED SUMO and save reference outputs."""
import subprocess, shutil, os

SCENARIOS = [
    "cf_krauss_platoon", "cf_idm_platoon", "cf_eidm_platoon",
    "cf_mixed_models", "lc_highway_merge", "lc_sublane_weave",
    "junction_signalized", "junction_priority", "insertion_heavy"
]

for scenario in SCENARIOS:
    cfg = f"tests/refactor/component/{scenario}/{scenario}.sumocfg"
    outdir = f"tests/refactor/component/{scenario}/reference/"
    os.makedirs(outdir, exist_ok=True)
    subprocess.run([
        "sumo", "-c", cfg,
        "--fcd-output", f"{outdir}/fcd.xml",
        "--tripinfo-output", f"{outdir}/tripinfos.xml",
        "--lanechange-output", f"{outdir}/lanechanges.xml",
        "--summary-output", f"{outdir}/summary.xml",
        "--no-step-log", "--duration-log.statistics",
        "--seed", "42"
    ], check=True)
    print(f"  [OK] {scenario}")
```

**Comparison script** (`tests/refactor/compare_outputs.py`):
```python
#!/usr/bin/env python3
"""Compare current SUMO output against reference with tolerance."""
import xml.etree.ElementTree as ET
import sys, math

TOLERANCE = 0.0101  # 1.01% -- matches SUMO's TextTest config

def compare_fcd(ref_path, new_path):
    """Compare FCD XML files with floating-point tolerance."""
    ref = ET.parse(ref_path)
    new = ET.parse(new_path)

    mismatches = 0
    for ref_ts, new_ts in zip(ref.findall('.//timestep'), new.findall('.//timestep')):
        assert ref_ts.get('time') == new_ts.get('time'), f"Timestep mismatch"
        ref_vehs = {v.get('id'): v for v in ref_ts.findall('vehicle')}
        new_vehs = {v.get('id'): v for v in new_ts.findall('vehicle')}

        assert set(ref_vehs.keys()) == set(new_vehs.keys()), \
            f"Vehicle set mismatch at t={ref_ts.get('time')}"

        for vid in ref_vehs:
            for attr in ['x', 'y', 'speed', 'pos', 'angle']:
                rv = float(ref_vehs[vid].get(attr, 0))
                nv = float(new_vehs[vid].get(attr, 0))
                if rv != 0 and abs(rv - nv) / abs(rv) > TOLERANCE:
                    mismatches += 1
                    print(f"  MISMATCH t={ref_ts.get('time')} veh={vid} "
                          f"{attr}: ref={rv} new={nv} diff={abs(rv-nv)/abs(rv):.4%}")

    return mismatches
```

### Level 3: Integration Tests (full simulation equivalence)

**Location**: `tests/refactor/integration/`

Larger, realistic scenarios that exercise all subsystems together.

| Scenario | Description | Vehicles | Duration | Outputs |
|----------|------------|----------|----------|---------|
| `highway_corridor` | 3-lane highway, 10km, on-ramp merge, Krauss + IDM mix | 5,000 | 3600s | FCD, tripinfos, lanechanges, summary |
| `urban_grid` | 5x5 signalized grid, mixed vehicle types | 2,000 | 1800s | FCD, tripinfos, lanechanges, detector |
| `large_network` | Real-world excerpt (Bologna or Luxembourg from SUMO scenarios) | 10,000 | 1800s | tripinfos, summary (FCD too large) |
| `meso_micro_compare` | Same network run in micro vs meso, compare aggregate stats | 5,000 | 3600s | summary, detector |

**Key**: These use `--seed 42` and `--default.speeddev 0` to eliminate stochastic variation. The reference is generated once with the unmodified SUMO and never changes.

**CI integration** (`tests/refactor/run_all.sh`):
```bash
#!/bin/bash
set -e
echo "=== Level 1: Unit Tests ==="
cd build && ctest --test-dir unittest -R refactor --output-on-failure

echo "=== Level 2: Component Tests ==="
python3 tests/refactor/compare_all_components.py

echo "=== Level 3: Integration Tests ==="
python3 tests/refactor/compare_all_integration.py

echo "=== Level 4: Performance Benchmark ==="
python3 tests/refactor/benchmark.py --baseline results/baseline.csv --output results/current.csv
python3 tests/refactor/compare_perf.py results/baseline.csv results/current.csv
```

### Level 4: Performance Regression Tests

**Location**: `tests/refactor/benchmark/`

Not behavioral -- these measure that refactoring actually improves performance and doesn't regress.

| Benchmark | Scenario | Metric | Baseline Target |
|-----------|----------|--------|----------------|
| `bench_plan_movements` | highway_corridor | `planMovements` wall time (ms/step) | Record baseline |
| `bench_exec_movements` | highway_corridor | `executeMovements` wall time (ms/step) | Record baseline |
| `bench_change_lanes` | urban_grid | `changeLanes` wall time (ms/step) | Record baseline |
| `bench_traci_lookup` | traci_stress | `getVehicle()` latency (ns/call) | Record baseline |
| `bench_total_sim` | large_network | Total simulation time (s) | Record baseline |
| `bench_cache_misses` | highway_corridor | L1-dcache-load-misses (perf stat) | Record baseline |

**Benchmark script** (`tests/refactor/benchmark.py`):
```python
#!/usr/bin/env python3
"""Run performance benchmarks and output CSV."""
import subprocess, time, csv, sys

BENCHMARKS = {
    "highway_corridor": "tests/refactor/integration/highway_corridor/highway_corridor.sumocfg",
    "urban_grid": "tests/refactor/integration/urban_grid/urban_grid.sumocfg",
}

results = []
for name, cfg in BENCHMARKS.items():
    # Run 3 times, take median
    times = []
    for _ in range(3):
        start = time.perf_counter()
        subprocess.run(["sumo", "-c", cfg, "--no-step-log", "--seed", "42",
                        "--duration-log.statistics", "--default.speeddev", "0"],
                       capture_output=True, check=True)
        times.append(time.perf_counter() - start)
    times.sort()
    results.append({"scenario": name, "median_time_s": times[1]})

# Write CSV
with open(sys.argv[2] if len(sys.argv) > 2 else "benchmark.csv", "w") as f:
    writer = csv.DictWriter(f, fieldnames=["scenario", "median_time_s"])
    writer.writeheader()
    writer.writerows(results)
```

### Test File Summary

```
tests/refactor/
├── unit/                              # Level 1: GTest unit tests
│   ├── CMakeLists.txt
│   ├── test_map_lookup.cpp
│   ├── test_leader_info.cpp
│   ├── test_active_lanes.cpp
│   ├── test_drive_items.cpp
│   ├── test_cf_dispatch.cpp
│   └── test_globals_policy.cpp
├── component/                         # Level 2: Single-subsystem scenarios
│   ├── cf_krauss_platoon/
│   │   ├── cf_krauss_platoon.sumocfg
│   │   ├── net.net.xml
│   │   ├── routes.rou.xml
│   │   └── reference/                 # Generated once with unmodified SUMO
│   │       ├── fcd.xml
│   │       ├── tripinfos.xml
│   │       └── lanechanges.xml
│   ├── cf_idm_platoon/
│   ├── cf_eidm_platoon/
│   ├── cf_mixed_models/
│   ├── lc_highway_merge/
│   ├── lc_sublane_weave/
│   ├── junction_signalized/
│   ├── junction_priority/
│   ├── insertion_heavy/
│   └── traci_queries/
├── integration/                       # Level 3: Full-network scenarios
│   ├── highway_corridor/
│   ├── urban_grid/
│   ├── large_network/
│   └── meso_micro_compare/
├── benchmark/                         # Level 4: Performance baselines
│   ├── results/
│   │   └── baseline.csv
│   └── perf_configs/
├── generate_references.py             # One-time reference generation
├── compare_outputs.py                 # FCD/tripinfo XML comparator
├── compare_all_components.py          # Run all Level 2 tests
├── compare_all_integration.py         # Run all Level 3 tests
├── benchmark.py                       # Performance measurement
├── compare_perf.py                    # Performance regression check
└── run_all.sh                         # Master test runner (all 4 levels)
```

---

## Part 2: Phased Refactoring Plan

### Phase 0: Benchmarking Infrastructure (2 PRs)

**PR 0.1: Instrument `simulationStep()` with per-phase timing**
- Files: `src/microsim/MSNet.h`, `MSNet.cpp` (lines 782-918)
- Add `StopWatch` members for each simulation phase (planMove, execMove, changeLanes, insertion, events)
- Report via `--duration-log.statistics`
- Risk: Very low (additive only)

**PR 0.2: Create benchmark scenarios + perf regression script**
- Create `tests/refactor/benchmark/` with 4 standardized scenarios
- Python script to run, collect timing CSV, compare against baseline
- Risk: None (no simulator changes)

### Phase 1: Low-Risk, High-Impact (5 PRs)

**PR 1.1: Replace `std::map<string,T*>` with `std::unordered_map` in all dictionaries**
- Files: `MSEdge.h:1035`, `MSLane.h:1630`, `MSVehicleControl.h:656,679`, `MSRoute.h:318`, `NamedObjectCont.h:44`
- Replace `DictType` typedefs; change `lower_bound`+`emplace_hint` to `try_emplace`
- Add explicit sort where deterministic output order is required (`getSortedIDList()`)
- Expected: 2-5x faster TraCI lookups, 15-25% faster net loading
- Test gate: Level 1 (`test_map_lookup`), Level 2 (all), Level 3 (all)

**PR 1.2: Pool `MSLeaderInfo` per lane (eliminate per-step allocations)**
- Files: `MSLane.h` (add `myLeaderInfoBuffer` member), `MSLane.cpp:1562-1597`
- Reuse pre-allocated buffer via `clear()` instead of constructing new each step
- Expected: ~2-5% in `planMovements`
- Test gate: Level 1 (`test_leader_info`), Level 2 (cf_*, lc_sublane)

**PR 1.3: Replace `std::list<MSLane*>` with `std::vector<MSLane*>` for active lanes**
- Files: `MSEdgeControl.h`, `MSEdgeControl.cpp` (lines 118-336)
- Two-region vector: `[0,neighborBoundary)` = multi-lane, `[neighborBoundary,size)` = single-lane
- Swap-with-back-and-pop for deactivation
- Expected: ~5-10% in all per-step phases (cache-friendly iteration)
- Test gate: Level 1 (`test_active_lanes`), Level 2 (all), Level 3 (all)

**PR 1.4: Swap `myLFLinkLanesPrev` instead of copying**
- Files: `MSVehicle.cpp:2150`
- Change `myLFLinkLanesPrev = myLFLinkLanes` to `myLFLinkLanesPrev.swap(myLFLinkLanes)`
- Add `myLFLinkLanes.reserve(8)` in constructor
- Expected: ~1-3% in `planMovements` (eliminates 100K+ vector copies/step)
- Test gate: Level 1 (`test_drive_items`), Level 2 (cf_*)

**PR 1.5: Cache `getCarFollowModel()` reference in `executeMove()`**
- Files: `MSVehicle.cpp:4574-4700`
- Capture `const MSCFModel& cfModel` once at function start
- Expected: ~0.5-1%
- Test gate: Level 2 (cf_*)

### Phase 2: Medium-Risk Structural (4 PRs)

**PR 2.1: SoA hot-data cache per lane**
- Files: `MSLane.h` (add `VehicleHotData` struct + `myHotData` vector), `MSLane.cpp:1562+`
- Extract pos/speed/posLat/lengthWithGap into contiguous 48-byte structs
- Populate at start of `planMovements()`, use for reads in inner loop
- Expected: 10-30% on large lanes (>10 vehicles), marginal on small lanes
- **Profile first** with `perf stat -e L1-dcache-load-misses` before implementing
- Test gate: Level 2 (all), Level 3 (highway_corridor)

**PR 2.2: Devirtualize Krauss CF model fast-path**
- Files: `MSCFModel.h`, `MSVehicleType.h`, `MSVehicle.cpp:2230`
- Type-tag check + `static_cast` for direct non-virtual call on Krauss (90%+ of vehicles)
- Expected: ~2-5% in Krauss-dominant scenarios
- Test gate: Level 1 (`test_cf_dispatch`), Level 2 (cf_krauss, cf_mixed)

**PR 2.3: Template-specialize `planMovements` on `gSemiImplicitEulerUpdate` x `gSublane`**
- Files: `MSLane.cpp`, `MSEdgeControl.cpp`
- 4 template instantiations, runtime dispatch at outer loop
- Expected: 3-8% (branch elimination + dead code removal)
- Test gate: Level 1 (`test_globals_policy`), Level 2 (all 4 flag combinations)

**PR 2.4: Enable parallel `changeLanes()`**
- Files: `MSEdgeControl.cpp:272-336`, `MSLaneChanger.cpp`, `MSLaneChangerSublane.cpp`
- Enable `PARALLEL_CHANGE_LANES` behind `gNumSimThreads > 1` runtime check
- Audit cross-edge thread safety
- Expected: Up to Nx speedup for changeLanes phase with N threads
- Test gate: Level 2 + Level 3 with `--threads 1,2,4,8`, compare FCD bit-exact

### Phase 3: High-Risk Architectural (3 PRs)

**PR 3.1: Work-stealing thread pool as default**
- Replace FOX round-robin assignment with `WorkStealingThreadPool`
- Expected: 10-30% better parallel scaling on heterogeneous networks

**PR 3.2: Batch CF computation for auto-vectorization**
- Add `batchFollowSpeed()` for lanes with uniform CF model
- Compile with `-mavx2 -mfma` for CF model source files
- Expected: 2-4x speedup for CF on long lanes

**PR 3.3: Dynamic micro-meso hybrid (design study first)**
- Lane-level fidelity switching with virtual vehicles at boundaries
- Expected: 5-10x for large sparse networks
- Start as design document + single-corridor prototype

---

## Sequencing & Dependencies

```
Phase 0:  PR 0.1 -> PR 0.2                    (benchmarking first)
          |
          v
          Generate test references (one-time)
          |
          v
Phase 1:  PR 1.1 | PR 1.2 | PR 1.3 | PR 1.4 | PR 1.5  (all independent)
          |
          v
Phase 2:  PR 2.1 | PR 2.2 | PR 2.3           (independent)
          PR 2.4 depends on Phase 0 parallel testing
          |
          v
Phase 3:  PR 3.1 <- PR 2.4
          PR 3.2 <- PR 2.2
          PR 3.3 <- all prior phases
```

## Estimated Impact

| Phase | Speedup | Confidence |
|-------|---------|-----------|
| Phase 1 (5 PRs) | 10-20% | High |
| Phase 2 (4 PRs) | 15-30% additional | Medium |
| Phase 3 (3 PRs) | 30-100% additional | Low (speculative) |
| **Compound (P1+P2)** | **25-45%** | **Medium-high** |

## Verification Protocol (Every PR)

1. Run Level 1 unit tests for the specific function modified
2. Run Level 2 component tests (all 10 scenarios)
3. Run Level 3 integration tests (all 4 scenarios)
4. Run Level 4 benchmark and compare against baseline CSV
5. Must pass ALL existing SUMO `ctest` tests
6. FCD diff must show 0 mismatches above 1.01% tolerance
