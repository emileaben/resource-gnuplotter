set term pdf
set grid xtics
set xdata time
set timefmt "%s"
set format x "%d%b\n%Hh"
unset ytics
set output "NL.pdf"
set title "RIPE Atlas probes in the Netherlands connected to RIPE Atlas infrastucture\n(only probes with disconnects shown)"
set ylabel "Probes"
#set yrange [-0.25:2.25]
#set xrange ["1480118400":"1480622400"]
#set xrange ["1480507200":]
set xlabel "Time"
unset key
plot "NL.log" u 1:2:($3-$1):(0) w vectors nohead lc rgb "#4682b4"
