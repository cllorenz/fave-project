#!/usr/bin/env sh

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

DIR=/dev/shm
mkdir -p $DIR/np

SOCK_PARAMS="-s 127.0.0.1 -p 44000"
BACK_PARAMS=""
DEBUG_PARAMS=""

UNIX=""

usage() { echo "usage: $0 [-hdu] [-S <backend>]" 2>&2; }

while getopts "hduS:" o; do
    case "${o}" in
        h)
            usage
            exit 0
            ;;
        d)
            DEBUG_PARAMS="-d"
            ;;
        u)
            UNIX="/dev/shm/np_aggregator.socket"
            ;;
        S)
            BACK_PARAMS="-S ${OPTARG}"
            ;;
        *)
            usage
            exit 1
            ;;
    esac
done

if [ -n "$UNIX" ]; then
    [ -s $UNIX ] && rm $UNIX
    SOCK_PARAMS="-u"
fi

python2 aggregator/aggregator.py $SOCK_PARAMS $BACK_PARAMS $DEBUG_PARAMS &

#PID=$!
#echo $PID > $DIR/aggr.pid
#taskset -p 0x00000004 $PID > /dev/null
#sleep 0.5s
