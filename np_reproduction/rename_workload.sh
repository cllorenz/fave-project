#!/usr/bin/bash

DIR=$1

for f in `ls $DIR/*.rules.json`; do
  ID=`cat $f | python2 -c "import sys, json; print json.load(sys.stdin)['id']"`
  mv $f $DIR/$ID.tf.json
done
