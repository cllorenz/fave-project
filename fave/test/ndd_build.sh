#!/usr/bin/env bash
#
# Build the NDD fat jar (ndd/ subtree) -- the artifact fave/apkeep/lib_ndd.py
# drives in-process via JPype.
#
# Invocation mirrors lib_ndd.py's own documented one
# (`mvn -f ndd/pom.xml -DskipTests package`); -DskipTests keeps this to the
# packaging step, since NDD's own Java test suite is not what this project
# gates on -- the Python-side differential tests are (test_apkeep_ndd_fwd.py,
# test_apkeep_ndd_wlup.py).
#
# Kept as its own script, rather than inlined in test.sh, for the same reasons
# apkeep_smoke.sh is: it pins JAVA_HOME to java-11 so both backend jars come from
# one toolchain, guards mvn/java/pom up front with a readable message rather than a
# raw Maven error, asserts the jar actually appeared (`mvn -q` can exit 0 having
# produced nothing usable), and stays separately invocable for rebuilding just this
# jar.
#
# Its consumers (test_apkeep_ndd_fwd.py, test_apkeep_ndd_wlup.py) run in the
# `integration` tier, in their own pytest process -- see FAVE_NDD_TESTS in test.sh
# for why they need a fresh JVM. They used to sit in the `fast` tier, whose
# environment deliberately has no JDK/Maven/JPype at all, which is why this script
# exists as the one place the jar can come from in a clean checkout.
#
# Usage:    bash fave/test/ndd_build.sh
# Requires: JDK 11 + Maven (same toolchain as apkeep_smoke.sh).

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
POM="$ROOT/ndd/pom.xml"
JAR="$ROOT/ndd/target/ndd-1.0.1-jar-with-dependencies.jar"

# Prefer a Java 11 JDK when JAVA_HOME is not set -- same convention as
# apkeep_smoke.sh, so both jars are built against the same toolchain.
if [ -z "${JAVA_HOME:-}" ] && [ -d /usr/lib/jvm/java-11-openjdk-amd64 ]; then
    export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
fi

fail() { echo "NDD build: $*" >&2; exit 1; }

command -v mvn >/dev/null 2>&1 || fail "mvn not found (need Maven + JDK 11)"
command -v java >/dev/null 2>&1 || fail "java not found (need JDK 11)"
[ -f "$POM" ] || fail "pom not found: $POM"

echo "== ndd: mvn package =="
( cd "$ROOT" && mvn -q -B -f "$POM" -DskipTests package ) || fail "build failed"
[ -f "$JAR" ] || fail "jar not produced: $JAR"

echo "NDD build: OK ($JAR)"
