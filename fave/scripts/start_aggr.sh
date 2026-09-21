#!/usr/bin/env bash

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

# The interpreter to run FaVe's Python with. A bare `python3` is whatever PATH
# resolves first, which in a container whose venv is not activated is the SYSTEM
# interpreter with none of FaVe's dependencies -- and the aggregator then dies on
# `No module named 'filelock'` inside a backgrounded process nobody reads, so every
# flow check fails as though the MODEL were wrong. `./test.sh` exports the
# interpreter it resolved; standalone callers keep the old default or set $PYTHON.
PYTHON="${PYTHON:-python3}"

DIR=/dev/shm
mkdir -p $DIR/np

SOCK_PARAMS="-s 127.0.0.1 -p 44000"
BACK_PARAMS=""
DEBUG_PARAMS=""
MAP_PARAMS=""
# AD6_PLAN.md §9.3 Phase 6 / §9.28. `-S` is the net_plumber SERVER list and has
# always been called "backend" in this script's own usage string; `-b` is the
# verification ENGINE (netplumber|apkeep|ad6). Two different things, and the
# older name is kept rather than renamed so no existing caller breaks.
ENGINE_PARAMS=""
# Verbatim pass-through for engine-specific options (--solver, --lite-acyclic,
# --grounding, --apkeep-engine). One opaque string rather than a flag apiece:
# this script has no business knowing an engine's vocabulary, and the
# aggregator already validates it and exits non-zero on a bad value.
EXTRA_PARAMS=""

UNIX=""

usage() { echo "usage: $0 [-hdut] [-S <np-servers>] [-m <mapping>] [-b <engine>] [-X <engine-opts>]" 2>&2; }

while getopts "hadm:uS:tb:X:" o; do
    case "${o}" in
        h)
            usage
            exit 0
            ;;
        b)
            ENGINE_PARAMS="-b ${OPTARG}"
            ;;
        X)
            EXTRA_PARAMS="${OPTARG}"
            ;;
        a)
            SOCK_PARAMS="-a"
            ;;
        d)
            DEBUG_PARAMS="-d"
            ;;
        m)
            MAP_PARAMS="-m ${OPTARG}"
            ;;
        u)
            UNIX="/dev/shm/np_aggregator.socket"
            ;;
        S)
            BACK_PARAMS="-S ${OPTARG}"
            ;;
        t)
            DEBUG_PARAMS="-t"
            ;;
        *)
            usage
            exit 1
            ;;
    esac
done

if [ -n "$UNIX" ]; then
    # -S (is a SOCKET), not -s (size > 0): a unix socket is always 0 bytes, so
    # `-s` was never true and a stale socket was never removed. After any
    # unclean shutdown the aggregator then died on "Address already in use" and
    # the benchmark reported the far less helpful "could not connect to fave".
    # scripts/start_np.sh has always used -S; this was a one-character typo.
    [ -S $UNIX ] && rm $UNIX
    SOCK_PARAMS="$SOCK_PARAMS -u"
fi

# WHERE the barrier owner file lives is util/barrier.py's business -- it honours
# $FAVE_BARRIER_DIR and names the file itself -- so ask it rather than spell the
# path a second time here and let the two drift.
#
# Failing here rather than falling back to a literal is deliberate: the only way
# this import fails is a PYTHONPATH that does not reach fave/, and that is
# exactly the condition under which the aggregator would later die inside a
# backgrounded process nobody reads. Better to say so now, with the cause.
OWNER="$("$PYTHON" -c 'from util import barrier; print(barrier.owner_path())' 2>&1)"
if [ $? -ne 0 ] || [ -z "$OWNER" ]; then
    echo "start_aggr: cannot locate the barrier owner file via util.barrier:" >&2
    echo "  $OWNER" >&2
    echo "  (is PYTHONPATH set to the fave/ directory?)" >&2
    exit 1
fi

# A stale owner from an unclean shutdown, for the same reason the socket above
# is removed: the wait below would return at once on a file belonging to a
# process that is gone, and the barrier would then fail with "the aggregator
# (pid N) no longer exists" instead of starting cleanly.
rm -f "$OWNER"

# EXTRA_PARAMS is deliberately unquoted: it carries several whitespace-separated
# options (e.g. "--solver cadical195 --lite-acyclic") that must reach argparse as
# separate words.
# shellcheck disable=SC2086
"$PYTHON" aggregator/aggregator_service.py $MAP_PARAMS $SOCK_PARAMS $BACK_PARAMS $ENGINE_PARAMS $EXTRA_PARAMS $DEBUG_PARAMS &
AGGR_PID=$!

# WAIT FOR THE BARRIER OWNER FILE, not for the socket, and not merely for the
# process to be spawned.
#
# The original wait was for the socket, because the aggregator constructs its
# verification ENGINE before it binds and that is not free: the APKeep backend
# starts a JVM and loads a jar first (the NDD engine, now the default, is the
# slowest of them). That closed the large gap and left a small one. The
# aggregator binds and then publishes the owner on the NEXT statement, and
# `sock.bind()` is what CREATES the socket -- so this loop released between the
# two, `GenericBenchmark._startup` logged "started aggregator" and called
# `_wait_for_fave()` at once, and the first barrier found no owner. Since
# `barrier._owner_alive` reads an absent owner as "no aggregator is registered"
# and `BarrierError` means "can no longer complete at all", a state that lasts
# microseconds was reported as permanent. Two benchmarks in a row hit it.
#
# The owner file is the right thing to wait for because it is the artifact the
# waiter downstream actually reads, and aggregator_service.py's own comment
# beside `publish_owner()` says so: it is written after the bind "so its
# presence means an aggregator is actually up". Waiting for it SUBSUMES the
# socket wait -- the publish cannot happen before the bind.
#
# Now unconditional. The TCP path had no wait at all, so it raced without even
# the partial protection the unix path had; the owner file is published for both
# socket types by the same statement.
#
# Bounded, and loud when it expires: a silent give-up here would let the
# benchmark carry on and blame the model (the swallowed-substep shape of
# AD6_PLAN.md §9.28). $AGGR_WAIT seconds, overridable for a slow box.
AGGR_WAIT="${AGGR_WAIT:-120}"
waited=0
while [ ! -e "$OWNER" ]; do
    if ! kill -0 "$AGGR_PID" 2>/dev/null; then
        echo "start_aggr: aggregator exited before it registered at $OWNER" >&2
        exit 1
    fi
    if [ "$waited" -ge "$AGGR_WAIT" ]; then
        echo "start_aggr: aggregator did not register at $OWNER within ${AGGR_WAIT}s" >&2
        exit 1
    fi
    sleep 1
    waited=$((waited + 1))
done

#PID=$!
#echo $PID > $DIR/aggr.pid
#taskset -p 0x00000004 $PID > /dev/null
#sleep 0.5s
