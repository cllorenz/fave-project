set xrange [0:200]
set xtics 30
set xlabel "Time (in s)"

set yrange [0.0:1500000.0]
set ytics 100000
set ylabel "Memory (in kB)"

set key left top
plot "memory_db.log" using 1 title 'SIZE' with lines,\
"memory_db.log" using 2 title 'RSS' with lines,\
"memory_db.log" using 3 title 'VSZ' with lines
set size 1.1,0.5
set terminal postscript portrait enhanced color dashed lw 1 "Helvetica" 14
set output "memory_db.ps"
replot
set terminal x11
set size 1,1
