#!/usr/bin/bash

LPATH="/tmp/np"

NP="$LPATH/np.log"
PF="$LPATH/pf.log"
PFR="$LPATH/pfr.log"
SUB="$LPATH/sub.log"
SUBL="$LPATH/subl.log"
SW="$LPATH/sw.log"


FILES="$PF $PFR $SUB $SUBL $SW"

TOTAL=`cat $FILES | awk '{s+=$1} END {print s;}'`
NPTOTAL=`grep "Event handling time" $NP | cut -d ':' -f 2 | cut -d 'm' -f 1 | cut -d ' ' -f 2 | awk 'BEGIN {s=0;}{s+=$1;} END {print s;}'`

#FILES="$@"

echo "total: $TOTAL"
echo "np:    $NPTOTAL"

for FILE in $FILES; do
    echo "file:   $FILE"

    TOTAL=`awk '{s+=$1} END {print s}' $FILE`
    echo "total:  $TOTAL"

    AVG=`awk 'BEGIN {i=0;} {s+=$1;i+=1;} END {print s/i;}' $FILE`
    echo "avg:    $AVG"

    SORTED=(`sort $FILE`)
    MEDIAN="${SORTED[$(( ${#SORTED[@]}/2 ))]}"
    echo "median: $MEDIAN"
done
