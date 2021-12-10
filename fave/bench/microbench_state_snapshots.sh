#!/usr/bin/env bash

# -*- coding: utf-8 -*-

# Copyright 2021 Claas Lorenz <claas_lorenz@genua.de>

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


RUNS=10
RESULTS=results/mb_ssnap
mkdir -p $RESULTS
#rm -rf $RESULTS/*

FWOP=$RESULTS/raw_wo_policy.dat
FWIP=$RESULTS/raw_with_policy.dat

echo -n "hz" > $FWOP
echo -n "hz" > $FWIP
for i in $(seq 1 $RUNS); do
	echo -n " ot$i" >> $FWOP
	echo -n " ot$i" >> $FWIP
done
echo "" >> $FWOP
echo "" >> $FWIP

export PYTHONPATH=.
echo "run without policies"
for hz in 1 10 50 100 200 300 400 500 600 700 800 900 1000; do
	echo -n "$hz"
	echo -n "$hz" >> $FWOP
	for i in $(seq 1 $RUNS); do
		RES=`python2 bench/wl_state_snapshots/benchmark.py -f $hz | cut -d ' ' -f 3`
		echo -n " $RES"
		echo -n " $RES" >> $FWOP
	done
	echo ""
	echo "" >> $FWOP
done

echo "run with policies"
for hz in 1 10 50 100; do
	echo -n "$hz"
	echo -n "$hz" >> $FWIP
	for i in $(seq 1 $RUNS); do
		RES=`python2 bench/wl_state_snapshots/benchmark.py -p -f $hz | cut -d ' ' -f 3`
		echo -n " $RES"
		echo -n " $RES" >> $FWIP
	done
	echo ""
	echo "" >> $FWIP
done
