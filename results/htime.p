set xrange [0:15]
set xtics 1
set xlabel " "

set yrange [1:2000]
set ytics 500
set ylabel "Runtime (in s)"

set style fill solid
set boxwidth 0.5
set key left top
plot "time.dat" using 1:2 title 'Runtime' with boxes
set size 1.1,0.5
set terminal postscript portrait enhanced color dashed lw 1 "Helvetica" 14
set output "htime.ps"
replot
set terminal x11
set size 1,1
