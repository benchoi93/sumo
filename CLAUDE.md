# SUMO Performance Refactoring Project

## Project Goal

Refactor the SUMO traffic microsimulator for significantly improved runtime performance while maintaining behavioral correctness. Reference implementation: [NextSim](https://github.com/AIxMobility/NextSim.git) for architectural inspiration.

## Architecture Overview

### Core Simulation Loop (`src/microsim/MSNet.cpp:simulationStep()`)
1. TraCI command processing
2. Traffic light updates
3. **HOT PATH**: `MSEdgeControl::planMovements()` → `MSLane::planMovements()` → `MSVehicle::planMove()`
4. **HOT PATH**: `MSEdgeControl::executeMovements()`
5. **HOT PATH**: `MSEdgeControl::changeLanes()`
6. Vehicle insertion
7. Output/events

### Key Performance Bottlenecks (Priority Order)

| # | Bottleneck | Location | Impact |
|---|-----------|----------|--------|
| 1 | **String-keyed `std::map`** for edges/vehicles | `MSEdge.h:1035`, `MSVehicleControl.h:74` | O(log n) every lookup |
| 2 | **Virtual dispatch in hot loops** | CF models (`MSCFModel::followSpeed/freeSpeed`), LC models | Per-vehicle per-step overhead |
| 3 | **AoS layout** — vehicle pointers scattered in heap | `MSLane.h:1486` (`std::vector<MSVehicle*>`) | Cache misses on sequential access |
| 4 | **Deep inheritance** (4 levels) | `SUMOTrafficObject→SUMOVehicle→MSBaseVehicle→MSVehicle` | vtable indirection, bloated objects |
| 5 | **Single-threaded by default** | `MSEdgeControl.cpp` | No CPU core utilization |
| 6 | **40+ global statics** checked in hot paths | `MSGlobals.h:46-190` | Branch prediction pollution |
| 7 | **Per-timestep allocations** | `MSLeaderInfo`, iterator temps | GC pressure, fragmentation |

### Critical Files
- `src/microsim/MSNet.cpp` — simulation loop coordinator
- `src/microsim/MSEdgeControl.cpp` — movement orchestration & threading
- `src/microsim/MSLane.cpp` — per-lane vehicle iteration (planMovements, executeMovements)
- `src/microsim/MSVehicle.cpp` — vehicle dynamics (planMove, executeMove)
- `src/microsim/MSEdge.h` — edge data structures & caches
- `src/microsim/MSGlobals.h` — global configuration statics
- `src/microsim/cfmodels/` — 16 car-following model implementations
- `src/microsim/lcmodels/` — 4 lane-change model implementations

### NextSim Design Patterns Worth Adopting
- **Integer-keyed `unordered_map`** instead of string-keyed `std::map` (NextSim's `UnitIdentifierMap`)
- **Hybrid meso-micro** with virtual vehicles for dynamic fidelity (NextSim's `UniformLink`)
- **OpenMP parallelism** at link/lane granularity
- **Custom lightweight smart pointers** with atomic refcounting
- **State-machine lane changing** (BLC→DLC→ALC) vs SUMO's monolithic LC call

## Build & Test

```bash
# Build
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)

# Run tests
cd build && ctest --output-on-failure

# Run a basic simulation for benchmarking
./bin/sumo -c tests/complex/tutorial/quickstart/data/quickstart.sumocfg
```

## Refactoring Rules

1. **Never break behavioral correctness** — every refactor must pass existing tests
2. **Benchmark before and after** — use `quickstart.sumocfg` and larger scenarios with `--duration-log`
3. **One bottleneck per PR** — atomic, reviewable changes
4. **Profile first** — use `perf record` / `perf stat` / `valgrind --tool=callgrind` before optimizing
5. **Hot path focus** — only optimize code called per-vehicle per-timestep
6. **Maintain API compatibility** — TraCI and libsumo interfaces must not break
7. **C++17 features welcome** — `std::optional`, `if constexpr`, structured bindings, `std::variant`
8. **Test with multiple CF/LC models** — Krauss (default), IDM, EIDM, LC2013, SL2015

## Coding Conventions (SUMO-specific)

- Class prefix: `MS` (microsim), `MSCF` (car-following), `MSLCM` (lane-change)
- Container typedef pattern: `typedef std::vector<MSVehicle*> VehCont`
- Named object containers: `NamedObjectCont<T*>` with string-keyed maps
- Build with CMake, minimum 3.5, C++17 for GCC/Clang
- FOX toolkit for GUI (optional dependency)

## Performance Measurement

```bash
# CPU profiling
perf stat ./bin/sumo -c scenario.sumocfg
perf record -g ./bin/sumo -c scenario.sumocfg && perf report

# Cache analysis
perf stat -e cache-references,cache-misses,L1-dcache-load-misses ./bin/sumo -c scenario.sumocfg

# Callgrind for detailed hotspot analysis
valgrind --tool=callgrind ./bin/sumo -c scenario.sumocfg
kcachegrind callgrind.out.*
```
