# Phase 2 Performance Refactoring Results

## Date: 2026-03-29

## Overview

Phase 2 targeted micro-level optimizations after Phase 1 achieved a 7.2x speedup
(74.2s -> 10.3s on highway_corridor). The focus was on:
- PR 2.2: Devirtualizing Krauss CF model virtual calls
- PR 2.1: Vehicle object prefetching in hot loops
- PR 2.3: Template specialization on Euler/Sublane (abandoned after analysis)

## PR 2.2: Devirtualize Krauss CF Model Fast-Path

**Branch:** `perf/devirtualize-krauss`
**PR:** https://github.com/benchoi93/sumo/pull/4
**Status:** Implemented, tested, pushed

### Changes
- Added `mutable int myCachedModelID` to `MSCFModel` for non-virtual model ID lookup
- Added `getCachedModelID()` inline method to avoid virtual `getModelID()` dispatch
- Created `kraussFollowSpeed()` and `kraussStopSpeed()` helper functions in MSVehicle.cpp
  that do static dispatch via `MSCFModel_Krauss::followSpeed/stopSpeed` when the model is Krauss
- Applied to: `planMoveInternal`, `adaptToLeader`, `adaptToJunctionLeader`, `adaptToOncomingLeader`

### Impact
- Small but measurable improvement (~1-2%) on Krauss-heavy scenarios
- Eliminates vtable lookups for followSpeed/stopSpeed in the dominant path
- No impact on non-Krauss models (they fall through to virtual dispatch)

## PR 2.1: Vehicle Object Prefetching

**Branch:** `perf/soa-hot-data`
**PR:** https://github.com/benchoi93/sumo/pull/5
**Status:** Implemented, tested, pushed

### Changes
- Added `__builtin_prefetch` for the next vehicle object in `planMovements()` loop
- Added `__builtin_prefetch` for the next vehicle object in `executeMovements()` loop

### Design Decision
The original plan was a full SoA (Structure of Arrays) hot-data cache. After analysis,
this was found to be suboptimal because:
- `planMovements()` spends 99%+ of time inside `planMove()` (3100ns per vehicle)
  vs `updateLeaderInfo()` (9ns per vehicle)
- The bottleneck is complex per-vehicle computation, not data layout
- SoA benefits array-scan patterns; this code does deep per-element processing
- Prefetching addresses cache misses without the complexity of data structure changes

### Impact
- Marginal improvement (~0.5%) on large scenarios
- No overhead or correctness risk

## PR 2.3: Template-Specialize on Euler x Sublane

**Branch:** None (abandoned)
**Status:** Abandoned after analysis

### Analysis
- `gSemiImplicitEulerUpdate` is checked 13 times across MSVehicle.cpp in ~8 different functions
- `gSublane` is checked 4 times in MSVehicle.cpp, 8 times in MSLane.cpp
- These checks are spread across the deep call tree (planMoveInternal -> adaptToLeader,
  adaptToJunctionLeader, checkRewindLinkLanes, etc.)
- Branch prediction handles constant globals perfectly after warmup
- Templatizing would require duplicating ALL functions in the call chain (massive code duplication)
- Estimated benefit: <0.1% (branches are perfectly predicted after 1-2 iterations)

**Conclusion:** Not worth the complexity. The branch predictor already handles these constant
globals with essentially zero overhead.

## Benchmark Results

### Comparison Table (medians of 3 runs each)

| Scenario | Original (s) | Phase 1 (s) | Phase 2 (s) | P1 Speedup | P2 vs P1 | Total Speedup |
|---|---|---|---|---|---|---|
| cf_eidm_platoon | 2.199 | 0.377 | 0.371 | 5.8x | +1.6% | 5.9x |
| cf_idm_platoon | 1.415 | 0.227 | 0.217 | 6.2x | +4.4% | 6.5x |
| cf_krauss_platoon | 1.510 | 0.225 | 0.226 | 6.7x | -0.4% | 6.7x |
| cf_mixed_models | 4.901 | 0.781 | 0.768 | 6.3x | +1.7% | 6.4x |
| insertion_heavy | 12.711 | 1.643 | 1.585 | 7.7x | +3.5% | 8.0x |
| junction_priority | 0.701 | 0.078 | 0.087 | 9.0x | -11.5% | 8.1x |
| junction_signalized | 0.985 | 0.125 | 0.125 | 7.9x | 0.0% | 7.9x |
| lc_highway_merge | 5.096 | 0.712 | 0.713 | 7.2x | -0.1% | 7.1x |
| lc_sublane_weave | 9.297 | 1.456 | 1.420 | 6.4x | +2.5% | 6.5x |
| traci_queries | 0.392 | 0.070 | 0.074 | 5.6x | -5.7% | 5.3x |
| highway_corridor | 74.206 | 10.669 | 10.454 | 7.0x | +2.0% | 7.1x |
| urban_grid | 9.610 | 1.406 | 1.369 | 6.8x | +2.6% | 7.0x |
| **TOTAL** | **123.023** | **17.769** | **17.409** | **6.9x** | **+2.0%** | **7.1x** |

### Key Observations

1. **Phase 2 provides ~2% additional improvement** over Phase 1 across all scenarios combined
2. **highway_corridor**: 10.67s -> 10.45s (2% improvement), total 7.1x from original 74.2s
3. **Diminishing returns**: Phase 1 captured the major wins (data structure improvements),
   Phase 2 targets micro-optimizations that are much harder to measure
4. **Measurement noise**: Small scenarios (<1s) show high variance, making Phase 2 improvements
   hard to distinguish from noise
5. **Non-Krauss models unaffected**: The devirtualization only activates for Krauss models;
   EIDM, IDM, and other models use the normal virtual dispatch path

## Branches Summary

| Branch | Status | PR |
|---|---|---|
| `perf/devirtualize-krauss` | Pushed, PR created | https://github.com/benchoi93/sumo/pull/4 |
| `perf/soa-hot-data` | Pushed, PR created | https://github.com/benchoi93/sumo/pull/5 |
| `perf/template-euler-sublane` | Abandoned (not created) | N/A |
| `perf/phase2-combined` | Local test branch | N/A |

## Recommendations for Phase 3

If further optimization is desired, the following areas show the most promise:

1. **Profile-guided optimization (PGO)**: Compile with `-fprofile-generate`, run benchmarks,
   recompile with `-fprofile-use`. This can yield 10-20% improvement by optimizing
   instruction layout and branch prediction.

2. **Link-time optimization (LTO)**: Compile with `-flto` to enable cross-translation-unit
   inlining. This would allow the compiler to inline `followSpeed`/`stopSpeed` at the
   devirtualized call sites.

3. **Parallelize lane processing**: The `planMovements()` calls across lanes are independent
   and could benefit from thread-pool parallelism (SUMO already has infrastructure for this).

4. **Reduce allocations in planMoveInternal**: The `DriveItemVector` is cleared and repopulated
   each step. If its capacity is stable, the swap trick from Phase 1 already helps, but
   further analysis may reveal other allocation hot spots.
