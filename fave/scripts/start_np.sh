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



SOCK_PARAMS="--server 127.0.0.1 44001"
LOG_PARAMS=""

SERVER=""
PORT=""
UNIX=""

RDR=""

usage() { echo "usage: $0 [-hvV] [-s <host> -p <port> |-u <unix socket>] [-l <logging>]" 2>&2; }

while getopts "hs:p:u:l:vV" o; do
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
            UNIX=${OPTARG}
            [ -S $UNIX ] && rm $UNIX
            ;;
        l)
            LOG_PARAMS="--log4j-config ${OPTARG}"
            ;;
        v)
            RDR="1"
            ;;
        V)
            VALGRIND="1"
            ;;
        *)
            usage
            exit 1
            ;;
    esac
done

if [[ -n "$SERVER" && -n "$PORT" ]]; then
    SOCK_PARAMS="--server $SERVER $PORT"
elif [ -n "$SERVER" ]; then
    SOCK_PARAMS="--server $SERVER 44001"
elif [ -n "$PORT" ]; then
    SOCK_PARAMS="--server 127.0.0.1 $PORT"
elif [ -n "$UNIX" ]; then
    SOCK_PARAMS="--unix $UNIX"
fi

if [ -n "$VALGRIND" ]; then
    valgrind --tool=memcheck --leak-check=full --track-origins=yes net_plumber --hdr-len 1 $LOG_PARAMS $SOCK_PARAMS &
elif [ -n "$RDR" ]; then
    net_plumber --hdr-len 1 $LOG_PARAMS $SOCK_PARAMS &
else
    net_plumber --hdr-len 1 $LOG_PARAMS $SOCK_PARAMS >> $DIR/np/stdout.log 2>> $DIR/np/stderr.log &
fi


#taskset -p 0x00000001 $PID > /dev/null

#sudo perf record -a -F 783 --call-graph dwarf -p $PID &
#PERF=$!
#echo $PERF > /tmp/perf.pid
#sleep 0.5s
