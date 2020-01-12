set xrange [0:5]
set xtics 1
set xlabel " "
set xtics font "Times-Roman,24"

set yrange [50:200]
set ytics 20
set ylabel "Runtime (in s)" font "Times-Roman,24"
set ytics font "Times-Roman,18"

set style fill solid
set grid ytics linecolor "black"
set boxwidth 0.5
set key left top
plot "time.dat" using 3:xticlabels(1) title '' with boxes linecolor rgb "#00305e"
set size 1.1,0.5
set terminal postscript portrait enhanced color dashed lw 1 "Helvetica" 14
set output "medium.time.ps"
replot
set terminal x11
set size 1,1
