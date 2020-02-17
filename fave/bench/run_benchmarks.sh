#!/usr/bin/env bash

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
RUNS=2

LAST_NP=last_np_dump
mkdir -p $LAST_NP
rm -rf $LAST_NP/*
mkdir -p results

# run FaVe benchmark
for i in $(seq 1 $RUNS); do
  SOUT=$i.stdout.log
  SERR=$i.stderr.log
  echo -n "run benchmark $i: $BENCH... "
  python $BENCH > $SOUT 2> $SERR
  echo "done"

  echo -n "check integrity... "
  check_integrity
  [ -z "$?" ] && break || echo "ok"
  rm -f $LAST_NP/*
  cp np_dump/* $LAST_NP/

  RDIR=results/$i.raw
  mkdir -p $RDIR
  rm -rf $RDIR/*

  mv $SOUT $RDIR/
  mv $SERR $RDIR/

  cp -r /tmp/np/ $RDIR/
done

# run NetPlumber benchmark
HDR_LEN=$(grep "length" np_dump/fave.json | tr -d ' ,' | cut -d: -f2 | awk '{ print $1/8; }')
for i in $(seq 1 $RUNS); do
  SOUT=$i.np.stdout.log
  SERR=$i.np.stderr.log

  net_plumber --hdr-len $HDR_LEN --load np_dump --policy np_dump/policy.json > $SOUT 2> $SERR

  RDIR=results/$i.raw
  mv $SOUT $RDIR/
  mv $SERR $RDIR/
done
