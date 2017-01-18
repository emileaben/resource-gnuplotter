#!/usr/bin/env python
import subprocess
import os
import time
import sys
import arrow
from tempfile import mkstemp

### TODO in radix

## do decent optparse


asns = []
countries = []
START_T = arrow.get(sys.argv[1]).timestamp
END_T = arrow.get(sys.argv[2]).timestamp
for arg in sys.argv[3:]:
   asns.append( arg )

idx=0
pfx2idx = {}
idx2pfx = {}
data = []
cbtics = []

for aidx,asn in enumerate( asns ):
   cbtics.append( '"%s" %s' % (asn, aidx) )
   cmd = "ido +minpwr 10 +M +oc +t +dc RIS_V_CC %s" % (asn)
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
         start = int(tparts[1])
         end = int(tparts[3])
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
      if has_data == True:
         pfx2idx[ pfx ] = idx
         idx2pfx[ idx ] = pfx
         idx += 1
   idx += 3 #for each asn

pid = os.getpid()
tmpfile = "/tmp/ccviz.%s" % pid
tmpplot = "/tmp/plt.%s" % pid

# print data to file
with open(tmpfile,'w') as fh:
   for drow in data:
      print >>fh, "%s %s %s %s" % tuple(drow)

## ASN tics
cbtics_txt = ','.join( cbtics )
print cbtics_txt

with open(tmpplot,'w') as fh:
   print >>fh, """
set term pdf
set term pdf
set grid xtics
set palette model RGB
#set palette model RGB defined (0 "green", 1 "dark-green", 2 "yellow", 3 "dark-yellow", 4 "red", 5 "dark-red", 6 "orange")
set title "Networks in Gambia as seen in RIPE RIS/BGP (2016-11-30)"
set palette maxcolors 7
set palette model RGB defined (0 "#3A7728", 1 "#0C1C8C", 2 "#CE1126", 3 "orange", 4 "purple", 5 "grey", 6 "yellow")
set output "t.pdf"
set timefmt "%%s"
set xdata time
unset key
set xlabel "time"
set ylabel "prefixes"
set xrange ["%d":"%d"]
set ytics format ""
set cbtics (%s)
set rmargin at screen 0.80
set cbtics font ",9"
plot "%s" u 1:2:3:(0):4 w vectors nohead lw 3 lc palette
""" % ( START_T, END_T, cbtics_txt, tmpfile )

os.system("gnuplot < %s" % tmpplot)
print >>sys.stderr, "data tmpfile: %s" % (tmpfile)
print >>sys.stderr, "plot tmpfile: %s" % (tmpplot)
print >>sys.stderr, "output in t.pdf"
         

