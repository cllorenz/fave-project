#!/usr/bin/env sh

URL="http://localhost:8080"

DATA=`cat testCycle.xml`
CONFIG=`curl --data "networks=$DATA" $URL/aggregator`
INSTANCES=`curl --data "config=$CONFIG&anomalies=2" $URL/instantiator`
RESULTS=`curl --data "instances=$INSTANCES" $URL/solver`

echo $RESULTS
