#!/usr/bin/env python
import subprocess
import requests
from ripe.atlas.cousteau import ProbeRequest
import ujson as json
import sys
import re
import arrow

now = arrow.utcnow()
END=now.timestamp
START=now.replace(days=-1)
CC=sys.argv[1]

START_TS = arrow.get(START).timestamp

probes = {}
filters = {'country_code': CC}
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

proc = subprocess.Popen("msmfetch 7000 %s %s" % (START,END), shell=True,stdout=subprocess.PIPE)

p2series = {}

max_ts = None

for line in iter(proc.stdout.readline,''):
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
         p2series[ p ] = [ [ START_TS, ts ] ]
      if d['event'] == 'connect':
         p2series[ p ] = [ [ ts, None ] ]
   max_ts = ts

idx=0
outfile = "%s.log" % CC
print >>sys.stderr,"output in %s" % outfile
with open(outfile ,'w') as outf:
   for p,series in p2series.iteritems():
      ## fix end of time
      if series[-1][1] == None:
         series[-1][1] = max_ts
      for s in series:
         if s[1] == None:
            s[1] = s[0] # ??!?! 
         print >>outf, "%s %s %s %s" % ( s[0],idx, s[1], idx )
      idx+=1
