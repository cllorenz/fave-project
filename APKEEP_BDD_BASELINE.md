# FaVe/APKeep(BDD) — frozen baseline & reproduction record

**Status:** Part 1 preservation of `APKEEP_NDD_PLAN.md` (2026-08-18). This is the
"short RESULTS doc freezing the headline numbers" (Part 1.4), the maintenance /
backport policy (Part 1.5), and the index of the committed eval harness (Part 1.3).
It records the FaVe/APKeep backend in its **BDD** engine state — the published
*baseline* the later NDD engine is compared against, and the differential **oracle**
NDD must reproduce.

Owner: Claas Lorenz. Companions: [`APKEEP_NDD_PLAN.md`](APKEEP_NDD_PLAN.md),
[`APKEEP_TUM_UP_PLAN.md`](APKEEP_TUM_UP_PLAN.md), [`APKEEP_BACKEND.md`](APKEEP_BACKEND.md),
`apkeep/FAVE_CHANGES.md`.

---

## 1. What is frozen

- **Code baseline (BDD):** commit `bb840dea` (`FaVe/APKeep C1 Lever B: query-seed
  IPv6 sources instead of .sf elements`) — the last engine/adapter code change; the
  commits after it are docs + this preservation work.
- **Maintenance branch:** `apkeep` (living BDD version for backported bugfixes).
  Work continues on `ndd`.
- **Tag:** `fave-apkeep-bdd-v1` (annotated) marks this preservation commit — the
  frozen baseline + oracle. Tag name / branch policy are flagged as an owner
  decision in `APKEEP_NDD_PLAN.md`; the tag is trivially movable/renamable, and the
  `apkeep` maintenance branch can be advanced to (or cherry-pick) these preservation
  commits at the owner's discretion.

## 2. Environment provenance

The performance numbers are only reproducible on the toolchain they were measured
on; the 2026-08-17 container reset destroyed the previous one (removing Java,
bison/flex/m4, python3-dev and the scratchpad). Pinned/recorded in the `Dockerfile`
(Part 1.2). Re-measured on:

| component | version |
|---|---|
| base | ubuntu 24.04 |
| openjdk-11-jdk-headless | 11.0.31+11-1ubuntu1~24.04.2 |
| maven | 3.8.7-2 |
| bison / flex / m4 | 2:3.8.2 / 2.6.4 / 1.4.19 |
| python3-dev | 3.12.3 |
| JPype1 / pybison | 1.7.1 / 0.6.4 |
| vendored JDD | 111 (`apkeep/local-maven-repo/.../JDD-111.jar`) |

`m4` is load-bearing (bison invokes it at runtime; pybison segfaults without it)
and was **added** to the Dockerfile in this pass — its absence after the reset was a
silent failure mode.

## 3. Reproduction

From `fave/`, `PYTHONPATH=.`, venv active, APKeep jar built (`cd apkeep && mvn -q
package`).

- **Correctness — the whole committed baseline (Java core + wl_ifi/i2/stanford/tum
  differentials):**
  ```
  PYTHON=/path/to/.venv/bin/python bash test/exactness_gate.sh   # -> EXACTNESS GATE: PASS
  ```
- **Correctness — the wl_up flagship differential (this pass reconstructs it; the
  original scratchpad `up_diff.py` was destroyed by the reset):**
  ```
  PYTHONPATH=. python3 bench/wl_up/eval/apkeep_up_diff.py --save   # -> EXACT, 3660/3660
  ```
- **Timing — from-zero build curve (opt-in JSONL profiler):**
  ```
  APKEEP_BUILD_PROFILE=curve.jsonl PYTHONPATH=. \
      python3 bench/wl_up/eval/apkeep_up_diff.py
  ```
- **NDD GO/NO-GO — wl_up field-locality:**
  ```
  PYTHONPATH=. python3 bench/wl_up/eval/field_locality.py
  ```

## 4. Frozen headline numbers

### 4.1 Correctness — EXACT NetPlumber parity (deterministic)

Full 136-device wl_up model, from zero, through both backends; 137 sources × 137
probes = 18 769 ordered pairs.

| metric | value |
|---|---|
| over-approx (APKeep \ NP) | **0** |
| under-approx (NP \ APKeep) | **0** |
| reachable pairs (identical) | **3660 / 3660** meaningful |

The APKeep and NetPlumber matrices are **byte-identical**. The raw matrices hold
3661 reachable pairs; the headline **3660** excludes the single host-to-self pair
(`source.clients.wifi.uni-potsdam.de -> probe.clients.wifi...`, `base(src)==base(probe)`),
matching the Phase D convention (a host reaching "itself" is not a compliance
question). Self-exclusion cannot change over/under (both backends agree on it), so
the EXACT verdict is convention-independent.

Also green: the exactness gate (Java core 29 tests + wl_ifi/wl_i2/wl_stanford/wl_tum
differentials, `FAVE_REQUIRE_BACKENDS=1`).

Golden matrices committed: `bench/wl_up/eval/mat_apk.json`, `mat_np.json` (complete,
self-pairs included).

### 4.2 Timing — from-zero build (JVM-warm, this env)

