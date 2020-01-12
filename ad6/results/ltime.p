set xrange [0:2100]
set xtics 500
set xlabel "Amount of Rules"

set yrange [1:2000]
set ytics 500
set ylabel "Runtime (in s)"

set key left top
plot "inst.time.dat" using 1:4 title 'First Use' with lines,\
"inst.time.dat" using 1:9 title 'Reuse' with lines,\
"solve.time.dat" using 1:4 title 'MiniSAT' with lines,\
"solve.time.dat" using 1:8 title 'Clasp' with lines
set size 1.1,0.5
set terminal postscript portrait enhanced color dashed lw 1 "Helvetica" 14
set output "ltime.ps"
replot
set terminal x11
set size 1,1
