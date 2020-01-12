#! /usr/bin/env sh

minisat /dev/shm/solver.in | grep "CPU time" | tr -s [[:blank:]] '\t' | cut -f 4
