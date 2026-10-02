SUPERSEDED -- the first cells of phase A, run against a 64 MB /dev/shm.

Not deleted, because they are the evidence for the defect, and because a
measurement thrown away without saying why is indistinguishable from one that
was never taken.

WHAT WAS WRONG. FaVe writes every runtime log under /dev/shm/np. On this box
that tmpfs is 64 MB, and a single large cell exceeds it: wl_i2 produced a
33 MB stdout.log while inv.log rotated through three 10 MB backups, ~73 MB in
one run. When it filled, net_plumber's logging write failed, the process died,
and the aggregator surfaced "ConnectionResetError: Connection reset by peer".

So wl_stanford_np is recorded here as status=error, outcome=error, wall 91.2 s
-- against the 6.4 s that MEASUREMENT_RUN_PLAN.md 5.1 records for the same
cell. IT IS NOT AN ENGINE FAILURE. It is the machine, and ./test.sh doctor had
warned about exactly this ("the bench workloads overflow a small one --
redirect logs to disk for anything at bench scale").

These cells are superseded WHOLESALE rather than selectively, including the six
that completed with a valid verdict. /dev/shm reached 100% during the sequence
and the cheap cells cannot be SHOWN to have been unaffected; re-running all of
them costs minutes, and reasoning about which ones were spared costs more than
that and could be wrong.

THE FIX, and why it is the one chosen. The container cannot remount /dev/shm,
so /dev/shm/np is now a symlink to /var/tmp/np-logs on the 70 GB disk. That
changes WHERE the bytes land and nothing about WHAT IS LOGGED. Lowering the log
levels instead -- which is what bench/wl_berkeley/np.conf does for its own size
series -- would have changed the instrumentation cost and therefore the
wall-clock, which is a reported number in this campaign.

A SECOND DEFECT, VISIBLE IN wl_stanford_np.json AND FILED SEPARATELY:
that cell records impl=reimpl-literature with backend=netplumber. That is
VeriFlow-FR's provenance on a NetPlumber row. Its captured aggregator.log holds
one line -- "backend: veriflow {...}" -- left in /dev/shm by the EARLIER e2e
test run, because this cell's own aggregator died before writing its stamp. The
harness read the stale file and recorded another engine's provenance as though
it were this cell's, with impl_source saying "backend configuration stamp".
Item 31 requires provenance stamped rather than typed by hand so that "a table
cannot mislabel a row"; this is that guarantee defeated by staleness instead of
by hand-typing.
