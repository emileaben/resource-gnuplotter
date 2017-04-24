#!/usr/bin/env python
import subprocess
import requests
from ripe.atlas.cousteau import ProbeRequest
import ujson as json
import sys
import re
import arrow
import argparse
import os

parser = argparse.ArgumentParser(description='Plot probe disconnects')
parser.add_argument('-s',dest='START', help='start time')
parser.add_argument('-e',dest='END', help='end time')
parser.add_argument('-c',dest='CC', help='country code (list)')
parser.add_argument('-a',dest='ASN', help='asn (list)')
parser.add_argument('-l',dest='LOC', help='location (ie. city)')
args = parser.parse_args()

## fix some to defaults
if not args.START and not args.END:
   now = arrow.utcnow()
   args.END   = now.timestamp
   args.START = now.replace(days=-1).timestamp
elif not args.START and args.END:
   # do 1 day
   end = arrow.get( args.END )
   args.END   = end.timestamp
   args.START = end.replace(days=-1).timestamp
elif args.START and not args.END:
   # do 1 day
   start = arrow.get( args.END )
   args.START = start.timestamp
   args.END   = start.replace(days=+1).timestamp
elif args.START and args.END:
   args.START = arrow.get( args.START ).timestamp
   args.END   = arrow.get( args.END   ).timestamp

filters = {}
if args.CC:
   filters['country_code'] = args.CC
elif args.ASN:
   filters['asn_v4'] = args.ASN
elif args.LOC:
   pass
   #TODO
else:
   print >>sys.stderr, "needs either country,asns or location"
   sys.exit(1)


probes = {}
pr_list = ProbeRequest(**filters)
oui2prb = {}
prb2oui = {}
oui_set = set()
for p in pr_list:
   probes[ p['id'] ] = p

'''
   if p['address_v6'] != None:
      #mre = re.match('\:(....)\:(..})ff\:fe..\:', p['address_v6'])
      mre = re.search(r'\:(\w\w)(\w\w)\:(\w\w)ff\:fe(\w\w)\:(\w\w)(\w\w)$', p['address_v6'])
      if mre:
         # U/L bit in group1
         g1 = int(mre.group(1),16)
         g2 = "%02x" % ( g1 & 0xfd )
         oui = "%s:%s:%s" % (g2, mre.group(2), mre.group(3))
         print oui
         # p = probe, v = vendor
         oui_set.add( oui )
         oui2prb.setdefault( oui, {'p': set(),'v': None})
         oui2prb[ oui ]['p'].add( p['id'] )
         prb2oui[ p['id'] ] = oui
for oui in oui2prb.keys():
   print "%s %s" % (oui, len( oui2prb[oui]['p'] ) )
   url = "http://macvendors.co/api/%s" % oui
   res = requests.get( url )
   j = res.json()
   if 'result' in j:
      if 'company' in j['result']:
         print j['result']['company']
'''

print >>sys.stderr, "init done!"

api_call="https://atlas.ripe.net/api/v2/measurements/7000/results?start=%s&stop=%s&format=txt" % ( args.START, args.END )
r = requests.get(api_call)
if r.status_code != 200:
	print >>sys.stderr, "Received status code "+str(r.status_code)+" from "+api_call
	sys.exit(-1)

p2series = {}

max_ts = None

for line in r.text.splitlines():
   d = json.loads( line )
   if d['prb_id'] not in probes:
      continue
   p = d['prb_id']
   ts = d['timestamp']
   if p in p2series:
      if d['event'] == 'disconnect':
         p2series[ p ][-1][1] = ts
      if d['event'] == 'connect':
         p2series[ p ].append( [ ts, None ] )
   else: 
      if d['event'] == 'disconnect':
         p2series[ p ] = [ [ args.START, ts ] ]
      if d['event'] == 'connect':
         p2series[ p ] = [ [ ts, None ] ]
   max_ts = ts

idx=0
datafile = "/tmp/.data.%s" % os.getpid()
print >>sys.stderr,"output in %s" % datafile
with open(datafile ,'w') as outf:
   for p,series in p2series.iteritems():
      ## fix end of time
      if series[-1][1] == None:
         #series[-1][1] = max_ts
         series[-1][1] = args.END
      for s in series:
         if s[1] == None:
            s[1] = s[0] # ??!?! 
         print >>outf, "%s %s %s %s" % ( s[0],idx, s[1], idx )
      idx+=1

### now create gnuplot file
plotfile = "/tmp/.plot.%s" % os.getpid()
print >>sys.stderr,"plotfile in %s" % plotfile
with open(plotfile, 'w') as outf:
   print >>outf, """
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

set title "RIPE Atlas probes in {CC} connected to RIPE Atlas infrastucture\\\n(only probes with disconnects shown)"

set ylabel "Probes"
set xlabel "Time (UTC)"

set output "{CC}.{START}.png"
plot "{PLFILE}" u 1:2:($3-$1):(0) w vectors nohead lc rgb "#4682b4"
   """.format( CC=args.CC, START=args.START, PLFILE=datafile )

## make sure local env is UTC
os.environ['TZ']='UTC'

os.system("gnuplot < %s" % plotfile )
os.system("open %s.%s.png" % (args.CC,args.START) )
