#!/bin/bash

# System dependencies for building and testing NetPlumber on Ubuntu 24.04.
# FaVe's own (Python) dependencies are installed separately by fave/setup.sh.
#
# Package names match the Dockerfile and the GitHub CI composite action
# (.github/actions/setup-fave-native); keep the three in sync.

set -e

APT_CONFS="--no-install-recommends -y"

sudo apt-get update
sudo apt-get $APT_CONFS install build-essential
sudo apt-get $APT_CONFS install liblog4cxx15
sudo apt-get $APT_CONFS install liblog4cxx-dev
sudo apt-get $APT_CONFS install libcppunit-1.15-0
sudo apt-get $APT_CONFS install libcppunit-dev

# For the libnetplumber Python binding (net_plumber/python): pybind11 + Python
# headers. Build it with `bash net_plumber/python/build_libnetplumber.sh` after
# NetPlumber is built (it does a one-off -fPIC rebuild so the core objects can
# link into a shared module).
sudo apt-get $APT_CONFS install python3-dev
sudo apt-get $APT_CONFS install pybind11-dev

# NOTE: BuDDy (libbdd) is NOT required for the default build. BDD support is
# off by default -- both `-DUSE_BDD` (build/sources.mk) and `LIBS += -lbdd`
# (build/objects.mk) are commented out, and `make all` links neither. Only the
# standalone `buddy_test` target needs libbdd; install it (e.g. `apt-get install
# libbdd-dev`) and uncomment those lines if you specifically want the BDD path.
