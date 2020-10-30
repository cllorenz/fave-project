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

mkdir -p /tmp/np

if [ "$#" -eq "1" ]; then
#    net_plumber --log4j-config $1 --hdr-len 1 --server 127.0.0.1 1234 >> /tmp/np/stdout.log &
    [ -f /tmp/net_plumber.socket ] && rm /tmp/net_plumber.socket
    #valgrind --tool=memcheck --leak-check=full --track-origins=yes net_plumber --log4j-config $1 --hdr-len 1 --unix /tmp/net_plumber.socket >> /tmp/np/stdout.log &
    net_plumber --log4j-config $1 --hdr-len 1 --unix /tmp/net_plumber.socket >> /tmp/np/stdout.log 2>> /tmp/np/stderr.log &
    PID=$!
else
    [ -f /tmp/np/stdout.log ] && rm /tmp/np/stdout.log
    touch /tmp/np/stdout.log
    net_plumber --hdr-len 1 --server 127.0.0.1 1234 >> /tmp/np/stdout.log &
    PID=$!
fi

#taskset -p 0x00000001 $PID > /dev/null

#sudo perf record -a -F 783 --call-graph dwarf -p $PID &
#PERF=$!
#echo $PERF > /tmp/perf.pid
#sleep 0.5s
