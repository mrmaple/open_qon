#!/usr/bin/env python
"""
$Id: search_reindex_tagged.py,v 1.2 2007/06/14 14:59:43 jimc Exp $
"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database, transaction_commit, commit_upgraded_versioneds
from qon.base import get_tagged_item_database
from qon.user import User
from qon.group import Group
from qon.wiki import Wiki, WikiPage
from qon.blog import Blog, BlogItem
from qon.util import get_oid
from qon import search

def _commit(i):
    commit_upgraded_versioneds()
    if i%500 == 0:
        print "Committing..."
        search.searchengine.commit_documents()

def index_tagged_item (item):
    # notify karma given does exactly what we
    # need for wiki pages, blogs, and users.
    search.searchengine.notify_karma_given(item)

def index_all_tagged ():
    tidb = get_tagged_item_database()

    i = 1
    for oid in tidb:
        item = get_oid(oid)
        index_tagged_item(item)
        _commit(i)
        i += 1
    _commit(0)

if __name__ == "__main__":

    # set batch mode to true so that we work synchronously and don't autocommit
    #search.searchengine.set_batch_mode(True)

    # open the ZODB database file    
    #db = open_database("file:/www/var/qon.fs")
    db = open_database()

    #--------------------------
    print ""
    print "Tagged items"
    print "---------------"  
    index_all_tagged()
    print ""

    print "Committing..."
    search.searchengine.commit_documents()

    # done
    transaction_commit()
    db.close()

