#!/usr/bin/env python

import argparse
import arrow
import re
import requests
from   ripe.atlas.cousteau import ProbeRequest
import subprocess
import sys
import os
import ujson as json

def parse_args():
	parser = argparse.ArgumentParser(description='Plot probe disconnects')
	parser.add_argument('-s',dest='START', help='start time')
	parser.add_argument('-e',dest='END', help='end time')
	parser.add_argument('-c',dest='CC', help='country code (list)')
	parser.add_argument('-a',dest='ASN', help='asn (list)')
	parser.add_argument('-l',dest='LOC', help='location (ie. city)')
	parser.add_argument('-r',dest='RADIUS', help='radius around location (together with -l). default 50km')
	parser.add_argument('--annotate', dest='ANNOTATE_FN', help='JSON file with annotations to mark on the timeline')
	args = parser.parse_args()

	## fix some to defaults
	now = arrow.utcnow()
	if not args.START and not args.END:
		args.END   = now.timestamp
		args.START = now.replace(days=-1).timestamp
	elif not args.START and args.END:
		# do 1 day
		end = arrow.get( args.END )
		args.END   = end.timestamp
		args.START = end.replace(days=-1).timestamp
	elif args.START and not args.END:
		start = arrow.get( args.START )
		args.START = start.timestamp
		args.END   = now.timestamp
	elif args.START and args.END:
		args.START = arrow.get( args.START ).timestamp
		args.END   = arrow.get( args.END   ).timestamp

	if not args.RADIUS:
		args.RADIUS=50

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
		print >>sys.stderr, "needs either country,asns or location"
		sys.exit(1)

	print >>sys.stderr, "times: %s - %s " % ( args.START, args.END )
	print >>sys.stderr, "filters: %s" % ( filters )

	probes = {}
	pr_list = ProbeRequest(**filters)
	for p in pr_list:
		probes[ p['id'] ] = p

	return (args, selector_lst, probes)

def locstr2latlng( locstring ):
	if 1: #try:
		geocode_url = "http://maps.googleapis.com/maps/api/geocode/json?address=%s&sensor=false" % locstring
		r = requests.get( geocode_url )
		resp = r.json()
		#print >>sys.stderr, "%s" % (resp)
		ll = resp['results'][0]['geometry']['location']
		return ( ll['lat'], ll['lng'] )
	#except:
	#   print "could not determine lat/long for '%s'" % ( locstring )

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
				print annotateLine

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

				print annotateLine
				annotationCount += 1
			fh.close()
	return '\n'.join(annotationList)

def do_gnuplot(args, selector_lst, probes):
	idx = 0
	datafile = "/tmp/.data.%s" % os.getpid()
	ykeys = []
	print >>sys.stderr,"data in %s" % datafile
	with open(datafile ,'w') as outf:
		for k,p in probes.iteritems():
			if not 'series' in p and p['status']['id'] == 1:
				p['series'] = [ [ args.START, args.END ] ]
			elif not 'series' in p:
				continue

			series = p['series']
			ykeys.append( '"%s/AS%s" %s' % (k,p['asn_v4'],idx) )

			## fix end of time
			if series[-1][1] == None:
				series[-1][1] = args.END
			for s in series:
				if s[1] == None:
					s[1] = s[0] # ??!?! 
				print >>outf, "%s %s %s %s" % ( s[0], idx, s[1], idx )
			idx+=1

	annotations_str = parse_annotations(args, idx)

	current_time=arrow.utcnow().timestamp

	gpfile = "/tmp/.plot.%s" % os.getpid()
	ytics = ",".join( ykeys )
	fname = ".".join(map(lambda x: x.replace('/','_') and x.replace(',','_') and x.replace(':','_') , selector_lst ) ) + ".png"
	print >>sys.stderr,"gnuplot script in %s" % gpfile
	with open(gpfile, 'w') as outf:
		print >>outf, """
set term pngcairo size 1000,600

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
plot "{PLFILE}" u 1:2:($3-$1):(0) w vectors nohead lw 5 lc rgb "#4682b4"
		""".format( FNAME=fname, CURRENT_TS=current_time, YTICS=ytics, CC=args.CC, START=args.START, PLFILE=datafile, SELECTOR_STR= "(" + ' '.join( selector_lst ) + ")", YMAX=idx, ANNOTATIONS=annotations_str )

	print >>sys.stderr, "output in %s" % fname

	## make sure local env is UTC
	os.environ['TZ']='UTC'
	os.system("gnuplot < %s" % gpfile )


def main():
	(args, selector_lst, probes) = parse_args()
	print >>sys.stderr, "init done!"

	api_call="https://atlas.ripe.net/api/v2/measurements/7000/results?start=%s&stop=%s&format=txt" % ( args.START, args.END )
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

