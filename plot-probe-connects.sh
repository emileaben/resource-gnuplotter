#!/usr/bin/env bash

while getopts  "c:" flag
do
	case $flag in
		c)
			CC=$OPTARG
			;;
		h)
			echo "$0 -c CC"
			exit
			;;
	esac
done

if [ -z ${CC+x} ]
then
	echo "$0 -c CC"
	exit 1
fi

if [ ! -e $CC.log ]
then
	echo "$CC.log doesn't exist!"
	exit 1
fi

gnuplot <<EOF

set term pngcairo size 1000,600

set grid xtics
set tics nomirror
set border 3
unset key

set xdata time
set timefmt "%s"
set format x "%d %b-%Hh"
set xtics rotate
unset ytics

set title "RIPE Atlas probes in the Netherlands connected to RIPE Atlas infrastucture\n(only probes with disconnects shown)"

set ylabel "Probes"
set xlabel "Time"

set output "$CC.png"
plot "$CC.log" u 1:2:(\$3-\$1):(0) w vectors nohead lc rgb "#4682b4"

EOF

