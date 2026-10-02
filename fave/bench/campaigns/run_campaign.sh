#!/usr/bin/env bash
#
# V5 reportable campaign driver -- MEASUREMENT_RUN_PLAN.md §6.
#
# Runs the phases CONSECUTIVELY and never concurrently: §6 says "serialise
# everything whose number is reported", because peak RSS and wall-clock are
# meaningless if two heavy cells share the machine, and the long cells' RATE is
# itself the result.
#
# It is detached (setsid nohup) and RESUMABLE, because §6.1's environment is a
# container in a VM on a shared server: re-running this script skips every
# phase that already has its output and resumes at the first that does not.
# The campaign must survive being started three times.
#
# It is also DEADLINE-AWARE. The owner granted 64 h of experiments and is out
# of office, so a phase that cannot fit in what remains is NOT STARTED: a run
# that was merely cut off has not been shown not to finish (§8.1), and starting
# a 24 h cell with 6 h left would manufacture exactly that false result.

set -u

ROOT=/home/ubuntu/fave-project
FAVE=$ROOT/fave
PY=$ROOT/.venv/bin/python3
export PATH="$ROOT/net_plumber/build:$PATH"

DATE=20261002
CAMP=$FAVE/bench/campaigns
RES_A=$CAMP/results_v5_$DATE
RES_B=$FAVE/bench/deltanet/eval/results_berkeley_ndd_$DATE
LOG=$CAMP/CAMPAIGN.log

# 64 h from the owner's instruction at ~2026-10-02T14:45Z.
DEADLINE=$(date -u -d '2026-10-05T06:45:00Z' +%s)

cd "$FAVE" || exit 1

# /dev/shm IS 64 MB ON THIS BOX AND THAT IS NOT ENOUGH.
#
# FaVe writes every runtime log under /dev/shm/np: NetPlumber's log4j appenders
# (np.log, inv.log, rpc.log) plus the captured console (stdout.log). On wl_i2
# that is a 33 MB stdout.log and an inv.log rotating through three 10 MB
# backups -- ~73 MB against a 64 MB tmpfs. When it fills, log4cxx's write
# fails, net_plumber dies, and the aggregator reports "Connection reset by
# peer"; the cell then looks like an ENGINE failure. wl_stanford_np failed
# exactly that way and recorded status=error.
#
# The container cannot remount /dev/shm (mount needs privileges it lacks), so
# the directory is a SYMLINK to disk. This is deliberately the fix that changes
# WHERE the bytes land and nothing about WHAT IS LOGGED: lowering the log
# levels (as bench/wl_berkeley/np.conf does) would change the instrumentation
# cost and therefore the wall-clock, which is a reported number here.
#
# Re-established on every start, because /dev/shm is recreated empty by a
# container restart and §6.1 requires the campaign to survive one.
if [ ! -L /dev/shm/np ]; then
    mkdir -p /var/tmp/np-logs
    rm -rf /dev/shm/np
    ln -s /var/tmp/np-logs /dev/shm/np
fi
SHM_AVAIL=$(df -Pm /dev/shm/np | awk 'NR==2 {print $4}')
if [ "${SHM_AVAIL:-0}" -lt 10240 ]; then
    echo "FATAL: only ${SHM_AVAIL} MB behind /dev/shm/np; a bench cell needs" \
         "far more and would fail as a fake engine error. Refusing to start." >&2
    exit 1
fi

say() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }
left_h() { echo $(( (DEADLINE - $(date -u +%s)) / 3600 )); }

# Refuse to start a phase that cannot fit. $1 = hours needed, $2 = phase name.
fits() {
    local need=$1 name=$2 have
    have=$(left_h)
    if [ "$have" -lt "$need" ]; then
        say "SKIP $name -- needs ${need} h, ${have} h left before the budget deadline."
        say "     NOT a did-not-finish: this phase was never started (§8.1)."
        return 1
    fi
    return 0
}

say "=== campaign driver up, $(left_h) h of budget left ==="
say "    net_plumber: $(command -v net_plumber)"

# ---------------------------------------------------------------- phase A ---
# 51 cells, cheapest workload first. The queue is itself resumable, so this is
# safe to re-enter: it skips every cell that already has a valid result.
say "--- phase A: the cheap matrix, 51 cells ---"
$PY bench/cell_queue.py --queue "$CAMP/v5_phase_a_main.json" \
    --out-dir "$RES_A" >>"$LOG" 2>&1
say "phase A exit=$? ($(ls "$RES_A"/*.json 2>/dev/null | wc -l) result files)"

# ---------------------------------------------------------------- phase B ---
# wl_berkeley through k=1: the cell whose feasibility is least certain, which
# is why §6 puts it before phase C.
if fits 5 "phase B (wl_berkeley drill)"; then
    say "--- phase B: wl_berkeley drill through k=1 ---"
    mkdir -p "$RES_B"
    if [ -n "$(ls "$RES_B"/k*.json 2>/dev/null)" ]; then
        say "phase B: results present, skipping the drill"
    else
        $PY bench/deltanet/eval/berkeley_drill.py --out "$RES_B" \
            --budget 50400 --jvm-xmx 20g --memory-floor 2000 >>"$LOG" 2>&1
        say "berkeley_drill exit=$?"
    fi
    $PY bench/deltanet/eval/berkeley_table.py "$RES_B" \
        > "$RES_B/TABLE.txt" 2>>"$LOG"
    say "berkeley_table written"
fi

# ---------------------------------------------------------------- phase C ---
# The probes FIRST, so that if either says "re-run after all" that is known
# before a day is committed (§5.3).
if fits 3 "phase C probes"; then
    say "--- phase C: the two 1 h faithful probes ---"
    for B in stanford i2; do
        OUTP=$FAVE/bench/wl_$B/eval/probe_${B}_1h_v5.json
        if [ -f "$OUTP" ]; then say "probe $B present, skipping"; continue; fi
        mkdir -p "$(dirname "$OUTP")"
        $PY bench/faithful_bdd_measure.py --bench $B --deadline-s 3600 \
            --status-every-s 60 --out "$OUTP" >>"$LOG" 2>&1
        say "probe $B exit=$?"
    done
fi

# The one full 24 h run. Needs its whole limit plus margin, or it is not begun.
OUTC=$FAVE/bench/wl_cloud/eval/bdd_v5_$DATE.json
if [ -f "$OUTC" ]; then
    say "phase C: wl_cloud result present, skipping"
elif fits 26 "phase C (bdd x wl_cloud, 24 h)"; then
    say "--- phase C: bdd x wl_cloud, one full run, 24 h limit ---"
    mkdir -p "$(dirname "$OUTC")"
    $PY bench/cloud_bdd_measure.py --engine bdd --deadline-s 86400 \
        --status-every-s 60 --out "$OUTC" >>"$LOG" 2>&1
    say "wl_cloud exit=$?"
fi

# ---------------------------------------------------------------- phase E ---
# The two deferred expected-did-not-finishes, last and singly, with their
# declared 24 h limits untouched. Whatever budget is left decides how many run.
if fits 25 "phase E (the deferred vf-plain cells)"; then
    say "--- phase E: the deferred vf-plain did-not-finish cells ---"
    $PY bench/cell_queue.py --queue "$CAMP/v5_phase_a_dnf.json" \
        --out-dir "$RES_A" >>"$LOG" 2>&1
    say "phase E exit=$?"
fi

say "=== campaign driver done, $(left_h) h of budget left ==="
