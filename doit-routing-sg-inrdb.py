#!/usr/bin/env python
import arrow
import hashlib
import os
import subprocess
import sys
from   tempfile import mkstemp
import time

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
deltas  = {} # deltas[ts] => number added/removed at that timestamp

# use these for {ASN -> height} for ASN labels on the right edge
y_min = {}
y_max = {}

last_time_seen = 0

for aidx,asn in enumerate( asns ):
	cmd = "ido +minpwr 30 +M +oc +t +dc RIS_V_CC %s" % (asn)
	proc = subprocess.Popen( cmd, shell=True, stdout=subprocess.PIPE)

	y_min.setdefault(asn, idx)
	y_max.setdefault(asn, idx)

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

			# we definitely have a time marker for this ASN
			# note it, and give it an ID to be used later
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
			if end > last_time_seen:
				last_time_seen = end

			has_data = True

			# hash the ASN and grab six hex digits to form the RGB value
			rgb = "#" + hashlib.md5(str(asn)).hexdigest()[0:6]

			data.append([start, idx, end-start, asn, pfx, rgb])

			deltas.setdefault(start, 0)
			deltas.setdefault(end,   0)
			deltas[start] = deltas[start] + 1
			deltas[end]   = deltas[end]   - 1

			# keep storing this
			y_max[asn] = idx

		if has_data == True:
			pfx2idx[ pfx ] = idx
			idx2pfx[ idx ] = pfx
			idx += 1

pid = os.getpid()
tmpfile        = "/tmp/ccviz.%s.%s"        % (CC, pid)
labelsfile     = "/tmp/ccviz.%s.labels.%s" % (CC, pid)
timeseriesfile = "/tmp/ccviz.%s.ts.%s"     % (CC, pid)
tmpplot        = "/tmp/plt.%s.%s"          % (CC, pid)
outfile        = "%s.png"                  % (CC)

# print data to file
with open(tmpfile, 'w') as fh:
	for drow in data:
		print >>fh, "%s %s %s %s %s %s" % tuple(drow)
	fh.close()

with open(labelsfile, 'w') as fh:
	for asn in y_min.keys():
		print >>fh, "%s %s %s" % (asn, last_time_seen, ((y_max[asn]-y_min[asn])/2)+y_min[asn])
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

with open(tmpplot,'w') as fh:
	print >>fh, """
set term pngcairo size 1000,700

set palette model RGB

# these functions are a bit ugly but they rip apart RGB values as strings
# and turn them into RGB values for plotting
red(colorstring)    = colorstring[2:3]
green(colorstring)  = colorstring[4:5]
blue(colorstring)   = colorstring[6:7]
hex2dec(hex)        = gprintf("%0.f",int('0X'.hex))
rgb(r,g,b)          = 65536*int(r)+256*int(g)+int(b)
hex2rgbvalue(color) = rgb( hex2dec(red(color)), hex2dec(green(color)), hex2dec(blue(color)) )

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

set output "{OUTFILE}"

set multiplot ti "Networks as seen in RIPE RIS"

# = lower plot =============================================
set lmargin at screen 0.05
set bmargin at screen 0.2
set tmargin at screen 0.75

set ytics format ""

plot "{TMPFILE}" using 1:2:3:(0):(hex2rgbvalue(stringcolumn(6))) w vectors nohead lw 1.5 lc rgb variable,\
     "{LABELS}" using 2:3:1 with labels left notitle

# = upper plot =============================================
set bmargin at screen 0.8
set tmargin at screen 0.95

unset xlabel
unset xtics
set ylabel "#prefixes"
set ytics format "%g"
set yrange [0:*]

plot "{TIMESERIES}" using 1:2 w steps lw 1.5

""".format( OUTFILE=outfile, TMPFILE=tmpfile, TIMESERIES=timeseriesfile, LABELS=labelsfile )


os.system("gnuplot < %s" % tmpplot)
print >>sys.stderr, "data tmpfile: %s" % (tmpfile)
print >>sys.stderr, "plot tmpfile: %s" % (tmpplot)
print >>sys.stderr, "output in %s"     % (outfile)

