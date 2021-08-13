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

TIME='/usr/bin/time -f %e'

scripts/start_aggr.sh

echo "pgf firewall (pf+ruleset)"
PYTHONPATH=. $TIME -o /tmp/np/test.log python2 topology/topology.py -a -t packet_filter -n pgf -i 2001:db8:abc::1 -p 24
PYTHONPATH=. $TIME -ao /tmp/np/test.log python2 ip6np/ip6np.py -n pgf -i 2001:db8:abc::1 -f rulesets/pgf-ruleset

echo "776x empty python scripts"
for i in {1..776}; do
    PYTHONPATH=. $TIME -ao /tmp/np/test.log python2 profile_dummy.py
done

echo "113x packet filter (pf+rulesets)"
for i in {1..113};do
    PYTHONPATH=. $TIME -ao /tmp/np/test.log python2 topology/topology.py -a -t packet_filter -n mail.api -i 2001:db8:abc::2 -p 1
    PYTHONPATH=. $TIME -ao /tmp/np/test.log python2 ip6np/ip6np.py -n mail.api -i 2001:db8:abc::2 -f "rulesets/api-mail-ruleset"
done

scripts/stop_aggr.sh
