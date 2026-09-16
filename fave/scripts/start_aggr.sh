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

UNIX=""

usage() { echo "usage: $0 [-hdut] [-S <backend>] [-m <mapping>]" 2>&2; }

while getopts "hadm:uS:t" o; do
    case "${o}" in
        h)
            usage
            exit 0
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

"$PYTHON" aggregator/aggregator_service.py $MAP_PARAMS $SOCK_PARAMS $BACK_PARAMS $DEBUG_PARAMS &

#PID=$!
#echo $PID > $DIR/aggr.pid
#taskset -p 0x00000004 $PID > /dev/null
#sleep 0.5s
