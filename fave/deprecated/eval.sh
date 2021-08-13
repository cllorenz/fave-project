#!/usr/bin/bash

# -*- coding: utf-8 -*-

# Copyright 2020 Claas Lorenz <claas_lorenz@genua.de>

# This file is part of FaVe.

# FaVe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FaVe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FaVe.  If not, see <https://www.gnu.org/licenses/>.

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
