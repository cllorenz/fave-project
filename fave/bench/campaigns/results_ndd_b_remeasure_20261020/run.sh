#!/bin/sh
# The six cells of PROTOCOL.txt, alone and serially. Run from fave/, venv
# python, PYTHONPATH=. -- each arm x workload one cell, 32 GB, 2 GB floor, 12 h.
C=bench/campaigns/results_ndd_b_remeasure_20261020
NOB=/home/yolo/.claude/jobs/83d1b9f6/tmp/wt_bnoff/apkeep/target/apkeep-1.0.0.jar
PY=../.venv/bin/python3
python3 bench/campaign_inputs.py check $C || exit 1
for w in $C/inputs/wl_berkeley_k30 bench/wl_tum; do
  for arm in B noB noB+A; do
    case $arm in
      B)     jar=;    extra= ;;
      noB)   jar=$NOB; extra= ;;
      noB+A) jar=$NOB; extra=--ndd-collect-visited ;;
    esac
    out=$C/cells/$(basename $w)_$arm
    FAVE_APKEEP_JAR=$jar PYTHONPATH=. $PY bench/incremental_cell.py $w \
      --engine ndd-apkeep --stream z --checks checks.json $extra \
      --limit-rss 32768 --memory-floor 2048 --limit-wall 43200 --out $out
    echo "$(basename $w) $arm rc=$?"
  done
done
