#!/bin/bash
# Builds the in-tree solvers/checkers and copies the cadical binary into solvers/.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"

log() { echo -e "\n=== $1 ===\n"; }

build_minisat_variant() {
    local dir="$1"
    log "Building $dir"
    make -C "$ROOT_DIR/$dir" -j"$JOBS"
}

log "Building simple_CAR"
make -C "$ROOT_DIR/simple_CAR" -j"$JOBS"

build_minisat_variant "minisat_proof"
build_minisat_variant "minisat_absorption_checker"
build_minisat_variant "minisat"

log "Building External/kissat_bve"
(
    cd "$ROOT_DIR/External/kissat_bve"
    ./configure
    make -C build -j"$JOBS"
)

log "Building External/glucose"
(
    cd "$ROOT_DIR/External/glucose/simp"
    make -j"$JOBS"
)

log "Building External/cadical (rel-2.1.3)"
(
    cd "$ROOT_DIR/External/cadical"
    ./configure
    make -C build -j"$JOBS"
)

log "Copying cadical binary to solvers/"
mkdir -p "$ROOT_DIR/solvers"
cp "$ROOT_DIR/External/cadical/build/cadical" "$ROOT_DIR/solvers/cadical"

log "Done"
