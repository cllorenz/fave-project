#!/usr/bin/env bash

cd Ubuntu-NetPlumber-Release
make clean
cd ..

PACK=package
SRC=$PACK/src
BUILD=$PACK/build

mkdir -p $SRC
mkdir -p $BUILD

cp -r src $PACK/
cp -r Ubuntu-NetPlumber-Release/* $BUILD/

cp setup-ubuntu.sh $PACK/

EXCLUDES=""
#"\
# --exclude='$SRC/net_plumber/policy_probe.h'\
# --exclude='$SRC/net_plumber/policy_probe.cc'\
#"

tar $EXCLUDES cfz net_plumber.tar.gz $PACK/

rm -rf $PACK