| metric | prior env (Phase C3/D, 2026-08-17) | this env (re-measured 2026-08-18) |
|---|---|---|
| APKeep from-zero build (`net.run`) | ~692 s (~11.5 min) | **680–748 s** (2 runs; ~11.3–12.5 min) |
| APKeep build + full query (subprocess wall, incl. JVM cold+JIT) | ~851 s | **1079 s** |
| NetPlumber build + full query (wall) | ~49 s | **44 s** |
| APKeep / NetPlumber wall ratio | ~17× | **24.5×** |
| final `ap_num` | 14 561 | **14 561** (exact) |
| elements | 543 | **543** (exact) |
| PPM share of build | ~92 % | **96 %** (encode 0.7 s, insert 22.7 s, merge 6.9 s) |

Structure reproduces exactly (`ap_num` 14 561, elements 543, PPM-dominated); the
absolute build wall shows ~10 % run-to-run variance (JVM/GC on a BDD-heavy workload:
680 s then 748 s) and this env's build is modestly slower than the prior one — the
expected "a different Java build can shift timings" the plan flagged, which is why
timing is context, not a correctness gate. The residual cost is the dst-prefix ×
proto/port cross-product in APKeep's single global AP partition (~29× sizing,
`APKEEP_TUM_UP_PLAN.md` Phase E) — the term NDD targets. Curve:
`bench/wl_up/eval/up_build.jsonl` (51 samples).

### 4.3 NDD GO/NO-GO — wl_up field-locality (§2.0)

Distribution of *constrained BDD header fields* per emitted rule, full model (6560
rules; in/out-port anti-spoofing is modelled structurally, not as a BDD field, so it
is correctly excluded from this count):

| constrained fields | share |
|---|---|
| 0 | 4.1 % |
| 1 | 11.0 % |
| 2 | 24.1 % |
| 3 | 31.4 % |
| 4 | 20.1 % |
| 5 | 9.3 % |
| **≤2 (orthogonal)** | **39.2 %** |
| **≥4 (many-field)** | **29.4 %** |
| src ∧ dst (both 128-bit IPv6) | 33.5 % |

Per-field usage: proto 67.9 %, dst 63.5 %, src 60.9 %, related 47.7 %, dport 20.4 %,
sport 19.9 %. Machine-readable: `bench/wl_up/eval/field_locality.json`.

**Verdict — MIXED / CAUTION, not the clean GO the plan's bar wants.** The plan's
decision rule (§2.0): *mostly 1–2 fields ⇒ strong NDD case; many 4–5-field rules ⇒
the paper's §6.6 degradation regime ⇒ reconsider before investing.* wl_up is a
**stateful multi-field firewall**: the modal rule constrains **3** fields, only
39.2 % are ≤2, and 29.4 % span ≥4 — nearer §6.6 than the orthogonal Stanford/I2 case,
consistent with the plan's own ~29× sizing (well above Purdue's 3×).

**But two facts pull the other way and matter for the call:**
1. The two heaviest fields are the **128-bit IPv6 src/dst** — exactly what NDD
   collapses to one variable each, removing the bit-recursion tax the plan flags as
   *worse* for us than for the IPv4 paper. A 4-field rule here is typically "two big
   IPv6 fields + two tiny fields (proto 1B, related 1b)", so per-field atomization
   still wins big on the dominant fields even when field-count is high.
2. The specific rules the plan feared ("anti-spoof src+dst+in/out-port") are only
   **2 BDD fields** here (src+dst); the port is structural. The real many-field
   population is the **service/stateful filter** rules (proto+src+dst+ports+related).

**Recommendation:** this is a genuine owner GO/NO-GO decision, not an automatic one.
It is the natural checkpoint before §2.1 (NDD library trust / test coverage) — see
`APKEEP_NDD_PLAN.md` refined-sequence step 3.

## 5. Committed eval artifacts (`fave/bench/wl_up/eval/`)

| file | what |
|---|---|
| `apkeep_up_diff.py` | wl_up APKeep-vs-NP full-matrix differential (reconstructed `up_diff.py`) |
| `field_locality.py` | §2.0 GO/NO-GO field-locality measurement |
| `field_locality.json` | frozen §2.0 result |
| `mat_apk.json` / `mat_np.json` | golden reachability matrices (the NDD oracle) |
| `up_build.jsonl` | from-zero build curve (profiler JSONL) |

Scratchpad is never again a preservation location (Part 1.3): all of the above live
in-repo.

## 6. Maintenance model — one shared adapter, two engines (Part 1.5)

The FaVe Python **adapter** (`fave/apkeep/adapter.py`) is backend-agnostic: it emits
APKeep rule strings (`+ fwd/filter/acl/nat ...`) and topology edges from a FaVe model
and drives reachability queries. The **Java engine** (`apkeep/`) is what diverges
between BDD (today) and NDD (planned). Structure:

- **One shared adapter, two engines (BDD, NDD).**
- **Modeling bugfixes** (rule encoding, element wiring, query seeding) land in the
  adapter and/or the shared Java classes and benefit **both** engines — these are the
  "backport" candidates onto the `apkeep` maintenance branch.
- **Engine fixes** (BDD-specific AP maintenance vs NDD's native atomize/update) are
  **branch-scoped** and do not backport.
- Every vendored-subtree (`apkeep/`, later `NDD/`) edit is a separate commit with a
  `FAVE_CHANGES`-style changelog entry (vendoring hygiene).

"Backport" therefore has a defined meaning: an adapter/shared-Java fix on `ndd` (or a
future NDD branch) is cherry-picked onto `apkeep`; an engine-internal fix is not.
