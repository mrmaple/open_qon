#!/usr/local/bin/python
"""
$Id: touch-all-objects.py,v 1.4 2005/03/26 05:22:05 pierre Exp $

Various regular maintenance.
"""
from dulcinea import site_util
from qon.base import open_database, get_database, close_database, \
    get_session_manager, get_user_database, get_list_database, \
    transaction_commit, get_group_database

site = 'qon'
config = site_util.get_config()

def iterate_touch(max=10**9):
    db = get_database()
    count = 0
    types = {}
    for obj in db.iterate():

        t = type(obj)
        types[t] = types.get(t, 0) + 1

        # force unghost - if you don't do this,
        # setting _p_changed has no effect
        if hasattr(obj, 'foo'):
            pass

        obj._p_changed = 1
        assert obj._p_changed
        
        if count % 1000 == 0:
            transaction_commit(None, 'Touch')
            print 'Touched %d objects' % count

        count += 1

        if count == max:
            break

    transaction_commit(None, 'Touch')

    bytype = []
    for t, c in types.iteritems():
        bytype.append((c, t))
    
    bytype.sort()
    bytype.reverse()
    for c, t in bytype:
        print '%8d    %s' % (c, t)

def iterate_id(max=10**9):

    db = get_database()
    count = 0
    types = {}
    for obj in db.iterate():
        t = type(obj)
        types[t] = types.get(t, 0) + 1
        count += 1
        
        if count == max:
            break
    
    bytype = []
    for t, c in types.iteritems():
        bytype.append((c, t))
    
    bytype.sort()
    bytype.reverse()
    for c, t in bytype:
        print '%8d    %s' % (c, t)

def iterate_counts_sizes(path):
    """Count and display the number and total size of every class of objects.
    
    NOTE: For accurate results, run on a packed db -- otherwise, objects will
    be counted multiple times.
    """
    
    from ZODB.FileStorage import FileIterator
    from ZODB.FileStorage.fsdump import get_pickle_metadata
    
    counts = {}
    sizes = {}
    
    fiter = FileIterator(path)
    for trans in fiter:
        for rec in trans:
            if rec.data:
                modname, classname = get_pickle_metadata(rec.data)
                counts[classname] = counts.get(classname, 0) + 1
                sizes[classname] = sizes.get(classname, 0) + len(rec.data)
    
    bycount = []
    for classname, c in counts.iteritems():
        bycount.append((c, classname))
    del counts
    
    bycount.sort()
    bycount.reverse()
    
    bysize = []
    for classname, s in sizes.iteritems():
        bysize.append((s, classname))
    
    bysize.sort()
    bysize.reverse()
    
    print "By object count"
    for c, name in bycount:
        print '%10d    %s' % (c, name)
    
    print '\n\nBy size'
    for s, name in bysize:
        print '%10d    %s' % (s, name)
        

def main():
    #open_database()  # ZEO
    open_database('file:/www/var/qon.fs')
    #iterate_touch()
    #iterate_id()
    iterate_counts_sizes('/www/var/qon.fs')
    close_database()

if __name__ == '__main__':
    main()
    