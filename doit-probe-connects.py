#!/usr/bin/env python
import geocoder
import hashlib
import argparse
import re
import requests
from   ripe.atlas.cousteau import ProbeRequest
import subprocess
import sys
import os
import ujson as json
try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache
import arrow

def parse_args():
	parser = argparse.ArgumentParser(description='Plot probe disconnects')
	parser.add_argument('-s',dest='START', help='start time')
	parser.add_argument('-e',dest='END', help='end time')
	parser.add_argument('-c',dest='CC', help='country code (list)')
	parser.add_argument('-a',dest='ASN', help='asn (list)')
	parser.add_argument('-l',dest='LOC', help='location (ie. city)')
	parser.add_argument('-r',dest='RADIUS', help='radius around location (together with -l). default 50km')
	parser.add_argument('-o',dest='SORT_ORDER', help='sort order to plot by. default: asn. other options: probe_id')
	parser.add_argument('--color-by',dest='COLOR_BY', help='property to color lines by. default: asn. other options: tag:<tag>,<tag>')
	parser.add_argument('--annotate', dest='ANNOTATE_FN', help='JSON file with annotations to mark on the timeline', default="")
	args = parser.parse_args()

	## fix some to defaults
	now = arrow.utcnow()
	if not args.START and not args.END:
		args.END   = now.timestamp
		args.START = now.replace(days=-7).timestamp
	elif not args.START and args.END:
		# do 7 day
		end = arrow.get( args.END )
		args.END   = end.timestamp
		args.START = end.replace(days=-7).timestamp
	elif args.START and not args.END:
		start = arrow.get( args.START )
		args.START = start.timestamp
		args.END   = now.timestamp
	elif args.START and args.END:
		args.START = arrow.get( args.START ).timestamp
		args.END   = arrow.get( args.END   ).timestamp

	if not args.RADIUS:
		args.RADIUS=50

	if not args.SORT_ORDER:
		args.SORT_ORDER='asn'

	if not args.COLOR_BY:
		args.COLOR_BY='asn'

	selector_lst = [] # contains textual desc of selector
	filters = {}
	if args.CC:
		filters['country_code'] = args.CC
		selector_lst.append( "country:%s" % ( args.CC, ) )
	if args.ASN:
		filters['asn_v4'] = args.ASN
		selector_lst.append( "asn:%s" % ( args.ASN, ) )
	if args.LOC:
		ll = locstr2latlng( args.LOC )
		filters['radius'] = '%s,%s:%s' % (ll[0],ll[1],args.RADIUS)
		selector_lst.append( "location:%s" % ( args.LOC, ) )
	## args asn cc loc can be combined, but need at least 1 of them
	if not args.CC and not args.ASN and not args.LOC:
		print( "needs either country,asns or location" )
		sys.exit(1)

	print( "times: %s - %s " % ( args.START, args.END ) , file=sys.stderr )
	print( "filters: %s" % ( filters ) , file=sys.stderr )

	probes = {}
	pr_list = ProbeRequest(**filters)
	for p in pr_list:
		probes[ p['id'] ] = p

	return (args, selector_lst, probes)


def locstr2latlng( locstring ):
        g = geocoder.geonames(locstring, key='emileaben')
        return g.latlng

def parse_annotations(args, idx):
	annotationCount = 1
	annotationList  = []
	if os.path.exists(args.ANNOTATE_FN):
		with open(args.ANNOTATE_FN, 'r') as fh:
			annotations = json.loads(fh.read())
			for record in annotations:
				start_ts = arrow.get(record["start"]).timestamp
				end_ts   = arrow.get(record["end"]).timestamp
				annotateLine = "set object " + str(annotationCount) + " rectangle from \"" + str(start_ts) + "\",-0.2 to \"" + str(end_ts) + "\","+str(idx)+" fillcolor rgb \""+record["color"]+"\" fillstyle solid noborder"
				annotationList.append(annotateLine)
				print(annotateLine)

				# I'm using graph coordinates for the y-axis, so I need
				# to determine the midpoint on the graph coordinate
				# system for the x axis.
				# we know: xrange, annotation range
				xfraction = -1
				annotationMiddle = end_ts - ((end_ts - start_ts) / 2)
				if annotationMiddle >= args.START and annotationMiddle <= args.END:
					fullWidth = args.END - args.START
					xFraction = (annotationMiddle - args.START) / float(fullWidth)

				label_y = 0.95
				annotateLine = "set label \""+record["name"]+"\" at graph "+str(xFraction)+","+str(label_y) + " center font \",8\""
				annotationList.append(annotateLine)

				print(annotateLine)
				annotationCount += 1
			fh.close()
	return '\n'.join(annotationList)

def none2int( val ):
	if val is None:
		return 0
	else:
		return int( val )

