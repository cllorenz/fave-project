# Where does the insert phase END, relative to the first withdrawal?
#
# §2.14 described every non-airtel member as "insert everything, then withdraw
# everything". opmix only COUNTS ops, so that described the balance, not the
# order: equal counts are equally consistent with a trace that interleaves
# them. This pass measures the order. If the last `+` precedes the first `-`,
# the inserts are a contiguous block (lines 1..N) and the state after line N
# is one the trace actually passes through -- the candidate static snapshot.
#
# Two more things are measured on the way, both cheap:
#
#   * whether field 4 is monotone across the INSERTS (a timestamp or sequence
#     number would be; withdrawal lines are not read for it);
#   * how many routers carry a rule for each prefix, as a histogram. §2.4's
#     rule is that a prefix is DELIVERED where it arrives without a rule; a
#     prefix every router but one carries can only be delivered at that one,
#     while one most routers lack needs a path analysis to say where.
#
# No FIB dict: one entry per distinct prefix and per router only, so unlike
# replay.awk no member is truncated. It does NOT detect insert revisions (a
# `(router, prefix)` inserted twice); replay.awk does, and needs the FIB for it.
BEGIN { FS = "," }
{
  n++
  op = substr($0, 1, 1)
  if (op == "+") {
    plus++; last_plus = n
    if (first_minus) plus_after_minus++
    pfx = substr($1, 2); per_prefix[pfx]++
    if (!($2 in routers)) { routers[$2] = 1; nrtr++ }
    v = $4 + 0
    if (plus == 1) first4 = v
    else if (v < prev4) dec4++
    else if (v == prev4) eq4++
    prev4 = v
  }
  else if (op == "-") {
    minus++
    if (!first_minus) first_minus = n
    last_minus = n
  }
  else other++
}
END {
  printf "lines=%d\ninserts=%d\nwithdrawals=%d\nother_op=%d\n", n, plus, minus, other
  printf "last_insert_line=%d\nfirst_withdrawal_line=%d\nlast_withdrawal_line=%d\n", \
         last_plus, first_minus, last_minus
  printf "inserts_after_first_withdrawal=%d\n", plus_after_minus
  printf "field4_first=%d\nfield4_last=%d\n", first4, prev4
  printf "field4_decreasing_steps=%d\nfield4_equal_steps=%d\n", dec4, eq4
  np = 0; for (p in per_prefix) { np++; hist[per_prefix[p]]++ }
  printf "insert_routers=%d\ninsert_prefixes=%d\n", nrtr, np
  # One line per distinct count; sort -t= -k1.18n to read it in order.
  for (c in hist) printf "routers_per_prefix[%d]=%d\n", c, hist[c]
}
