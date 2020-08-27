#!/usr/bin/env python
import arrow
import hashlib
import json
import os
import radix
import subprocess
import sys
from   tempfile import mkstemp
import time

## do decent optparse

asns      = []
countries = []

START_T   = arrow.get(sys.argv[1]).timestamp
END_T     = arrow.get(sys.argv[2]).timestamp
CC        = sys.argv[3]

for arg in sys.argv[4:]:
	asns.append( arg )

print >>sys.stderr, "start:%s end:%s" % ( START_T, END_T )
print >>sys.stderr, asns

idx     = 0
data    = []
deltas  = {} # deltas[ts] => number added/removed at that timestamp

# use these for {ASN -> height} for ASN labels on the right edge
#y_min = {}
#y_max = {}

last_time_seen = 0

asnmap  = {}  # asn -> dict of prefixes -> list of vector tuples
state = {}

#asns.sort(key = lambda x: int(x))
for asn in asns:
	print >>sys.stderr, asn

	cmd = "ido +minpwr 1 +M +oc +t +dc RIS_V_CC %s" % (asn)
	proc = subprocess.Popen( cmd, shell=True, stdout=subprocess.PIPE)

	asnmap.setdefault(asn, {})
	state.setdefault(asn, {"trie": radix.Radix(), "y_min": 0, "y_max": 0, "y_map": {}, "y_hgt": {} })

	prefixes = asnmap[asn]

	for line in iter(proc.stdout.readline,''):
		line = line.rstrip('\n')
		if not line.startswith('BLOB'):
			continue

		s = line.split('\a')
		fields = s.pop(0).split('|')
		pfx = fields[2]

		prefixes.setdefault(pfx, [])

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

			state[asn]["trie"].add(pfx)
			prefixes[pfx].append( (start, end) )

# now munge the data
# I think I want two cycles:
# 1: pass over all prefixes. Log the larger nets first. Count how many nets are inside each.
# 2: calculate the y-positions and heights for each of these.
#
# this is going to be inefficient until I decide I should hack py-radix!

def descend(depth, trie, pfx, visited, y_map, y_hgt_map, y_pos):
	print str(depth)+" Descending into "+pfx
	print str(depth)+" Visiting "+pfx+" for the first time!"
	# make a note that we've been here
	visited.add(pfx)
	y_map[pfx] = y_pos

	# uncover this prefix's children
	# if it has no children, give it a height of '1'
	children = trie.search_covered(pfx)

	# if it does have children, accumulate *their* heights
	height = 1
	children.sort(key = lambda x: int(x.prefix.split('/')[1]))
	for child in children:
		if child.prefix == pfx:
			continue
		if child.prefix in visited:
			continue

		(visited, fatness, y_map, y_hgt_map) = descend(depth+1, trie, child.prefix, visited, y_map, y_hgt_map, y_pos)
		height += fatness
		y_pos  += fatness

	y_hgt_map[pfx] = height

	print str(depth)+" Leaving "+pfx+" with pos:"+str(y_map[pfx])+", height:"+str(y_hgt_map[pfx])
	return (visited, height, y_map, y_hgt_map)

y_pos = 0
#y_map = {}
#y_hgt_map = {}
asns = asnmap.keys()
asns.sort(key = lambda x: int(x))
for asn in asns:
	pfx_map  = {}
	prefixes = asnmap[asn].keys()
	state[asn]["y_min"] = y_pos

	print "parp"
	print asn

	visited = set()
	# sort the list, returning the largest networks first
	prefixes.sort(key = lambda x: int(x.split('/')[1]))
	for pfx in prefixes:
		if pfx in visited:
			continue

		print pfx
		trie = state[asn]["trie"]
		(visited, fatness, y_map, y_hgt_map) = descend(0, trie, pfx, visited, state[asn]["y_map"], state[asn]["y_hgt"], y_pos)
		state[asn]["y_hgt"][pfx] = fatness
		y_pos += fatness

		print "0 Leaving "+pfx+" with pos:"+str(y_map[pfx])+", height:"+str(y_hgt_map[pfx])

