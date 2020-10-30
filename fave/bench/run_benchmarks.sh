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

function check_integrity {
  # first run, there is no previous data
  [ "$(ls -A $LAST_NP)" ] && return 0

  # the amount of files changed since the last run -> report error
  [ "$(ls $LAST_NP | wc -l)" == "$(ls np_dump | wc -l)" ] || return 1

  for f in $(ls np_dump); do
    # if files differ -> report error
    [ "$(sha256sum $LAST_NP/$f | cut -f' ' -d1)" == "$(sha256sum np_dump/$f | cut -f' ' -d1)" ] || return 2
  done

  return 0
}

BENCH=$1
[ -n "$2" ] && RULESET=$2 || RULESET=bench/wl_tum/tum-ruleset
RUNS=10

LAST_NP=last_np_dump
mkdir -p $LAST_NP
rm -rf $LAST_NP/*
mkdir -p results

# run FaVe benchmark
for i in $(seq 1 $RUNS); do
  RDIR=results/$i.raw
  mkdir -p $RDIR
  rm -rf $RDIR/*

  sleep 1

  SOUT=$RDIR/$i.stdout.log
  SERR=$RDIR/$i.stderr.log
  echo -n "run benchmark $i: $BENCH... "
  python2 $BENCH -4 -r $RULESET > $SOUT 2> $SERR
  echo "done"

  sleep 1

  echo -n "check integrity... "
  check_integrity
  [ -z "$?" ] && break || echo "ok"
  rm -f $LAST_NP/*
  cp np_dump/* $LAST_NP/

  cp -r /tmp/np/ $RDIR/
done

# run NetPlumber benchmark
HDR_LEN=$(grep "length" np_dump/fave.json | tr -d ' ,' | cut -d: -f2 | awk '{ print $1/8; }')
for i in $(seq 1 $RUNS); do
  SOUT=$i.np.stdout.log
  SERR=$i.np.stderr.log

  echo -n "run netplumber directly $i: $BENCH... "
  net_plumber --hdr-len $HDR_LEN --load np_dump --policy np_dump/policy.json > $SOUT 2> $SERR
  echo "done"

  RDIR=results/$i.raw
  mv $SOUT $RDIR/
  mv $SERR $RDIR/
done
