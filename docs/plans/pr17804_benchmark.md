# PR 17804 Benchmark Results

## Machine
- AMD EPYC 7643 48-Core Processor (2 sockets, 96 physical cores)
- Linux 5.15.0-151-generic x86_64
- GCC 11.4.0, Release build

## Scenarios (from SUMO maintainer)

### Scenario A: City (10x10 grid, 2 lanes, actuated TLS)
```
netgenerate -g --grid.number 10 -L 2 --turn-lanes 2 --no-turnarounds --grid.length 400 -j traffic_light --tls.default-type actuated
randomTrips.py -n net.net.xml -p 0.3 -r routes.rou.xml --random-routing-factor 2
```

### Scenario B: Motorway (20-segment, 3 lanes)
```
netgenerate -g --grid.y-number 1 --grid.x-number 20 -L 3 --no-turnarounds --bidi-probability 0 --grid.length 1000
randomTrips.py -n net.net.xml --min-distance 1e4 -p 0.3 -r routes.rou.xml
sumo --default.departspeed avg --default.departlane free --max-depart-delay 5
```

## Results (3 runs each, seconds)

| Scenario | v1.26.0 (original) | PR 17804 (patched) | Difference |
|----------|-------------------|-------------------|------------|
| A: City run1 | 26.64 | 26.89 | +0.9% |
| A: City run2 | 26.90 | 26.78 | -0.4% |
| A: City run3 | 27.28 | 27.16 | -0.4% |
| **A median** | **26.90** | **26.89** | **~0%** |
| B: Motorway run1 | 24.98 | 24.81 | -0.7% |
| B: Motorway run2 | 24.86 | 24.76 | -0.4% |
| B: Motorway run3 | 25.55 | 24.70 | -3.3% |
| **B median** | **24.98** | **24.76** | **-0.9%** |

## Conclusion

**No measurable speedup** — differences are within measurement noise (~1%).

The `std::list` → `std::vector` change for `myActiveLanes` does not improve simulation performance because:
1. Active lane counts are small (~100-500 lanes) — iteration overhead is negligible vs per-lane computation
2. The `erase-in-loop` pattern on `std::list` is not a bottleneck when lane counts are small
3. The compaction pattern on `std::vector` has similar cost for small N

The change is architecturally cleaner (contiguous memory, no heap nodes) but does not deliver measurable wall-clock improvement on realistic scenarios.

## Maintainer Results (for comparison)

| Scenario | Machine | v1.26.0 | PR 17804 |
|----------|---------|---------|----------|
| A: City | Linux Intel i9 | 17.4s | 17.1s |
| A: City | Win11 Intel i7 | 48.3s | 49.2s |
| B: Motorway | Linux Intel i9 | 12.4s | 12.3s |
| B: Motorway | Win11 Intel i7 | 39.2s | 39.8s |

Consistent with our findings — no meaningful difference.
