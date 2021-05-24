#!/use/bin/env bash

RUNS=10
BENCH=$1
RESULTS=$2

BDIR=$BENCH"_json_vanilla"
export PYTHONIOENCODING=utf8
HDR_LEN=$(cat $BDIR/config.json | python2 -c "import sys, json; print json.load(sys.stdin)['length']")

mkdir -p $RESULTS/$BENCH

echo -n "run $BENCH:"
for i in $(seq 1 $RUNS); do
    echo -n " $i"
    RDIR=$RESULTS/$BENCH/$i.vnp
    mkdir -p $RDIR
    ~/hassel-public/net_plumber/Ubuntu-NetPlumber-Release/net_plumber --hdr-len $HDR_LEN --load $BDIR --policy $BDIR/policy.json > $RDIR/stdout.log 2> $RDIR/stderr.log
done
echo ""
