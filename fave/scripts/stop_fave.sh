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

SOCK_PARAMS="-s 127.0.0.1 -p 44000"

SERVER=""
PORT=""
UNIX=""

usage() { echo "usage: $0 [-h] [-s <host> -p <port> |-u]" 2>&2; }

while getopts "hs:p:u" o; do
    case "${o}" in
        h)
            usage
            exit 0
            ;;
        s)
            SERVER=${OPTARG}
            ;;
        p)
            PORT=${OPTARG}
            ;;
        u)
            UNIX="1"
            ;;
        *)
            usage
            exit 1
            ;;
    esac
done

if [[ -n "$SERVER" && -n "$PORT" ]]; then
    SOCK_PARAMS="-s $SERVER -p $PORT"
elif [ -n "$SERVER" ]; then
    SOCK_PARAMS="-s $SERVER -p 44000"
elif [ -n "$PORT" ]; then
    SOCK_PARAMS="-s 127.0.0.1 -p $PORT"
elif [ -n "$UNIX" ]; then
    SOCK_PARAMS="-u"
fi

"$PYTHON" aggregator/stop.py $SOCK_PARAMS
RC=$?

# AD6_PLAN.md §9.32: net_plumber's ONLY shutdown path used to be the line above
# -- stop.py talks to the AGGREGATOR, which then calls
# verification_engine.stop(). If the aggregator never started, died, or was
# killed, the request reached nobody and net_plumber was orphaned: still
# holding its unix socket, still writing logs, and invisible to the benchmark,
# which discarded this exit status entirely.
#
# So: when the aggregator could not be reached, fall back to the pids
# start_np.sh recorded. Each is killed ONLY after confirming it is still a
# net_plumber -- a bare `kill` on a stale pidfile would shoot whatever process
# inherited the number.
PIDFILE=$DIR/np/np.pid
if [ $RC -ne 0 ] && [ -f "$PIDFILE" ]; then
    echo "stop_fave: aggregator unreachable (rc=$RC); stopping net_plumber directly" >&2
    while read -r PID; do
        [ -n "$PID" ] || continue
        COMM=$(cat "/proc/$PID/comm" 2>/dev/null)
        if [ "$COMM" = "net_plumber" ]; then
            kill "$PID" 2>/dev/null && echo "stop_fave: killed net_plumber $PID" >&2
        fi
    done < "$PIDFILE"
fi

# The pidfile describes THIS run only; a stale one would make the next run's
# fallback chase dead pids.
[ -f "$PIDFILE" ] && rm -f "$PIDFILE"

exit $RC
