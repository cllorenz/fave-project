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
    [ -s $UNIX ] && rm $UNIX
    SOCK_PARAMS="$SOCK_PARAMS -u"
fi

# EXTRA_PARAMS is deliberately unquoted: it carries several whitespace-separated
# options (e.g. "--solver cadical195 --lite-acyclic") that must reach argparse as
# separate words.
# shellcheck disable=SC2086
"$PYTHON" aggregator/aggregator_service.py $MAP_PARAMS $SOCK_PARAMS $BACK_PARAMS $ENGINE_PARAMS $EXTRA_PARAMS $DEBUG_PARAMS &

#PID=$!
#echo $PID > $DIR/aggr.pid
#taskset -p 0x00000004 $PID > /dev/null
#sleep 0.5s