def do_gnuplot(args, selector_lst, probes):
	idx = 0
	datafile = "/tmp/.data.%s" % os.getpid()
	ykeys = []

	### sort order
	pr_sorted_list = []
	if args.SORT_ORDER == 'probe_id':
		pr_sorted_list = sorted( probes.keys(), reverse=True )
	else:
	# default
		pr_sorted_list = sorted( probes.keys(), key=lambda x: none2int( probes[x]['asn_v4'] ), reverse=True )

	print( "data in %s" % datafile, file=sys.stderr )
	with open(datafile ,'w') as outf:
		for prb_id in pr_sorted_list:
			p = probes[ prb_id ]
			## color by. TODO different options
			## added 'aap' here because without 7018 and 7922 have identical colors
			rgb = '#4682b4'
			if args.COLOR_BY.startswith('tag:'):
				color_tags = args.COLOR_BY[4:].split(',')
				for probe_tag in p['tags']:
					if probe_tag['slug'] in color_tags:
						rgb  = '#ff8c00'
			else:
				hashable = "aap%s" % p['asn_v4']
				hashable = hashable.encode('utf-8')
				rgb = "#" + hashlib.md5( hashable ).hexdigest()[0:6]
			if not 'series' in p and p['status']['id'] == 1:
				p['series'] = [ [ args.START, args.END ] ]
			elif not 'series' in p:
				continue

			series = p['series']
			ykeys.append( '"%s/AS%s" %s' % (prb_id,p['asn_v4'],idx) )

			## fix end of time
			if series[-1][1] == None:
				series[-1][1] = args.END
			for s in series:
				if s[1] == None:
					s[1] = s[0] # ??!?! 
				print( "%s %s %s %s %s" % ( s[0], idx, s[1], idx, rgb ) , file=outf )
			idx+=1

	annotations_str = parse_annotations(args, idx)

	current_time=arrow.utcnow().timestamp

	img_y_size = max( 600, idx*10)

	gpfile = "/tmp/.plot.%s" % os.getpid()
	ytics = ",".join( ykeys )
	fname = ".".join(map(lambda x: x.replace('/','_') and x.replace(',','_') and x.replace(':','_') , selector_lst ) ) + ".png"
	print( "gnuplot script in %s" % gpfile , file=sys.stderr )
	with open(gpfile, 'w') as outf:
		print ("""
set term pngcairo size 1000,{IMG_Y_SIZE}

set palette model RGB

# these functions are a bit ugly but they rip apart RGB values as strings
# and turn them into RGB values for plotting
red(colorstring)    = colorstring[2:3]
green(colorstring)  = colorstring[4:5]
blue(colorstring)   = colorstring[6:7]
hex2dec(hex)        = gprintf("%0.f",int('0X'.hex))
rgb(r,g,b)          = 65536*int(r)+256*int(g)+int(b)
hex2rgbvalue(color) = rgb( hex2dec(red(color)), hex2dec(green(color)), hex2dec(blue(color)) )

set grid xtics
set tics nomirror
set border 3
unset key

set xdata time
set timefmt "%s"
set format x "'%y-%m-%dT%H:%M"
set yrange [-0.2:{YMAX}]
set xtics rotate
set ytics ({YTICS})

set title "RIPE Atlas probes status {SELECTOR_STR}"

set arrow from {CURRENT_TS},-0.2 to {CURRENT_TS},graph({CURRENT_TS},1) nohead lt 0 lw 2

{ANNOTATIONS}

set ylabel "Probe ID/ASN"
set xlabel "Time (UTC)"

set output "{FNAME}"
plot "{PLFILE}" u 1:2:($3-$1):(0):(hex2rgbvalue(stringcolumn(5))) w vectors nohead lw 6 lc rgb variable
		""".format( FNAME=fname, CURRENT_TS=current_time, YTICS=ytics, CC=args.CC, START=args.START, PLFILE=datafile, SELECTOR_STR= "(" + ' '.join( selector_lst ) + ")", YMAX=idx, ANNOTATIONS=annotations_str, IMG_Y_SIZE=img_y_size ), file=outf )

	print( "output in %s" % fname , file=sys.stderr )

	## make sure local env is UTC
	os.environ['TZ']='UTC'
	os.system("gnuplot < %s" % gpfile )


def main():
	(args, selector_lst, probes) = parse_args()
	print("init done!", file=sys.stderr )

	api_call="https://atlas.ripe.net/api/v2/measurements/7000/results?start=%s&stop=%s&format=txt" % ( args.START, args.END )
	print("api url: %s" % api_call , file=sys.stderr )
	r = requests.get(api_call)
	if r.status_code != 200:
		print >>sys.stderr, "Received status code "+str(r.status_code)+" from "+api_call
		sys.exit(-1)

	max_ts = None

	for line in r.text.splitlines():
		d = json.loads( line )
		if d['prb_id'] not in probes:
			continue
		pid = d['prb_id']
		ts = d['timestamp']
		if 'series' in probes[ pid ]:
			if d['event'] == 'disconnect':
				probes[ pid ]['series'][-1][1] = ts
			if d['event'] == 'connect':
				probes[ pid ]['series'].append( [ ts, None ] )
		else: 
			if d['event'] == 'disconnect':
				probes[ pid ]['series'] = [ [ args.START, ts ] ]
			if d['event'] == 'connect':
				probes[ pid ]['series'] = [ [ ts, None ] ]
		max_ts = ts

	##TODO ordering of series

	do_gnuplot(args, selector_lst, probes)

if __name__ == '__main__':
	main()

