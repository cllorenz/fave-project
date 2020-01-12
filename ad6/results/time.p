set xrange [0:5]
set xtics 1
set xlabel " "

set yrange [0:2]
set ytics 0.1
set ylabel "Runtime (in s)"

set style fill solid
set boxwidth 0.5
set key left top
plot "time.dat" using 2 title 'Runtime' with boxes
set size 1.1,0.5
set terminal postscript portrait enhanced color dashed lw 1 "Helvetica" 14
set output "time.ps"
replot
set terminal x11
set size 1,1