#
#		tmp = trie.search_worst(pfx).prefix
#		if tmp == pfx:
#			y_pos += 1
##			y_map[tmp] = y_pos
##			pfxnode = trie.search_exact(pfx)
##			pfxnode.data["y"] = y_pos
##			y_pos += 1
#		print tmp, pfx, y_pos
#		y_map[pfx] = y_pos
#		#print pfx, trie.search_worst(pfx).prefix
	state[asn]["y_max"] = y_pos

#for asn in asnmap:
#	for pfx in asnmap[asn]:
#		print asn, pfx, y_map[pfx], asnmap[asn][pfx]

max_height = 0
for asn in asns:
	pfx_map  = {}
	prefixes = asnmap[asn].keys()

	rgb = "#" + hashlib.md5(str(asn)).hexdigest()[0:6]

	prefixes.sort(key = lambda x: int(x.split('/')[1]))
	for pfx in prefixes:
		for timespec in asnmap[asn][pfx]:
			start = timespec[0]
			end   = timespec[1]
			idx   = state[asn]["y_map"][pfx]
			hgt   = state[asn]["y_hgt"][pfx]
			data.append([start, end, idx, idx+hgt, pfx, asn, rgb])
			print [start, end, idx, idx+hgt, pfx, asn, rgb]

			deltas.setdefault(start, 0)
			deltas.setdefault(end,   0)
			deltas[start] = deltas[start] + 1
			deltas[end]   = deltas[end]   - 1
	max_height = state[asn]["y_max"]

annotationsFile = "annotations.json"
annotationCount = 1
annotationList  = []
if os.path.exists(annotationsFile):
	with open(annotationsFile, 'r') as fh:
		annotations = json.loads(fh.read())
		for record in annotations:
			start_ts = arrow.get(record["start"]).timestamp
			end_ts   = arrow.get(record["end"]).timestamp
			annotateLine = "set object " + str(annotationCount) + " rectangle from \"" + str(start_ts) + "\",0 to \"" + str(end_ts) + "\","+str(max_height)+" fillcolor rgb \""+record["color"]+"\" fillstyle solid noborder"
			annotationList.append(annotateLine)
			print annotateLine

			xFraction = -1
			# if the annotation falls within the start/end range,
			# add the label to the plot.
			if end_ts >= START_T and start_ts <= END_T:
				fullWidth        = END_T  - START_T
				annotationMiddle = ((end_ts - start_ts) / 2) + start_ts
				label_x          = (annotationMiddle - START_T) / float(fullWidth)
				label_y          = -0.1
				if   "align" in record and record["align"] == "right":
					label_x = (start_ts - START_T) / float(fullWidth)
				elif "align" in record and record["align"] == "left":
					label_x = (end_ts - START_T) / float(fullWidth)
				else:
					record["align"] = "center"

				annotateLine = "set label \""+record["name"]+"\" at graph "+str(label_x)+","+str(label_y) + " "+record["align"]+" font \",8\""
				annotationList.append(annotateLine)

			print annotateLine
			annotationCount += 1
		fh.close()


pid = os.getpid()
datfile        = "/tmp/ccviz.%s.%s"        % (CC, pid)
labelsfile     = "/tmp/ccviz.%s.labels.%s" % (CC, pid)
timeseriesfile = "/tmp/ccviz.%s.ts.%s"     % (CC, pid)
tmpplot        = "/tmp/plt.%s.%s"          % (CC, pid)
outfile        = "%s.png"                  % (CC)

with open(datfile, 'w') as fh:
	for drow in data:
		print >>fh, "%s %s %s %s %s %s %s" % tuple(drow)
	fh.close()

with open(labelsfile, 'w') as fh:
	for asn in state.keys():
		print >>fh, "%s %s %s" % ("AS"+asn, last_time_seen, ((state[asn]["y_max"]- state[asn]["y_min"])/2.0)+state[asn]["y_min"])
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

set xtics 86400
set xtics rotate
set format x "'%y-%m-%d\\n%H:%M"
set xrange [{START_TS}:{END_TS}]

set ylabel "prefixes"

