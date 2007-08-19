#!/opt/local/bin/python

"""Grossly hacked Zope code to find references to a given list of OIDs.

Usage::

  Immediately below this comment, create a list of packed OIDs to search for,
  then run:
  
  python findrefs.py /www/var/qon.fs

"""

search_oids = [
    '\x00\x00\x00\x00\x00\n\xbc$',
    '\x00\x00\x00\x00\x00\x01\xa1#',
    '\x00\x00\x00\x00\x00\x0c\xc3\x99',
]


##############################################################################
#
# Copyright (c) 2002 Zope Corporation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE
#
##############################################################################

"""Check FileStorage for dangling references.

usage: fsrefs.py [-v] data.fs

fsrefs.py checks object sanity by trying to load the current revision of
every object O in the database, and also verifies that every object
directly reachable from each such O exists in the database.

It's hard to explain exactly what it does because it relies on undocumented
features in Python's cPickle module:  many of the crucial steps of loading
an object are taken, but application objects aren't actually created.  This
saves a lot of time, and allows fsrefs to be run even if the code
implementing the object classes isn't available.

A read-only connection to the specified FileStorage is made, but it is not
recommended to run fsrefs against a live FileStorage.  Because a live
FileStorage is mutating while fsrefs runs, it's not possible for fsrefs to
get a wholly consistent view of the database across the entire time fsrefs
is running; spurious error messages may result.

fsrefs doesn't normally produce any output.  If an object fails to load, the
oid of the object is given in a message saying so, and if -v was specified
then the traceback corresponding to the load failure is also displayed
(this is the only effect of the -v flag).

Three other kinds of errors are also detected, when an object O loads OK,
and directly refers to a persistent object P but there's a problem with P:

 - If P doesn't exist in the database, a message saying so is displayed.
   The unsatisifiable reference to P is often called a "dangling
   reference"; P is called "missing" in the error output.

 - If the current state of the database is such that P's creation has
   been undone, then P can't be loaded either.  This is also a kind of
   dangling reference, but is identified as "object creation was undone".

 - If P can't be loaded (but does exist in the database), a message saying
   that O refers to an object that can't be loaded is displayed.

fsrefs also (indirectly) checks that the .index file is sane, because
fsrefs uses the index to get its idea of what constitutes "all the objects
in the database".

Note these limitations:  because fsrefs only looks at the current revision
of objects, it does not attempt to load objects in versions, or non-current
revisions of objects; therefore fsrefs cannot find problems in versions or
in non-current revisions.
"""

import cPickle
import cStringIO
import traceback
import types

from ZODB.FileStorage import FileStorage
from ZODB.TimeStamp import TimeStamp
from ZODB.utils import u64, oid_repr
from ZODB.FileStorage.fsdump import get_pickle_metadata
from ZODB.POSException import POSKeyError

VERBOSE = 0

# So full of undocumented magic it's hard to fathom.
# The existence of cPickle.noload() isn't documented, and what it
# does isn't documented either.  In general it unpickles, but doesn't
# actually build any objects of user-defined classes.  Despite that
# persistent_load is documented to be a callable, there's an
# undocumented gimmick where if it's actually a list, for a PERSID or
# BINPERSID opcode cPickle just appends "the persistent id" to that list.
# Also despite that "a persistent id" is documented to be a string,
# ZODB persistent ids are actually (often? always?) tuples, most often
# of the form
#     (oid, (module_name, class_name))
# So the effect of the following is to dig into the object pickle, and
# return a list of the persistent ids found (which are usually nested
# tuples), without actually loading any modules or classes.
# Note that pickle.py doesn't support any of this, it's undocumented code
# only in cPickle.c.
def get_refs(pickle):
    # The pickle is in two parts.  First there's the class of the object,
    # needed to build a ghost,  See get_pickle_metadata for how complicated
    # this can get.  The second part is the state of the object.  We want
    # to find all the persistent references within both parts (although I
    # expect they can only appear in the second part).
    f = cStringIO.StringIO(pickle)
    u = cPickle.Unpickler(f)
    u.persistent_load = refs = []
    u.noload() # class info
    u.noload() # instance state info
    return refs

# There's a problem with oid.  'data' is its pickle, and 'serial' its
# serial number.  'missing' is a list of (oid, class, reason) triples,
# explaining what the problem(s) is(are).
def report(oid, data, serial, missing):
    from_mod, from_class = get_pickle_metadata(data)
    if len(missing) > 1:
        plural = "s"
    else:
        plural = ""
    ts = TimeStamp(serial)
    print "oid %s %s.%s" % (hex(u64(oid)), from_mod, from_class)
    print "last updated: %s, tid=%s" % (ts, hex(u64(serial)))
    print "refers to object%s:" % plural
    for oid, info, reason in missing:
        if isinstance(info, types.TupleType):
            description = "%s.%s" % info
        else:
            description = str(info)
        print "\toid %s %s: %r" % (oid_repr(oid), reason, description)
    print

def main(path, search_oids):
    fs = FileStorage(path, read_only=1)

    # Set of oids in the index that failed to load due to POSKeyError.
    # This is what happens if undo is applied to the transaction creating
    # the object (the oid is still in the index, but its current data
    # record has a backpointer of 0, and POSKeyError is raised then
    # because of that backpointer).
    undone = {}

    # Set of oids that were present in the index but failed to load.
    # This does not include oids in undone.
    noload = {}

    for oid in fs._index.keys():
        try:
            data, serial = fs.load(oid, "")
        except (KeyboardInterrupt, SystemExit):
            raise
        except POSKeyError:
            undone[oid] = 1
        except:
            if VERBOSE:
                traceback.print_exc()
            noload[oid] = 1

    inactive = noload.copy()
    inactive.update(undone)

    for oid in fs._index.keys():
        if oid in inactive:
            continue
        data, serial = fs.load(oid, "")
        refs = get_refs(data)
        missing = [] # contains 3-tuples of oid, klass-metadata, reason
        for info in refs:
            try:
                ref, klass = info
            except (ValueError, TypeError):
                # failed to unpack
                ref = info
                klass = '<unknown>'

            if ref in search_oids:
                report(oid, data, serial, [(ref, klass, "searching for")])
                
            if ref not in fs._index:
                missing.append((ref, klass, "missing"))
            if ref in noload:
                missing.append((ref, klass, "failed to load"))
            if ref in undone:
                missing.append((ref, klass, "object creation was undone"))
        if missing:
            report(oid, data, serial, missing)

if __name__ == "__main__":
    import sys
    import getopt

    opts, args = getopt.getopt(sys.argv[1:], "v")
    for k, v in opts:
        if k == "-v":
            VERBOSE += 1

    path,  = args
    print "searching for oids: %s" % [hex(u64(search_oid)) for search_oid in search_oids]
    main(path, search_oids)
