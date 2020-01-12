#!/bin/sh

if [ "$#" -ne 1 ]; then
	echo "usage: $0 <configuration>"
	exit 1
fi

CONFIG=$1

ITYPE=`cat $CONFIG | grep -E "itype" | cut -f 2`

SCRIPT=$ITYPE.p

XRANGE=`cat $CONFIG | grep -E "xrange" | cut -f 2`
XTICS=`cat $CONFIG | grep -E "xtics" | cut -f 2`
XLABEL=`cat $CONFIG | grep -E "xlabel" | cut -f 2`

YRANGE=`cat $CONFIG | grep -E "yrange" | cut -f 2`
YTICS=`cat $CONFIG | grep -E "ytics" | cut -f 2`
YLABEL=`cat $CONFIG | grep -E "ylabel" | cut -f 2`

echo "set xrange $XRANGE" > $SCRIPT
echo "set xtics $XTICS" >> $SCRIPT
echo "set xlabel \"$XLABEL\"" >> $SCRIPT
echo "" >> $SCRIPT

echo "set yrange $YRANGE" >> $SCRIPT
echo "set ytics $YTICS" >> $SCRIPT
echo "set ylabel \"$YLABEL\"" >> $SCRIPT
echo "" >> $SCRIPT

echo "set key left top" >> $SCRIPT

echo -n "plot " >> $SCRIPT

DATA=`cat $CONFIG | grep -E "ifile" | tr '\t' ';' | tr ' ' '_'`
LEN=`echo "$DATA" | wc -l`
COUNT=1
for FILE in $DATA
do
	IFILE=`echo $FILE | cut -d ';' -f 2`
        COL=`echo $FILE | cut -d ';' -f 3`
        TITLE=`echo $FILE | cut -d ';' -f 4 | tr '_' ' '`

	echo -n "\"$IFILE\" using $COL title '$TITLE' with lines" >> $SCRIPT
	if [ "$COUNT" -lt "$LEN" ]; then
		echo ",\\" >> $SCRIPT
	else
		echo "" >> $SCRIPT
	fi
	COUNT=`expr $COUNT + 1`
done

echo "set size 1.1,0.5" >> $SCRIPT
echo "set terminal postscript portrait enhanced color dashed lw 1 \"Helvetica\" 14" >> $SCRIPT
echo "set output \"$ITYPE.ps\"" >> $SCRIPT
echo "replot" >> $SCRIPT
echo "set terminal x11" >> $SCRIPT
echo "set size 1,1" >> $SCRIPT

gnuplot $SCRIPT

epstopdf $ITYPE.ps
pdfcrop $ITYPE.pdf > /dev/null
mv $ITYPE-crop.pdf $ITYPE.pdf
