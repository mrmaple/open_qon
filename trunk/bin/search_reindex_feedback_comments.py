#!/usr/bin/env python
"""
$Id: search_reindex_feedback_comments.py,v 1.1 2006/03/01 08:29:08 alex Exp $
Go through every searchable object in the db and ask search.py
to re-index them.
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

def index_all_user_blogitems():
    """ iterate through each user and index each news item """
    i = 1
    j = 1
    for userid, user in db.user_db.root.items():
        for bi in user.get_blog().get_items():
            print "%s) %s BlogItem: %s" % (i, userid, bi.title)
            # search.searchengine.notify_new_blog_item(bi)
            _commit(i)
            i += 1
            for c in bi.get_comments():
                if c.get_karma_score() != 0:
                    search.searchengine.notify_edited_blog_comment(c)
                    _commit(i+j)
                    j += 1
    _commit(0)
    
def index_all_group_blogitems():
    """ iterate through each group and index each discussion topic """
    i = 1
    j = 1
    for groupid, group in db.group_db.root.items():
        for bi in group.get_blog().get_items():
            print "%s) %s BlogItem: %s" % (i, groupid, bi.title)
            # search.searchengine.notify_new_blog_item(bi)
            _commit(i)
            i += 1                    
            for c in bi.get_comments():
                if c.get_karma_score() != 0:                
                    search.searchengine.notify_edited_blog_comment(c)
                    _commit(i+j)
                    j += 1
    _commit(0)
    
if __name__ == "__main__":

    # set batch mode to true so that we work synchronously and don't autocommit
    search.searchengine.set_async(False)
    search.searchengine.set_commit_immediately(False)
    # search.searchengine.set_always_try_deleting_first(True)   # set True on re-runs of this script when you're only indexing part of the whole

    # open the ZODB database file    
    #db = open_database("file:/www/var/qon.fs")
    db = open_database()

    # do it
    print ""    
    print "User BlogItems"
    print "--------------"
    index_all_user_blogitems()
    print ""
    #--------------------------
    print ""
    print "Group BlogItems"
    print "---------------"    
    index_all_group_blogitems()
    print ""

    print "Committing..."
    search.searchengine.commit_documents()

    # done
    transaction_commit()
    db.close()
