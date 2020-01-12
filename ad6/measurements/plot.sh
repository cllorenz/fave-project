#!/usr/bin/env sh

SCRIPT=$1
ITYPE=`echo $SCRIPT | cut -d '.' -f 1`

gnuplot $SCRIPT

epstopdf $ITYPE.ps
pdfcrop $ITYPE.pdf > /dev/null
mv $ITYPE-crop.pdf $ITYPE.pdf

