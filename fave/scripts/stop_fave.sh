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

python2 aggregator/stop.py $SOCK_PARAMS
