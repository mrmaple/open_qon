#!/usr/bin/env python
"""
$Id: populate_parent_blogitem_for_comments.py,v 1.3 2005/03/17 23:32:24 alex Exp $
Go through every blogitem and associate its comments with itself.
Meant to be run just once.

"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database, transaction_commit
from qon.user import User
from qon.group import Group
from qon.wiki import Wiki, WikiPage
from qon.blog import Blog, BlogItem
from qon import search

def do_all_user_blogitems():
    """ iterate through each user and index each news item """
    i = 1
    for userid, user in db.user_db.root.items():
        for bi in user.get_blog().get_items():
            print "%s) %s BlogItem: %s" % (i, userid, bi.title)
            bi.populate_parent_blogitem_for_comments()
            transaction_commit()
            i+=1

def do_all_group_blogitems():
    """ iterate through each group and index each discussion topic """
    i = 1
    for groupid, group in db.group_db.root.items():
        for bi in group.get_blog().get_items():
            print "%s) %s BlogItem: %s" % (i, groupid, bi.title)
            bi.populate_parent_blogitem_for_comments()
            transaction_commit()
            i+=1

if __name__ == "__main__":


    # open the ZODB database file    
    #db = open_database("file:/www/var/qon.fs")
    db = open_database()

    # do it
    print ""    
    print "User BlogItems"
    print "--------------"
    do_all_user_blogitems()
    print ""
    #--------------------------
    print ""
    print "Group BlogItems"
    print "---------------"    
    do_all_group_blogitems()
    print ""

    # done
    transaction_commit()
    db.close()
