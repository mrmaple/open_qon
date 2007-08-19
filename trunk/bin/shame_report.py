#!/usr/bin/env python
"""
$Id: shame_report.py,v 1.1 2007/05/10 04:31:26 alex Exp $
shame report
"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database, transaction_commit, get_list_database, get_group_database
from qon.user import User
from qon.group import Group
from qon.wiki import Wiki, WikiPage
from qon.blog import Blog, BlogItem
from qon.ui.blocks.util import path_to_obj, full_url
from qon.karma import min_karma_to_show

def users():
    list_db = get_list_database()
    bottom_users = list_db.bottom_users()
    print "\nLowest-ranked users"
    print "karma\turl\tdisplay name\tmember since\tlast login"
    for user in bottom_users:
        if user.get_karma_score() < 0:
            print "%d\thttp://www.ned.com/user/%s/\t%s\t%s\t%s" % (user.get_karma_score(), user.get_user_id(), user.display_name(), str(user.member_since()), str(user.last_login))

def user_news():
    items = []
    comments = []
    for user_id, user in db.user_db.root.items():
        for item in user.get_blog().get_items():
            if item.get_karma_score() < min_karma_to_show:
                items.append((item, user_id))
            for comment in item.get_all_comments():
                if comment.get_karma_score() < min_karma_to_show:
                    comments.append((comment, user_id))

    print "\n\nFolded user news discussions"
    print "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % \
          ("title", "user", "url", "author_name", "author_id", "created", "last_edited", "last_modified", "num_comments", "feedback", "plus_users", "plus_score", \
           "neg_users", "neg_score", "decayed")
    for bi, user_id in items:
        print_item(bi, user_id)

    print "\nFolded user news comments"
    print "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % \
          ("title", "user", "url", "author_name", "author_id", "created", "last_edited", "last_modified", "num_comments", "feedback", "plus_users", "plus_score", \
           "neg_users", "neg_score", "decayed")
    for bi, user_id in comments:
        print_item(bi, user_id)        


def group_discussions():
    items = []
    comments = []
    for group_id, group in get_group_database().root.iteritems():
        for item in group.blog.get_items():
            if item.get_karma_score() < min_karma_to_show:
                items.append((item, group_id))
            for comment in item.get_all_comments():
                if comment.get_karma_score() < min_karma_to_show:
                    comments.append((comment, group_id))

    print "\n\nFolded group discussions"
    print "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % \
          ("title", "group", "url", "author_name", "author_id", "created", "last_edited", "last_modified", "num_comments", "feedback", "plus_users", "plus_score", \
           "neg_users", "neg_score", "decayed")
    for bi, group_id in items:
        print_item(bi, group_id)

    print "\nFolded group comments"
    print "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % \
          ("title", "group", "url", "author_name", "author_id", "created", "last_edited", "last_modified", "num_comments", "feedback", "plus_users", "plus_score", \
           "neg_users", "neg_score", "decayed")
    for bi, group_id in comments:
        print_item(bi, group_id)        
        
    
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

    print "%s\t%s\thttp://www.ned.com%s\t%s\t%s\t%s\t%s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d" % \
          (title, shortgroup, url, author_name, author_id, str(date), str(modified), str(last_modified), num_comments, feedback, plus_users, plus_total, \
           neg_users, neg_total, decayed)    

if __name__ == "__main__":

    # open the ZODB database file    
    #db = open_database("file:/www/var/qon.fs")
    db = open_database()

    # do it

    print "Shame Report"
    
    users()
    user_news()
    group_discussions()
        
    # done
    db.close()