set output "{OUTFILE}"

set multiplot ti "Networks as seen in RIPE RIS"

# = lower plot =============================================
set lmargin at screen 0.05
set bmargin at screen 0.13
set tmargin at screen 0.75

set ytics format ""

set style fill solid noborder
# boxxyerrors:  x y xlow xhigh ylow yhigh
plot "{DATFILE}" using 1:3:1:2:3:4:(hex2rgbvalue(stringcolumn(7))) w boxxyerrorbars lc rgb variable,\
     "{LABELS}" using 2:3:1 with labels font ",8" left notitle

# = upper plot =============================================
set bmargin at screen 0.8
set tmargin at screen 0.95

unset xlabel
unset xtics
set ylabel "#prefixes"
set ytics format "%g"
set yrange [0:*]

{ANNOTATIONS}

plot "{TIMESERIES}" using 1:2 w steps lw 1.5

""".format( OUTFILE=outfile, DATFILE=datfile, TIMESERIES=timeseriesfile, LABELS=labelsfile, START_TS=START_T, END_TS=END_T, ANNOTATIONS='\n'.join(annotationList) )


os.system("gnuplot < %s" % tmpplot)
print >>sys.stderr, "data tmpfile: %s" % (datfile)
print >>sys.stderr, "plot tmpfile: %s" % (tmpplot)
print >>sys.stderr, "output in %s"     % (outfile)

sys.exit(1)


#	y_min.setdefault(asn, idx)
#	y_max.setdefault(asn, idx)
#
#	# pull out the network size and give it a height
#	height  = 1
#	network = pfx.split('/')[0]
#	masklen = int(pfx.split('/')[1])
#	if ":" in network and masklen <= 64 and masklen >= 32:
#		height = 65 - masklen
#	elif ":" not in network and masklen <= 24 and masklen >= 8:
#		height = 25 - masklen
#
#		has_data = True
#
#		# hash the ASN and grab six hex digits to form the RGB value
#		rgb = "#" + hashlib.md5(str(asn)).hexdigest()[0:6]
#
##			data.append([start, end-start, idx, height, pfx, asn, rgb])
#		data.append([start, end, idx, idx+height, pfx, asn, rgb])
#
#		deltas.setdefault(start, 0)
#		deltas.setdefault(end,   0)
#		deltas[start] = deltas[start] + 1
#		deltas[end]   = deltas[end]   - 1
#
#	if has_data == True:
#		idx += height
#		# keep storing this
#		y_max[asn] = idx
#
#annotationsFile = "annotations.json"
#annotationCount = 1
#annotationList  = []
#if os.path.exists(annotationsFile):
#	with open(annotationsFile, 'r') as fh:
#		annotations = json.loads(fh.read())
#		for record in annotations:
#			start_ts = arrow.get(record["start"]).timestamp
#			end_ts   = arrow.get(record["end"]).timestamp
#			annotateLine = "set object " + str(annotationCount) + " rectangle from \"" + str(start_ts) + "\",0 to \"" + str(end_ts) + "\","+str(idx)+" fillcolor rgb \""+record["color"]+"\" fillstyle solid noborder"
#			annotationList.append(annotateLine)
#			print annotateLine
#
#			xFraction = -1
#			# if the annotation falls within the start/end range,
#			# add the label to the plot.
#			if end_ts >= START_T and start_ts <= END_T:
#				fullWidth        = END_T  - START_T
#				annotationMiddle = ((end_ts - start_ts) / 2) + start_ts
#				label_x          = (annotationMiddle - START_T) / float(fullWidth)
#				label_y          = -0.1
#				if   "align" in record and record["align"] == "right":
#					label_x = (start_ts - START_T) / float(fullWidth)
#				elif "align" in record and record["align"] == "left":
#					label_x = (end_ts - START_T) / float(fullWidth)
#				else:
#					record["align"] = "center"
#
#				annotateLine = "set label \""+record["name"]+"\" at graph "+str(label_x)+","+str(label_y) + " "+record["align"]+" font \",8\""
#				annotationList.append(annotateLine)
#
#			print annotateLine
#			annotationCount += 1
#		fh.close()
#
#tmpfile        = "/tmp/ccviz.%s.%s"        % (CC, pid)
#labelsfile     = "/tmp/ccviz.%s.labels.%s" % (CC, pid)
#timeseriesfile = "/tmp/ccviz.%s.ts.%s"     % (CC, pid)
#tmpplot        = "/tmp/plt.%s.%s"          % (CC, pid)
#outfile        = "%s.png"                  % (CC)
#
## print data to file
#with open(tmpfile, 'w') as fh:
#	for drow in data:
#		print >>fh, "%s %s %s %s %s %s %s" % tuple(drow)
#	fh.close()
#
#with open(labelsfile, 'w') as fh:
#	for asn in y_min.keys():
#		print >>fh, "%s %s %s" % ("AS"+asn, last_time_seen, ((y_max[asn]-y_min[asn])/2)+y_min[asn])
#	fh.close()
#
#with open(timeseriesfile, 'w') as fh:
#	total = 0
#	# [:-1] in the loop here is to skip the last '0' point, because
#	# the deltas calculated above will subtract everything that 'ends'
#	# at the end of time
#	timestamps = sorted(deltas.keys())
#	for ts in timestamps[:-1]:
#		total = total + deltas[ts]
#		print >>fh, ts, total
#	# put a dummy point at the end, to fill out gnuplot lines
#	# to the right-most side
#	print >>fh, timestamps[-1], total
#	fh.close()
#
#with open(tmpplot,'w') as fh:
#	print >>fh, """
#set term pngcairo size 1000,700
#
#set palette model RGB
#
## these functions are a bit ugly but they rip apart RGB values as strings
## and turn them into RGB values for plotting
#red(colorstring)    = colorstring[2:3]
#green(colorstring)  = colorstring[4:5]
#blue(colorstring)   = colorstring[6:7]
#hex2dec(hex)        = gprintf("%0.f",int('0X'.hex))
#rgb(r,g,b)          = 65536*int(r)+256*int(g)+int(b)
#hex2rgbvalue(color) = rgb( hex2dec(red(color)), hex2dec(green(color)), hex2dec(blue(color)) )
#
#unset key
#
#set grid xtics
#set border 3
#set tics nomirror
#
#set xdata time
#set timefmt "%s"
#
#set xtics 86400
#set xtics rotate
#set format x "'%y-%m-%d\\n%H:%M"
#set xrange [{START_TS}:{END_TS}]
#
#set ylabel "prefixes"
#
#set output "{OUTFILE}"
#
#set multiplot ti "Networks as seen in RIPE RIS"
#
## = lower plot =============================================
#set lmargin at screen 0.05
#set bmargin at screen 0.13
#set tmargin at screen 0.75
#
#set ytics format ""
#
#set style fill solid noborder
## boxxyerrors:  x y xlow xhigh ylow yhigh
#plot "{TMPFILE}" using 1:3:1:2:3:4:(hex2rgbvalue(stringcolumn(7))) w boxxyerrorbars lc rgb variable,\
#     "{LABELS}" using 2:3:1 with labels font ",8" left notitle
#
## = upper plot =============================================
#set bmargin at screen 0.8
#set tmargin at screen 0.95
#
#unset xlabel
#unset xtics
#set ylabel "#prefixes"
#set ytics format "%g"
#set yrange [0:*]
#
#{ANNOTATIONS}
#
#plot "{TIMESERIES}" using 1:2 w steps lw 1.5
#
#""".format( OUTFILE=outfile, TMPFILE=tmpfile, TIMESERIES=timeseriesfile, LABELS=labelsfile, START_TS=START_T, END_TS=END_T, ANNOTATIONS='\n'.join(annotationList) )
#
#
#os.system("gnuplot < %s" % tmpplot)
#print >>sys.stderr, "data tmpfile: %s" % (tmpfile)
#print >>sys.stderr, "plot tmpfile: %s" % (tmpplot)
#print >>sys.stderr, "output in %s"     % (outfile)
#
#pid = os.getpid()
