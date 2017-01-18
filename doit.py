#!/usr/bin/env python
import subprocess
import requests
from ripe.atlas.cousteau import Probe
import ujson as json

START="2016-06-01"
END="2016-06-08"
CC='KE'

probes = {}
grrr_why_are_parameters_not_standardised = END.replace('-','')
r = requests.get("https://atlas.ripe.net/api/v1/probe-archive/?format=json&day=%s" % ( grrr_why_are_parameters_not_standardised, ) )
rdata = r.json()
for p in rdata['objects']:
   probes[ p['id'] ] = p

proc = subprocess.Popen("msmfetch 7000 %s %s" % (START,END), shell=True,stdout=subprocess.PIPE)

BATCH_SIZE=120

series = {}

DUMMY_PRB = {
   'asn_v4': -1,
   'asn_v6': -1,
   'country_code': 'XX'
}

for line in iter(proc.stdout.readline,''):
   d = json.loads( line )
   try:
      prb = probes[ d['prb_id'] ]
   except:
      ## dummy probe
      prb = DUMMY_PRB
   if prb['country_code'] != CC:
      continue
   # 'timestamp' and 'event'
   ts = d['timestamp']
   ts -= ts % BATCH_SIZE
   series.setdefault( ts, [0,0] )
   if d['event'] == 'connect':
      series[ts][0] += 1
   elif d['event'] == 'disconnect':
      series[ts][1] += 1
   else:
      print >>sys.stderr, "CANT HAPPEN"

ts_sorted = sorted( series.keys() )
for ts in ts_sorted:
   print "%s %s %s" % ( ts, series[ts][0], series[ts][1] )
