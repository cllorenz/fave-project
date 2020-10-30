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

#PERF=`cat /tmp/perf.pid`
#sudo kill -9 $PERF
#rm /tmp/perf.pid

#PID=`cat /tmp/np.pid`
#kill -9 $PID
#rm /tmp/np.pid

PYTHONPATH=. python2 scripts/stop_np.py

[ -S /tmp/net_plumber.socket ] && rm /tmp/net_plumber.socket
