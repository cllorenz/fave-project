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
# Kept as its own script, rather than inlined in test.sh, for the same reason
# apkeep_smoke.sh is: the tests that CONSUME this jar currently live in the
# `fast` tier, whose environment deliberately has no JDK/Maven at all (see
# .github/actions/setup-fave-native's own note -- pybison and JPype1 are
# integration-only and stay out of requirements.txt so `fast` remains pure
# Python). So `integration` is the only tier that can build it, and anyone who
# wants those tests to actually run rather than skip needs to be able to invoke
# this one step on its own.
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
