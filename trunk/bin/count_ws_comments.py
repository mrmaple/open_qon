#!/usr/bin/env python
"""
$Id: count_ws_comments.py,v 1.1 2004/12/30 22:53:28 alex Exp $
This script reports how many comments have been left on workspace
pages.  This will help us decide if we should keep the feature.
"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database
from qon.user import User
from qon.group import Group
from qon.wiki import Wiki, WikiPage
from qon.blog import Blog, BlogItem               

if __name__ == "__main__":

    # open the ZODB database file    
    #db = open_database("file:/www/var/qon.fs")
    db = open_database()

    """ iterate through each group and its wiki pages """
    total_num_pages = 0
    total_num_pages_with_comments = 0
    total_num_comments = 0
    
    for groupid, group in db.group_db.root.items():
        num_pages = 0
        num_pages_with_comments = 0
        num_comments = 0
        w = group.get_wiki()
        for wikipagename, wikipage in w.pages.items():
            total_num_pages += 1
            num_pages += 1
            c = len(wikipage.get_comments())
            if c > 0:
                total_num_pages_with_comments += 1
                num_pages_with_comments += 1
                total_num_comments += c
                num_comments += c
                # print "  [%s %s] number of comments: %s" % (groupid, wikipage.versions[-1].title, c)

        print " %s pages: %s, pages with comments: %s, comments: %s" % (groupid.ljust(32), str(num_pages).rjust(3), str(num_pages_with_comments).rjust(3), str(num_comments).rjust(3))

    print "\n[OVERALL] pages: %s, pages with comments: %s, comments: %s" % (total_num_pages, total_num_pages_with_comments, total_num_comments)

        
    # done
    db.close()
