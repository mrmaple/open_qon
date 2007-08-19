#!/usr/bin/env python
"""
$Id: search_reindex_polls.py,v 1.1 2005/05/19 23:18:15 alex Exp $
"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database, transaction_commit, commit_upgraded_versioneds
from qon.user import User
from qon.group import Group
from qon.wiki import Wiki, WikiPage
from qon.blog import Blog, BlogItem
from qon import search

def _commit(i):
    commit_upgraded_versioneds()
    if i%500 == 0:
        print "Committing..."
        search.searchengine.commit_documents()

def index_all_group_polls():
    """ iterate through each group and index each poll """
    i = 1
    for groupid, group in db.group_db.root.items():
        for p in group.polls.get_polls():
            print "%s) %s Poll: %s" % (i, groupid, p.title)
            search.searchengine.notify_poll_vote(p)
            _commit(i)
            i += 1                    
    _commit(0)

if __name__ == "__main__":

    # set batch mode to true so that we work synchronously and don't autocommit
    search.searchengine.set_batch_mode(True)

    # open the ZODB database file    
    #db = open_database("file:/www/var/qon.fs")
    db = open_database()

    #--------------------------
    print ""
    print "Group Polls"
    print "---------------"  
    index_all_group_polls()
    print ""

    print "Committing..."
    search.searchengine.commit_documents()

    # done
    transaction_commit()
    db.close()
