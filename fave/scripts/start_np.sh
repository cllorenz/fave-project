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

if [ "$#" -eq "1" ]; then
    #valgrind --tool=memcheck --leak-check=full --track-origins=yes net_plumber --log4j-config $1 --hdr-len 1 --unix /tmp/net_plumber.socket >> /tmp/np/stdout.log &
    net_plumber --log4j-config $1 --hdr-len 1 --server 127.0.0.1 44001 >> $DIR/np/stdout.log 2>> $DIR/np/stderr.log &
elif [ "$#" -eq "2" ]; then
    [ -f $DIR/$2.socket ] && rm $DIR/$2.socket
    net_plumber --log4j-config $1 --hdr-len 1 --unix $DIR/$2.socket >> $DIR/np/$2.stdout.log 2>> $DIR/np/$2.stderr.log &
else
    [ -f $DIR/np/stdout.log ] && rm $DIR/np/stdout.log
    touch $DIR/np/stdout.log
    net_plumber --hdr-len 1 --server 127.0.0.1 44001 >> $DIR/np/stdout.log &
fi

#taskset -p 0x00000001 $PID > /dev/null

#sudo perf record -a -F 783 --call-graph dwarf -p $PID &
#PERF=$!
#echo $PERF > /tmp/perf.pid
#sleep 0.5s
