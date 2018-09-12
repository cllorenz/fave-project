#!/usr/bin/env sh

PYTHONPATH=. python2 aggregator/stop.py

[ -S /tmp/np_aggregator.socket ] && rm /tmp/np_aggregator.socket
