#!/usr/bin/env bash
#
# APKeep backend smoke + golden pin (integration tier).
#
# Builds the vendored APKeep (apkeep/ subtree) and runs it on its bundled
# Stanford dataset, then pins the set of detected forwarding loops against a
# committed golden. This is a CHARACTERIZATION test: it does not assert APKeep
# is "correct", it asserts our build of it still produces the exact loop set it
# produced when vendored -- so any later modification we make to APKeep (the
# planned embeddable API, the reachability solver hooks) that changes its core
# behavior is caught immediately. See APKEEP_BACKEND.md (P0).
#
# The loop set is order-independent (APKeep reports loops out of a HashSet), so
# we normalize to one sorted "prefix || path" record per loop before diffing.
# The timing/percentage stat line and the CLI banner are intentionally dropped.
#
# Usage:   bash fave/test/apkeep_smoke.sh
# Regen:   APKEEP_GOLDEN_REGEN=1 bash fave/test/apkeep_smoke.sh   (rewrites golden)
#
# Requires JDK 11 + Maven (APKeep's documented toolchain). Prefers an installed
# java-11 JDK if JAVA_HOME is unset.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
APKEEP_DIR="$ROOT/apkeep"
GOLDEN="$HERE/apkeep_stanford_loops.golden"

# Prefer a Java 11 JDK (APKeep's documented target) when JAVA_HOME is not set.
if [ -z "${JAVA_HOME:-}" ] && [ -d /usr/lib/jvm/java-11-openjdk-amd64 ]; then
    export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
fi

fail() { echo "APKeep smoke: $*" >&2; exit 1; }

command -v mvn >/dev/null 2>&1 || fail "mvn not found (need Maven + JDK 11)"
command -v java >/dev/null 2>&1 || fail "java not found (need JDK 11)"
[ -d "$APKEEP_DIR/networks/stanford" ] || fail "bundled networks/stanford missing in $APKEEP_DIR"

# 1. Build the fat jar.
echo "== apkeep: mvn package =="
( cd "$APKEEP_DIR" && mvn -q -B package ) || fail "build failed"
JAR="$APKEEP_DIR/target/apkeep-1.0.0.jar"
[ -f "$JAR" ] || fail "jar not produced: $JAR"

# 2. Run the bundled Stanford snapshot through the CLI (init -> update -> loops).
#    Run from $APKEEP_DIR so the relative snapshot path resolves.
echo "== apkeep: run bundled stanford =="
raw="$(cd "$APKEEP_DIR" && printf 'init networks/stanford\nupdate\ndump loops\nexit\n' \
        | timeout 600 java -jar "$JAR" 2>&1)"
rc=$?
[ $rc -eq 0 ] || { echo "$raw" | tail -20 >&2; fail "APKeep run exited $rc"; }

# 3. Normalize: one sorted "loop found for [...]: || <path>" record per loop.
normalized="$(printf '%s\n' "$raw" \
    | awk '/^loop found/{p=$0; getline q; gsub(/ +$/,"",q); print p" || "q}' \
    | sort)"

[ -n "$normalized" ] || { echo "$raw" | tail -20 >&2; fail "no loops parsed from output"; }

if [ "${APKEEP_GOLDEN_REGEN:-0}" = "1" ]; then
    printf '%s\n' "$normalized" > "$GOLDEN"
    echo "APKeep smoke: regenerated golden ($(wc -l < "$GOLDEN") loops): $GOLDEN"
    exit 0
fi

[ -f "$GOLDEN" ] || fail "golden missing: $GOLDEN (run with APKEEP_GOLDEN_REGEN=1 to create)"

# 4. Diff against the golden.
if diff -u "$GOLDEN" <(printf '%s\n' "$normalized"); then
    echo "APKeep smoke: OK ($(printf '%s\n' "$normalized" | wc -l) loops match golden)"
    exit 0
else
    fail "loop set diverged from golden (see diff above)"
fi
