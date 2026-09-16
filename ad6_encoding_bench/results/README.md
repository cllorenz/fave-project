# Re-run logs

Raw stdout of the Axis 6 / 6b / 7 re-runs of 2026-09-16 (`AD6_ENCODING_PLAN.md` §3.9a),
kept because those axes' published numbers (§3.7/§3.8/§3.9) were measured with the
stateful queries accidentally solved **unconditioned** — `cchecks.json`'s `cond` strings
never reached the solver — and a reader comparing the two tables should be able to see
the actual output rather than take the write-up's word for it.

- `2026-09-16_axis6_rerun.log`  — `axis6_wlup_real.py 50 50`
- `2026-09-16_axis6b_rerun.log` — `axis6b_wlup_full_scale.py 300`
- `2026-09-16_axis7_rerun.log`  — `axis7_native_incremental.py 300`
- `2026-09-16_cond_ab.log`      — the A/B that shows the condition now bites: same 50
  stateful queries, ad6-real both times, cond applied vs cond stripped. 25 of 50 answers
  differ; every `related:0` query goes reachable → unreachable.

Environment: rebuilt sandbox, `z3-solver` 5.1.0 (the version behind the original numbers
was never recorded), `minisat`/`clasp` present, `cadical`/`cryptominisat5` absent. Absolute
times are therefore not comparable with the published ones; each run's internal ratios are.
