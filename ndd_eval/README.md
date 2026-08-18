# NDD library trust — §2.1 evaluation (staging)

This directory stages the NDD-library **trust** work from `APKEEP_NDD_PLAN.md` §2.1,
*before* the NDD library is vendored (§2.4). Once `XJTU-NetVerify/NDD` is vendored
into the FaVe tree, `NDDIPv6DifferentialTest.java` moves into its
`src/test/java/org/ants/jndd/diagram/` and runs as part of that module's `mvn test`.

## What this is

`NDDIPv6DifferentialTest.java` — a differential-vs-BDD trust suite for the NDD
library on **FaVe's own header profile**: two 128-bit IPv6 address fields (src, dst)
plus small transport fields. The NDD paper's own tests use the IPv4 5-tuple; this
targets the 128-bit fields the FaVe/APKeep fork depends on (the plan's "`createVar`
at 128 bits is exactly where research code breaks" risk).

**Oracle.** Each NDD boolean op is checked to commute with the `toBDD` homomorphism
— `toBDD(op_NDD(P,Q)) == op_BDD(toBDD(P), toBDD(Q))` — using the same JDD engine NDD
runs on (`NDD.getBDDEngine()`). JDD BDDs are canonical, so equal node ids ⇔ equal
packet sets: an EXACT set-equality oracle that never rounds (unlike `satCount` over a
2^280 space). `exist` is checked with layout-independent algebraic identities instead
(NDD fields share a BDD variable template, so a `getBDDVars`-built cube is not in the
`toBDD` variable space — see the test's comments).

## Reproduce

```
git clone --depth 1 https://github.com/XJTU-NetVerify/NDD.git
cp NDDIPv6DifferentialTest.java NDD/src/test/java/org/ants/jndd/diagram/
cd NDD
JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64 mvn -q -B -Dtest=NDDIPv6DifferentialTest test
```

Upstream imported commit and full findings: `../APKEEP_NDD_EVAL.md`.
