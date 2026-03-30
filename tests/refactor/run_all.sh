#!/bin/bash
# Master test runner for SUMO refactoring tests.
# Runs all 4 test levels sequentially. Each level must pass before proceeding.
#
# Usage:
#   ./run_all.sh [--sumo-binary path]
#
# Levels:
#   1. Unit tests (placeholder - extend as needed)
#   2. Component tests (compare_all_components.py)
#   3. Integration tests (compare_all_integration.py)
#   4. Performance benchmark (benchmark.py)

set -e

# Parse arguments
SUMO_BINARY="sumo"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --sumo-binary)
            SUMO_BINARY="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--sumo-binary path]"
            echo ""
            echo "  --sumo-binary    Path to SUMO binary (default: sumo)"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            exit 1
            ;;
    esac
done

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================"
echo "SUMO Refactoring Test Suite"
echo "============================================================"
echo "  SUMO binary: ${SUMO_BINARY}"
echo "  Test dir:    ${SCRIPT_DIR}"
echo "  Date:        $(date)"
echo ""

# ---- Level 1: Unit tests ----
echo "============================================================"
echo "Level 1: Unit Tests"
echo "============================================================"
UNIT_DIR="${SCRIPT_DIR}/unit"
# Unit tests are compiled GTest binaries (built via CMake).
# Look for executables matching the test_refactor_* naming convention,
# first in CMAKE_BINARY_DIR/tests/refactor/unit, then in UNIT_DIR itself.
BUILD_UNIT_DIR="${SCRIPT_DIR}/../../build/tests/refactor/unit"
UNIT_FOUND=0
for search_dir in "${BUILD_UNIT_DIR}" "${UNIT_DIR}"; do
    if [ -d "${search_dir}" ]; then
        for test_bin in "${search_dir}"/test_refactor_*; do
            [ -x "${test_bin}" ] || continue
            echo "  Running: $(basename "${test_bin}")"
            "${test_bin}"
            UNIT_FOUND=1
        done
    fi
done
if [ "${UNIT_FOUND}" -eq 1 ]; then
    echo "Level 1: PASSED"
else
    echo "  No unit test binaries found (build with CMake + GTest first), skipping."
    echo "Level 1: SKIPPED"
fi
echo ""

# ---- Level 2: Component tests ----
echo "============================================================"
echo "Level 2: Component Tests"
echo "============================================================"
COMPONENT_DIR="${SCRIPT_DIR}/component"
if [ -d "${COMPONENT_DIR}" ]; then
    python3 "${SCRIPT_DIR}/compare_all_components.py" --sumo-binary "${SUMO_BINARY}" --base-dir "${SCRIPT_DIR}"
    echo "Level 2: PASSED"
else
    echo "  No component directory found, skipping."
    echo "Level 2: SKIPPED"
fi
echo ""

# ---- Level 3: Integration tests ----
echo "============================================================"
echo "Level 3: Integration Tests"
echo "============================================================"
INTEGRATION_DIR="${SCRIPT_DIR}/integration"
if [ -d "${INTEGRATION_DIR}" ]; then
    python3 "${SCRIPT_DIR}/compare_all_integration.py" --sumo-binary "${SUMO_BINARY}" --base-dir "${SCRIPT_DIR}"
    echo "Level 3: PASSED"
else
    echo "  No integration directory found, skipping."
    echo "Level 3: SKIPPED"
fi
echo ""

# ---- Level 4: Performance benchmark ----
echo "============================================================"
echo "Level 4: Performance Benchmark"
echo "============================================================"
python3 "${SCRIPT_DIR}/benchmark.py" \
    --sumo-binary "${SUMO_BINARY}" \
    --scenarios-dir "${SCRIPT_DIR}" \
    --output "${SCRIPT_DIR}/benchmark_results.csv"
echo "Level 4: COMPLETE"
echo ""

echo "============================================================"
echo "All levels completed successfully."
echo "============================================================"
