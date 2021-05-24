#!/usr/bin/env bash

BENCH=$1

LOG=stdout.log
echo "" > $LOG
HASSEL_DIR=~/hassel-public

export PYTHONPATH=$HASSEL_DIR

TF_GENERATOR=$HASSEL_DIR/hsa-python/examples/$BENCH/generate_$BENCH"_"backbone_tf.py
JSON_GENERATOR=$HASSEL_DIR/hsa-python/examples/$BENCH/generate_rules_json_file.py

if [ "$BENCH" == "i2" ]; then
    TF_GENERATOR=$HASSEL_DIR/hsa-python/examples/$BENCH/generate_internet2_backbone_tf.py
    JSON_GENERATOR=$HASSEL_DIR/hsa-python/examples/$BENCH/generate_i2_json_tfs.py
fi

TF_DIR=$BENCH"_tfs"

VANILLA_DIR=$BENCH"_json_vanilla"
mkdir -p $VANILLA_DIR
FAVENP_DIR=$BENCH"_json_favenp"
mkdir -p $FAVENP_DIR
FAVENP_DUMP=$BENCH"_favenp_dump"
mkdir -p $FAVENP_DUMP
rm -rf $FAVENP_DUMP/*


TF_LOG=$BENCH"_gen_tfs.log"
JSON_LOG=$BENCH"_gen_json.log"

VANILLA_LOG=$BENCH"_vanilla.log"
FAVENP_LOG=$BENCH"_favenp.log"
DUMP_LOG=$BENCH"_favenp_dump.log"

HDR_LEN=`grep "length" $VANILLA_DIR/config.json | tr -d ' ,' | cut -d: -f2`

echo "generate tfs"
rm -rf $TF_DIR
mkdir -p $TF_DIR
PYTHONPATH=$HASSEL_DIR/hsa-python \
python2 $TF_GENERATOR $BENCH"_orig" $TF_DIR > $TF_LOG
cat $TF_LOG >> $LOG

GEN_TFS=`grep "completed in" $TF_LOG | cut -d' ' -f3`
echo "run time: $GEN_TFS s"

echo "transform tfs to json"
PYTHONPATH=$HASSEL_DIR/hsa-python \
python2 $JSON_GENERATOR \
    $TF_DIR \
    $VANILLA_DIR > $JSON_LOG
cat $JSON_LOG >> $LOG

echo "generate policy"
python2 create_policy.py $VANILLA_DIR >> $LOG

echo "rename tfs"
bash rename_workload.sh $VANILLA_DIR

echo "transform to favenp workload"
python2 transform.py $VANILLA_DIR $FAVENP_DIR >> $LOG

echo "run vanillanp on vanilla workload"
$HASSEL_DIR/net_plumber/Ubuntu-NetPlumber-Release/net_plumber \
    --hdr-len $HDR_LEN \
    --load $VANILLA_DIR \
    --policy $VANILLA_DIR/policy.json > $VANILLA_LOG
cat $VANILLA_LOG >> $LOG

LOAD_VANILLA=`grep "total run time" $VANILLA_LOG | cut -d' ' -f 5`
POLICY_VANILLA=`grep "Loaded policy" $VANILLA_LOG | cut -d' ' -f5`

echo "init: "$(echo $LOAD_VANILLA | awk '{ print $1 / 1000000.0; }')" s"
echo "reach: $POLICY_VANILLA s"

echo "run favenp on favenp workload"
net_plumber \
    --hdr-len $HDR_LEN \
    --load $FAVENP_DIR \
    --policy $FAVENP_DIR/policy.json \
    --dump $FAVENP_DUMP > $FAVENP_LOG

cat $FAVENP_LOG >> $LOG

LOAD_FAVENP=`grep "total run time" $FAVENP_LOG | cut -d' ' -f 4`
POLICY_FAVENP=`grep "Loaded policy" $FAVENP_LOG | cut -d' ' -f5`

echo "init: "$(echo $LOAD_FAVENP | awk '{ print $1 / 1000000.0; }')" s"
echo "reach: $POLICY_FAVENP s"

echo "compare results"
python2 analyze_output.py $BENCH $VANILLA_LOG $FAVENP_LOG

echo "run favenp on favenp dump"
net_plumber \
    --hdr-len $HDR_LEN \
    --load $FAVENP_DUMP \
    --policy $FAVENP_DUMP/policy.json > $DUMP_LOG

cat $DUMP_LOG >> $LOG

LOAD_DUMP=`grep "total run time" $DUMP_LOG | cut -d' ' -f 4`
POLICY_DUMP=`grep "Loaded policy" $DUMP_LOG | cut -d' ' -f5`

echo "init: "$(echo $LOAD_DUMP | awk '{ print $1 / 1000000.0; }')" s"
echo "reach: $POLICY_DUMP s"

echo "compare results"
python2 analyze_output.py $BENCH $FAVENP_LOG $DUMP_LOG

FAVE_DIR=$BENCH"_json_fave"
cp -r $FAVENP_DIR $FAVE_DIR
cp $FAVE_DIR/*.json ../fave/bench/wl_$BENCH/$BENCH"-json/"

REPRO_WD=$(pwd)
FAVE_LOG=$REPRO_WD/$BENCH"_fave.log"
FAVE_DUMP_LOG=$BENCH"_fave_dump.log"
FAVE_DUMP=$REPRO_WD/$BENCH"_fave_dump"

echo "run fave on favenp workload"

cd ../fave

PYTHONPATH=. python2 bench/wl_$BENCH/benchmark.py > $FAVE_LOG
cat $FAVE_LOG >> $LOG

FAVE_INIT=`grep "seconds" /dev/shm/np/aggregator.log | grep -v "dump\|stop" | \
  awk 'BEGIN {
    done = 0; result = 0;
  } {
    if (done || $4 == "generators" || $4 == "generator") {
      done = 1;
    } else if (done && $4 == "probe") {
      done = 0;
      result += $6;
    } else {
      result += $6;
    }
  } END {
    print result;
  }'`

FAVE_REACH=`grep "seconds" /dev/shm/np/aggregator.log | grep -v "dump\|stop" | \
  awk 'BEGIN {
    start = 0;
    result = 0;
  } {
    if (start || $4 == "generators" || $4 == "generator") {
      start = 1;
      if ($4 == "generators" || $4 == "generator") {
        result += $6;
      } else if ($4 == "links") {
        result += $6;
      } else if ($4 == "probe") {
        start = 0;
      }
    }
  } END {
    print result;
  }'`

echo "init: $FAVE_INIT s"
echo "reach: $FAVE_REACH s"

rm -rf $FAVE_DUMP
cp -r np_dump $FAVE_DUMP

cd $REPRO_WD

echo "run favenp on fave dump"

net_plumber \
    --hdr-len $HDR_LEN \
    --load $FAVE_DUMP \
    --policy $FAVE_DUMP/policy.json > $FAVE_DUMP_LOG

LOAD_FAVE_DUMP=`grep "total run time" $FAVE_DUMP_LOG | cut -d' ' -f 4`
POLICY_FAVE_DUMP=`grep "Loaded policy" $FAVE_DUMP_LOG | cut -d' ' -f5`

echo "init: "$(echo $LOAD_FAVE_DUMP | awk '{ print $1 / 1000000.0; }')" s"
echo "reach: $POLICY_FAVE_DUMP s"
