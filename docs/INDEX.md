# Document index

Twenty-one reference documents, ~23,500 lines. They are lab notebooks, not
specifications: each records what was tried, what it cost, what was measured and
what the owner decided, usually with a dated status header at the top. **Read the
status header before the body** — several of these describe work that is finished,
and are kept because results and source comments cite them.

Two documents live at the repository root instead, because that is where a reader
looks for them first: [`../README.md`](../README.md) (what FaVe is, how to build and run it)
and [`../TODO.md`](../TODO.md) (the live QA backlog, 3,081 lines, the most-churned file here).

Measurement **results** are not in this directory. They live beside the artifacts
that produced them, under [`../fave/bench/campaigns/`](../fave/bench/campaigns/)
(start at `RESULTS.md`) and `../fave/bench/deltanet/eval/`.

## Start here

| document | lines | what it is |
|---|---:|---|
| [`MEASUREMENT_RUN_PLAN.md`](MEASUREMENT_RUN_PLAN.md) | 986 | **The run book.** The measurements that are open and worth running, ordered so a session with no prior context can execute it top to bottom, unattended. Start here to run something. |
| [`ACCOMMODATIONS.md`](ACCOMMODATIONS.md) | 136 | **The accommodation registry.** Every way a tool was helped to run the suite, or a workload changed for it — what was done, what it costs, the evidence it is right. The write-up cites this for all of them. |
| [`CONVENTIONS.md`](CONVENTIONS.md) | 87 | How result directories and per-cell artifacts are named, what a run directory must carry, and why a committed result directory is never renamed. Read before starting a run. |
| [`INCREMENTAL_PLAN.md`](INCREMENTAL_PLAN.md) | 362 | **The incremental axis (TODO item 31), PLAN.** Making updates work end to end — engines that report what a change affected, FaVe re-verifying only those checks — and measuring it. The owner's decisions of 2026-10-09 are its §4; open questions its §9. |

## The verification backends — one document per engine family

FaVe compares six engine configurations. NetPlumber (C++/HSA) is the reference and
has no design document of its own; the other three families each have one.

| document | lines | status |
|---|---:|---|
| [`APKEEP_BACKEND.md`](APKEEP_BACKEND.md) | 1,859 | **INTEGRATED.** Atomic-predicate verifier, two engines (BDD and NDD) behind one adapter. Faithful-VLAN model is the default. No open defect in §10. |
| [`AD6_PLAN.md`](AD6_PLAN.md) | 7,671 | **Built.** A generic SAT/QBF model checker as a backend, first-party. The largest document here — use its section numbers, which source comments cite directly. |
| [`VERIFLOW_PLAN.md`](VERIFLOW_PLAN.md) | 1,121 | **V1–V4 done.** VeriFlow-FR, an *independent reimplementation* — explicitly not "VeriFlow", and no result from it is reported as VeriFlow's (§9, D2). |

## APKeep in depth

Read `APKEEP_BACKEND.md` first; these are the sub-tracks it refers to.

| document | lines | status |
|---|---:|---|
| [`APKEEP_NDD_PLAN.md`](APKEEP_NDD_PLAN.md) | 272 | The plan to preserve the BDD state and integrate NDD. Largely executed; the running record is the eval log below. |
| [`APKEEP_NDD_EVAL.md`](APKEEP_NDD_EVAL.md) | 801 | The NDD integration's running evaluation log. |
| [`APKEEP_BDD_BASELINE.md`](APKEEP_BDD_BASELINE.md) | 255 | The **frozen** BDD baseline — the published comparand and the differential oracle NDD must reproduce. |
| [`BDD_MEASUREMENT_PLAN.md`](BDD_MEASUREMENT_PLAN.md) | 215 | The 56 h BDD campaign, written after a use-after-free invalidated the BDD half of the engine comparison. |
| [`APKEEP_FAITHFUL_PLAN.md`](APKEEP_FAITHFUL_PLAN.md) | 226 | The soundness track: eliminating APKeep's reachability over-approximation on `wl_stanford`. |
| [`APKEEP_STANFORD_NP_SPEC.md`](APKEEP_STANFORD_NP_SPEC.md) | 470 | The gate result that found the mechanism behind that over-approximation — and overturned the prior hypothesis. |
| [`APKEEP_TUM_UP_PLAN.md`](APKEEP_TUM_UP_PLAN.md) | 779 | Bringing `wl_tum` (stateful IPv4) and `wl_up` (IPv6 campus) onto APKeep. |
| [`NDD_FIELD_UNIFICATION_PLAN.md`](NDD_FIELD_UNIFICATION_PLAN.md) | 216 | Steps 1–4 done. Written after the fourth slot-drop defect of the same shape: a header field must be remembered in five places. |

## ad6 in depth

| document | lines | status |
|---|---:|---|
| [`AD6_ENCODING_PLAN.md`](AD6_ENCODING_PLAN.md) | 1,111 | Encoding and solver architecture, run as a parallel track. Core investigation done; the incremental lever is closed out and in production. |

## Modelling semantics

Cross-backend questions about what FaVe's model *means*, as opposed to how one
engine implements it.

| document | lines | status |
|---|---:|---|
| [`TABLE_SEMANTICS_PLAN.md`](TABLE_SEMANTICS_PLAN.md) | 1,039 | **Built.** Making FaVe's implicit first-match contract explicit, so the declaration reaches the engines. |
| [`OUT_STAGE_PLAN.md`](OUT_STAGE_PLAN.md) | 766 | **Steps 0–5 done.** The `wl_stanford` out stage as a modelled device. Read its §3 first — the oracle it asked for showed no reachability question can observe the gap. |

## Workloads

| document | lines | status |
|---|---:|---|
| [`CLOUD_BENCH_PLAN.md`](CLOUD_BENCH_PLAN.md) | 4,478 | Extending the suite with the NoD cloud dataset (`wl_cloud`) and the Delta-net traces. Built and running; also the record of three engine defects it found. |

## Testing strategy — one per language, non-overlapping

| document | lines | scope |
|---|---:|---|
| [`TESTING_STRATEGY_PYTHON.md`](TESTING_STRATEGY_PYTHON.md) | 285 | `fave/` and `policy_translator/` |
| [`TESTING_STRATEGY_CXX.md`](TESTING_STRATEGY_CXX.md) | 289 | `net_plumber/` only |
| [`TESTING_STRATEGY_JAVA.md`](TESTING_STRATEGY_JAVA.md) | 166 | the vendored APKeep fork under `apkeep/` — the engine, not FaVe's adapter |

---

**Citations.** Source comments throughout the repository cite these documents by
bare name and section — `(AD6_PLAN.md §5.5)`, `(TABLE_SEMANTICS_PLAN.md S1+S2)`.
Those citations do not carry paths, so they stay valid wherever the file lives;
`grep -rn 'AD6_PLAN.md' .` finds every one. The same names also appear inside
`results_*/` artifacts, which are measurement evidence and are never rewritten.
