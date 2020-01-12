set xrange [0:11]
set xtics 1
set xlabel "Time (in s)"

set yrange [0.0:100000.0]
set ytics 10000
set ylabel "Memory (in kB)"

set key left top

set arrow from 2,0 to 2,48632 nohead
set arrow from 10.2,0 to 10.2,57788 nohead

set grid ytics linecolor "black"

plot "memory_nodb.log" using 4:2 title 'RSS' with lines linecolor rgb "#00305e"
set size 1.1,0.5
set terminal postscript portrait enhanced color dashed lw 1 "Helvetica" 14
set output "memory_nodb.ps"
replot
set terminal x11
set size 1,1
