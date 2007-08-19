#!/usr/bin/env python
"""
$Id: hot.py,v 1.2 2005/03/19 06:39:44 alex Exp $
Hot items experiment
"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database
from qon.user import User
from qon.group import Group
from qon.wiki import Wiki, WikiPage
from qon.blog import Blog, BlogItem
from datetime import datetime, timedelta
import qon.util

all_items = []  # (type, title, feedback, pageviews, readers, comments)
cutoff_date = datetime.utcnow() - timedelta(days=5)

def gather_all_user_blogitems():
    """ iterate through each user and index each news item """
    i=0
    for userid, user in db.user_db.root.items():
        for bi in user.get_blog().get_items():
            if bi.date > cutoff_date:
                print "%s) %s BlogItem: %s" % (i, userid, bi.title)
                (pageviews, readers) = bi.item_views()                
                all_items.append(("user news", bi.title, bi.get_karma_score(), pageviews, readers, len(bi.get_comments())))
                i+=1

def gather_all_group_blogitems():
    """ iterate through each group and index each discussion topic """
    i=0
    for groupid, group in db.group_db.root.items():
        for bi in group.get_blog().get_items():
            if bi.date > cutoff_date:            
                print "%s) %s BlogItem: %s" % (i, groupid, bi.title)
                (pageviews, readers) = bi.item_views()                                
                all_items.append(("discussion", bi.title, bi.get_karma_score(), pageviews, readers, len(bi.get_comments())))
                i+=1

def gather_all_group_wikipages():
    """ iterate through each group and index each wikipage """
    i=0
    for groupid, group in db.group_db.root.items():
        w = group.get_wiki()
        for wikipagename, wikipage in w.pages.items():
            first_revision = wikipage.versions[0]
            if first_revision.date > cutoff_date:
                print "%s) %s WikiPage: %s" % (i, groupid, first_revision.title)
                all_items.append(("wikipage", first_revision.title, wikipage.get_karma_score(), 0, 0, len(wikipage.get_comments())))
                i+=1
                
if __name__ == "__main__":

    # open the ZODB database file    
    #db = open_database("file:/www/var/qon.fs")
    db = open_database()

    # do it
    all_items = []

    print ""    
    print "User BlogItems"
    print "--------------"
    gather_all_user_blogitems()
    print ""
    #--------------------------

    print ""
    print "Group BlogItems"
    print "---------------"    
    gather_all_group_blogitems()
    print ""
    #--------------------------
    print ""
    print "Group WikiPages"
    print "---------------"  
    gather_all_group_wikipages()        
    print ""     

    feedback = qon.util.sort_list(all_items, lambda x: x[2])
    print "\nTop 10 By Feedback::\n"    
    for x in feedback[:10]:
        print " %s (%s) %s " % (x[2], x[0], x[1])

    pageviews = qon.util.sort_list(all_items, lambda x: x[3])
    print "\nTop 10 By Pageviews::\n"    
    for x in pageviews[:10]:
        print " %s (%s) %s " % (x[3], x[0], x[1])

    readers = qon.util.sort_list(all_items, lambda x: x[4])
    print "\nTop 10 By Readers::\n"    
    for x in readers[:10]:
        print " %s (%s) %s " % (x[4], x[0], x[1])

    comments = qon.util.sort_list(all_items, lambda x: x[5])
    print "\nTop 10 By Comments::\n"    
    for x in comments[:10]:
        print " %s (%s) %s " % (x[5], x[0], x[1])
        

    # done
    db.close()
