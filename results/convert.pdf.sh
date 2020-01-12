#!/usr/bin/env sh


gnuplot $1.p

epstopdf $1.ps
pdfcrop $1.pdf > /dev/null
mv $1-crop.pdf $1.pdf
