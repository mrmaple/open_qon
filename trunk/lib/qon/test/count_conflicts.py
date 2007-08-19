#! /usr/bin/env python
"""
Counts the number of ConlictErrors by object id, and prints a sorted
list.

Usage::

  grep ConflictError /www/log/qon/error.log | python count_conflicts.py
  
"""

import sys
import re

def count_conflicts(f):
    """Count ConflictErrors in file f. Returns dictionary of oid -> count."""
    
    conflict_re = re.compile(r"ConflictError.*('\\x00.*')")
    
    oids = {}
    
    while 1:
        l = f.readline()
        if not l:
            break
            
        match = conflict_re.search(l)
        if match:
            oid = match.group(1)
            oids[oid] = oids.get(oid, 0) + 1

    return oids

def sort_counts(oids):
    """Given dictionary of oid->count, return a reverse sorted list of [(count, oid)...]"""
    
    bycount = []
    
    for oid, count in oids.iteritems():
        bycount.append((count, oid))
    
    bycount.sort()
    bycount.reverse()
    
    return bycount
    
    
if __name__ == '__main__':
    f = sys.stdin
    
    oids = count_conflicts(f)
    bycount = sort_counts(oids)
    
    for count, oid in bycount:
        print count, oid
