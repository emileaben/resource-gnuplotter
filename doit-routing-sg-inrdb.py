#!/usr/bin/env python
import subprocess
import os
import time
import sys
import arrow
from tempfile import mkstemp

### TODO in radix

## do decent optparse

asns      = []
countries = []

START_T   = arrow.get(sys.argv[1]).timestamp
END_T     = arrow.get(sys.argv[2]).timestamp
CC        = sys.argv[3]

for arg in sys.argv[4:]:
	asns.append( arg )

print >>sys.stderr, "start:%s end:%s" % ( START_T, END_T )

idx     = 0
pfx2idx = {}
idx2pfx = {}
data    = []
cbtics  = []
deltas  = {} # deltas[ts] => number added/removed at that timestamp

for aidx,asn in enumerate( asns ):
	cbtics.append( '"%s" %s' % (asn, aidx) )
	cmd = "ido +minpwr 30 +M +oc +t +dc RIS_V_CC %s" % (asn)
	proc = subprocess.Popen( cmd, shell=True, stdout=subprocess.PIPE)
	for line in iter(proc.stdout.readline,''):
		line = line.rstrip('\n')
		if not line.startswith('BLOB'):
			continue

		s = line.split('\a')
		fields = s.pop(0).split('|')
		pfx = fields[2]
		has_data = False
		for tspec in s:
			tparts = tspec.split()
			if len(tparts) == 0:
				continue

			# examplar timespec format: 'VALID: 1504516800 - 1505374500'
			start = int(tparts[1])
			end   = int(tparts[3])
			if end < START_T:
				continue
			if start < START_T:
				start = START_T
			if start > END_T:
				continue
			if end > END_T:
				end = END_T
			has_data = True

			data.append([start,idx,end-start,aidx])

			deltas.setdefault(start, 0)
			deltas.setdefault(end,   0)
			deltas[start] = deltas[start] + 1
			deltas[end]   = deltas[end]   - 1

		if has_data == True:
			pfx2idx[ pfx ] = idx
			idx2pfx[ idx ] = pfx
			idx += 1

	idx += 3 #for each asn

pid = os.getpid()
tmpfile = "/tmp/ccviz.%s.%s"            % (CC, pid)
tmpplot = "/tmp/plt.%s.%s"              % (CC, pid)
outfile = "%s.png"                      % (CC)
timeseriesfile = "/tmp/ccviz.%s.ts.%s"  % (CC, pid)

# print data to file
with open(tmpfile, 'w') as fh:
	for drow in data:
		print >>fh, "%s %s %s %s" % tuple(drow)
	fh.close()

with open(timeseriesfile, 'w') as fh:
	total = 0
	# [:-1] in the loop here is to skip the last '0' point, because
	# the deltas calculated above will subtract everything that 'ends'
	# at the end of time
	timestamps = sorted(deltas.keys())
	for ts in timestamps[:-1]:
		total = total + deltas[ts]
		print >>fh, ts, total
	# put a dummy point at the end, to fill out gnuplot lines
	# to the right-most side
	print >>fh, timestamps[-1], total
	fh.close()


## ASN tics
cbtics_txt = ','.join( cbtics )

with open(tmpplot,'w') as fh:
	print >>fh, """
set term pngcairo size 1000,700

set palette model RGB

unset key

set grid xtics
set border 3
set tics nomirror

set xdata time
set timefmt "%s"

set xlabel "time"
set xtics rotate
set format x "%Y-%m-%d"

set ylabel "prefixes"
set ytics format ""

set rmargin at screen 0.80
set cbtics ({CBTICS})
set cbtics font ",9"

set output "{OUTFILE}"

set multiplot ti "Networks as seen in RIPE RIS"

# = lower plot =============================================
set lmargin at screen 0.05
set bmargin at screen 0.2
set tmargin at screen 0.75

set ytics format ""

plot "{TMPFILE}" using 1:2:3:(0):4 w vectors nohead lw 1.5 lc palette

# = upper plot =============================================
set bmargin at screen 0.8
set tmargin at screen 0.95

unset xlabel
unset xtics
set ylabel "#prefixes"
set ytics format "%g"

plot "{TIMESERIES}" using 1:2 w steps lw 1.5

""".format( CBTICS=cbtics_txt, OUTFILE=outfile, TMPFILE=tmpfile, TIMESERIES=timeseriesfile )


os.system("gnuplot < %s" % tmpplot)
print >>sys.stderr, "data tmpfile: %s" % (tmpfile)
print >>sys.stderr, "plot tmpfile: %s" % (tmpplot)
print >>sys.stderr, "output in %s"     % (outfile)

