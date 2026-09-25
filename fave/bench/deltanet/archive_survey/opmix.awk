# Op mix ONLY -- no FIB dict, so no memory ceiling and no early abort.
# The replay pass capped at 30M live keys on three members; this answers the
# actual question (insert-only, or removals too?) over the WHOLE file.
{ c[substr($0, 1, 1)]++ }
END { printf "lines=%d\n", NR
      for (k in c) printf "op[%s]=%d\n", k, c[k] }
