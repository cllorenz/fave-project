# Replay a Delta-net update trace to its FINAL FIB, and census it on the way.
#
# The trace is a sequence of `+`/`-` updates; the final snapshot is whatever is
# still live at EOF. That snapshot is emitted in the SAME format the trace uses
# (`+<prefix>,<router>,<next_hop>,<priority>`), so `bench/deltanet/trace.py`
# consumes it unchanged -- the point of the exercise.
#
# NOT the Python parser, deliberately: that one REFUSES a withdrawal, and
# withdrawals are the whole subject here.
BEGIN { FS = ","; CAP = 45000000 }
{
  n++
  op  = substr($0, 1, 1)
  pfx = substr($1, 2)
  key = $2 SUBSEP pfx

  if (op == "+") {
    plus++
    if (key in fib) revisions++; else nlive++
    fib[key] = $3 "," $4
    if (nlive > CAP) { over = 1; exit }

    # Census work is done once per NEW name, not once per line: the regexes
    # are what made the first pass slow, and distinct names are few.
    if (!(pfx in prefixes)) { prefixes[pfx] = 1; npfx++
      slash = index(pfx, "/"); plen = substr(pfx, slash + 1) + 0; plens[plen]++ }
    if (!($2 in routers)) { routers[$2] = 1; nrtr++
      if ($2 !~ /^s[0-9]+-[0-9]+$/) { rbad++; if (rbad <= 3) rsample[rbad] = $2 } }
    if (!($3 in hops)) { hops[$3] = 1; nhop++
      if ($3 !~ /^s[0-9]+-[0-9]+$/) { hbad++; if (hbad <= 3) hsample[hbad] = $3 } }

    slash = index(pfx, "/"); plen = substr(pfx, slash + 1) + 0
    if ($4 + 0 != 5 * plen + 100) { pbad++; if (pbad <= 3) psample[pbad] = $0 }
  }
  else if (op == "-") {
    minus++
    if (key in fib) { delete fib[key]; nlive-- } else spurious++
  }
  else { other++; if (other <= 3) osample[other] = $0 }
}
END {
  printf "lines=%d\ninserts=%d\nwithdrawals=%d\nother_op=%d\n", n, plus, minus, other > census
  printf "insert_revisions=%d\nspurious_withdrawals=%d\n", revisions, spurious > census
  printf "final_snapshot_rules=%d\nexceeded_cap=%d\n", nlive, over > census
  printf "union_prefixes=%d\nunion_routers=%d\nunion_nexthops=%d\n", npfx, nrtr, nhop > census
  printf "priority_violations=%d\nrouter_name_nonconforming=%d\nnexthop_name_nonconforming=%d\n", pbad, rbad, hbad > census
  s = ""; for (p in plens) s = s sprintf("%d:%d ", p, plens[p])
  printf "union_plen_lengths=%s\n", s > census
  for (i = 1; i <= 3; i++) if (i in psample) printf "sample_prio_violation=%s\n", psample[i] > census
  for (i = 1; i <= 3; i++) if (i in rsample) printf "sample_router_name=%s\n", rsample[i] > census
  for (i = 1; i <= 3; i++) if (i in hsample) printf "sample_nexthop_name=%s\n", hsample[i] > census
  for (i = 1; i <= 3; i++) if (i in osample) printf "sample_other_op=%s\n", osample[i] > census

  if (!over) for (k in fib) {
    split(k, kk, SUBSEP); split(fib[k], vv, ",")
    printf "+%s,%s,%s,%s\n", kk[2], kk[1], vv[1], vv[2]
  }
}
