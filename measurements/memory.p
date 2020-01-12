set xrange [0:45]
set xtics 10
set xlabel "Time (in s)"

set yrange [0.0:500000.0]
set ytics 50000
set ylabel "Memory (in kB)"

set key left top
plot "memory.log" using 1 title 'SIZE' with lines,\
"memory.log" using 2 title 'RSS' with lines,\
"memory.log" using 3 title 'VSZ' with lines
set size 1.1,0.5
set terminal postscript portrait enhanced color dashed lw 1 "Helvetica" 14
set output "memory.ps"
replot
set terminal x11
set size 1,1
