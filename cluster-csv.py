#!/usr/bin/env python
'''
 prototype implementation of a clustering algorithm for timeline data
'''
import sys
import json
import arrow

step=1800

mini = None


def load( inp ):
   global mini
   maxi = None
   series={}
   for line in inp:
      line = line.rstrip('\n')
      fields = line.split(' ')
      #(ts,prb_id,idx,fail_pct) = line.split('\s+')
      if len(fields) != 5: continue
      (ts,prb_id,idx,count) = map(int,fields[0:4])
      fail_pct = float( fields[4] )
      if mini == None or mini > ts: mini = ts
      if maxi == None or maxi < ts: maxi = ts
      if not prb_id in series:
         series[prb_id] = {}
      series[prb_id][ ts ] = fail_pct
   nseries = {}  
   for prb_id in series:
      slist = []
      ssum = 0
      for ts in range(mini,maxi+1,step):
         if ts in series[ prb_id ]:
            slist.append( series[ prb_id ][ ts ] )
            ssum += series[ prb_id ][ ts ]
         else:
            slist.append( None )
      nseries[prb_id] = {
         'list': slist,
         'sum': ssum
      }
   return nseries

def distance( ary1, ary2 ):
   dist = 0
   max_dist = 100 ## max distance per point
   l = len(ary1)
   if l != len(ary2):
      raise ValueError("Arrays must be same length")
   for idx, val1 in enumerate( ary1 ):
      val2 = ary2[idx]
      if val1 != None and val2 != None:
         dist += abs( val1 - val2 )
      elif val1 == None or val2 == None:
         # uncertainty penalty? @@TODO normalise by min/max value? currently we know that is 0-100
         dist +=  max_dist *1.0 / l
   return dist

series = load( sys.stdin )
probe_ids = series.keys()
probe_ids.sort( key=lambda x:series[x]['sum'] )

this_id = probe_ids.pop(0)
out_ids = [ this_id ]
while len( probe_ids ) > 0:
   min_distance = None
   min_idx=None
   min_prb_id=None
   for idx,prb_id in enumerate( probe_ids ):
      this_distance = distance( series[ prb_id ]['list'] , series[ this_id ]['list'] )
      if min_distance == None or this_distance < min_distance:
         min_distance = this_distance
         min_idx = idx
         min_prb_id = prb_id
   # remove the min_idx from list
   out_ids.append( min_prb_id )
   del( probe_ids[ min_idx ] ) 
   this_id = min_prb_id

## now output clustered         
p_idx=0
print "date,prb_id,bucket,count"
for prb_id in out_ids:
   for idx,val in enumerate(series[ prb_id ]['list']):
      ts = mini + idx*step
      if val != None:
         print "%s,%s,%s,%s" % (arrow.get(ts).format("YYYY-MM-DD HH:mm"), prb_id, p_idx, val)
   p_idx += 1
