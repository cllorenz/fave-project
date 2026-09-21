# wl_cloud — the NoD cloud workload, gated on third-party verdicts

Full background: `CLOUD_BENCH_PLAN.md` §1. This file covers only what the two
hand-written inputs in this directory mean, because they are the one part of
the workload that is *not* derived from the raw data.

## What is derived and what is not

Everything under `cloud-tf/` is vendored raw data, checked against `SHA256SUMS`
before anything reads it. From it, on **every** run:

| artifact | derived by |
|---|---|
| `oracle.json` | `cloud_oracle.py`, out of the six `.smt2` instances |
| `topology/routes/sources/policies.json` | `cloud_preparation.py`, out of `network.tf` |
| `reachability.csv`, `roles.json` | `policy_translator`, out of the two files below |
| `checks.json`, `cchecks.json`, `reachable.json` | `reach_csv_to_checks.py --complement` |

Not derived, and not derivable:

| artifact | why |
|---|---|
| `roles_and_services.txt` | a role is an *intent*; the dataset ships none |
| `reach.txt` | likewise — a policy states what *should* hold |

`benchmark.role_members` is what keeps the fabricated half honest: every role
must name an endpoint the transfer function actually has, and must declare the
`ipv4` that endpoint's generator actually injects. Both are refused at run time,
not only in a test.

## The inventory is fabricated

The dataset states its six questions over bare node ids. §1.9 is the owner's
decision to express them as an FPL policy instead, which needs roles and
services that have no counterpart in the raw data. So:

* one role per endpoint the six queries name, named after the node it stands
  for (`cloud_tf.node_name`) and carrying that node's own `/30`;
* one service per TCP port they constrain — 331, 332, 350, 351.

`README.txt` in `cloud-tf/` calls **331** *the* public service port, while query
03 is satisfiable on **332**. CLOUD_BENCH_PLAN.md §1.4 records that as an
unresolved discrepancy; both are declared here because both are asked about.

## Why the policy is written the way it is

`--->` rather than `<->>` or `<-->`. The cloud ACLs are stateless, so asserting
that return traffic is permitted because the forward direction is would be a
claim about conntrack this network does not implement. `<-->` would assert a
symmetric permission the dataset states for no pair.

**q02 has no rule.** Its verdict is `unsat` — nothing from the internet reaches
`dc2_leaf7_host6` — which is what default-deny already says. A rule would have
to be a permission, i.e. the opposite of the verdict.

**q06 has a rule it is expected to fail.** Its verdict is also `unsat`, but
unlike q02 it is unsat *on one port*: TCP 351 from `dc1_leaf6_host0`. Leaving it
to default-deny would generate an **unconditioned** denial — a strictly stronger
claim than the dataset makes, and one it offers no evidence for. Stated as a
permission instead, the generated must-reach check asks exactly q06's question,
and the dataset's answer makes it a **violation**. That expected violation *is*
the reproduction, and `cloud_provenance.expected_violated` is where it lives.

## 6 verdicts, 71 checks

Compiling five rules with `--complement` yields 71 checks. Six carry a
third-party verdict; the other 65 are expectations derived from a policy we
wrote. The stamp reports them **separately and never summed** — an unlabelled
table would let a mistake in our own understanding read as authoritative as a
verdict produced outside this tree (§1.9.0).

`cloud_provenance.pair_oracle_to_checks` refuses unless each query is carried by
exactly one check. That refusal replaces the failure mode of the hand-built
check set this supersedes: a check that went missing still counted as agreement,
because nothing had violated it.

A query's constraints need only be a **subset** of its check's, with any surplus
positive: `S350` compiles to `protocol:tcp;port:350` where query 05 constrains
only `tcp_dst = 350`. The narrowing is sound both ways — a narrower must-reach
check that passes proves the broader question satisfiable, and a narrower
must-not-reach check is implied by the broader unreachability. A surplus
*negation* would do neither, so it is not a match.

## A trap that was in the translator

Writing this inventory in the repository's usual style is what found it, so it
is recorded here even though it is fixed.

`policy_builder.comment_pattern` was `[ \t]* \# [ \t]* .* <newline>`, where the
second quantifier and `.*` both match the blanks after the `#`. Same language --
`[ \t]*.*` accepts exactly what `.*` accepts -- but one extra way to match
*every* comment line, so a run of them before a definition had 2^n parses to
explore before it could fail:

| comment lines before the first definition | translator |
|---:|---:|
| 10 | 0.06 s |
| 16 | 0.20 s |
| 20 | 2.08 s |
| 24 | > 120 s |

Blank lines made it worse rather than better -- they are another alternative in
the same group -- so three blank-separated blocks of 8 measured 31.8 s against
20 consecutive lines' 2.08 s.

**Fixed 2026-09-21** by dropping the redundant quantifier, plus the same overlap
one line lower (`[ \t]* = [ \t]*` against a `value_pattern` that contains a
space, made possessive). 200 comment lines and a 100-attribute role are now both
flat. Every committed policy in the tree compiles to a byte-identical matrix.
`policy_translator/test/test_policy_builder.py` guards both, with the parse in a
subprocess so the defect returning is a *failure* rather than a hang.
