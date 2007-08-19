#!/usr/bin/env python
"""
$Id: report_blogitem_stats.py,v 1.1 2006/01/24 07:39:04 alex Exp $
Go through pretty much every object in the DB to gather 'first use' date
about every user.
"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database, transaction_commit, get_list_database
from qon.user import User
from qon.group import Group
from qon.wiki import Wiki, WikiPage
from qon.blog import Blog, BlogItem
from qon.ui.blocks.util import path_to_obj, full_url

_limit = 999999999
oids = {}

def collect_watched_data():
    # collect all watched objects
    i = 1
    for userid, user in db.user_db.root.items():
        # print "%d) %s" % (i, user.display_name())        
        for oid in user.get_watch_list().watched_items_oids():
            oids[oid] = oids.get(oid, 0) + 1
            
        i += 1
        
def do_all_user_blogitems():
    """ iterate through each user and news item """
    i = 1
    for userid, user in db.user_db.root.items():
        if i > _limit:
            break
        
        for bi in user.get_blog().get_items():

            # print "%d) %s BlogItem: %s" % (i, userid, bi.title)
            print_item(bi, "-")
                    
            i += 1

def do_all_group_blogitems():
    """ iterate through each group and index each discussion topic """
    i = 1
    for groupid, group in db.group_db.root.items():
        if i > _limit:
            break
        
        for bi in group.get_blog().get_items():
          
            # print "%d) %s BlogItem: %s" % (i, groupid, bi.title)
            print_item(bi, groupid)
                    
            i += 1                   

def print_item(bi, group_short_name):
    title = bi.title.replace('\n', ' ')
    shortgroup = group_short_name
    url = path_to_obj(bi)
    author_name = bi.author.display_name().replace('\n', ' ')
    author_id = bi.author.get_user_id()
    date = bi.date
    modified = bi.modified
    last_modified = bi.last_modified()
    num_comments = bi.num_all_comments()
    feedback = bi.get_karma_score()

    plus_total, neg_total, pos_karma_givers, neg_karma_givers = bi.karma_details()

    plus_users =  len(pos_karma_givers)
    neg_users = len(neg_karma_givers)
    decayed = (plus_total - neg_total) - feedback            
    (times, members) = bi.item_views()
    watched_count = oids.get(bi._p_oid, 0)

    def num_comment_authors(comments):
        uniq_authors = {}
        for comment in comments:
            uniq_authors[comment.author] = 1
        return len(uniq_authors.keys())

    num_commenting_users = num_comment_authors(bi.get_all_comments())                 

    print "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d" % \
          (title, shortgroup, url, author_name, author_id, str(date), str(modified), str(last_modified), num_comments, num_commenting_users, feedback, plus_users, plus_total, \
           neg_users, neg_total, decayed, times, members, watched_count)    

if __name__ == "__main__":

    # open the ZODB database file    
    #db = open_database("file:/www/var/qon.fs")
    db = open_database()

    # do it

    collect_watched_data()

    print "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % \
          ("title", "group", "url", "author_name", "author_id", "created", "last_edited", "last_modified", "num_comments", "num_commenting_users", "feedback", "plus_users", "plus_score", \
           "neg_users", "neg_score", "decayed", "times_viewed", "members_viewed", "watched")
    
    do_all_user_blogitems()
    do_all_group_blogitems()
        
    # done
    db.close()
