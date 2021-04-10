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

RDIR=$1
BENCH=$2
[ -n "$3" ] && RULESET="-r $3" || RULESET=""
[ -n "$4" ] && OPTS=$4 || OPTS=""
RUNS=10

LAST_NP=last_np_dump
mkdir -p $LAST_NP
rm -rf $LAST_NP/*
mkdir -p $RDIR/fave

# run FaVe benchmark
for i in $(seq 1 $RUNS); do
  RAW_DIR=$RDIR/fave/$i.raw
  rm -rf $RAW_DIR
  mkdir -p $RAW_DIR

  sleep 1

  SOUT=$RAW_DIR/stdout.log
  SERR=$RAW_DIR/stderr.log
  echo -n "run benchmark $i: $BENCH... "
  python2 $BENCH $OPTS $RULESET > $SOUT 2> $SERR
  echo "done"

  sleep 1

  echo -n "check integrity... "
  check_integrity
  [ -z "$?" ] && break || echo "ok"
  rm -rf $LAST_NP/*
  mv np_dump/* $LAST_NP/

  cp -r /dev/shm/np/ $RAW_DIR
done

# run NetPlumber benchmark
echo -n "run netplumber directly for $BENCH ..."
mv $LAST_NP np_dump
HDR_LEN=$(grep "length" np_dump/fave.json | tr -d ' ,' | cut -d: -f2 | awk '{ print $1/8; }')
for i in $(seq 1 $RUNS); do
  RAW_DIR=$RDIR/np/$i.raw
  rm -rf $RAW_DIR
  mkdir -p $RAW_DIR
  SOUT=$RAW_DIR/stdout.log
  SERR=$RAW_DIR/stderr.log

  echo -n " $i"
  net_plumber --hdr-len $HDR_LEN --load np_dump --policy np_dump/policy.json > $SOUT 2> $SERR
done
echo ""
