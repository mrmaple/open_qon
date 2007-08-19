#!/usr/bin/env python
"""
$Id: feedback_experiment.py,v 1.1 2005/01/10 06:50:48 alex Exp $
Feedback experiement -- calculate users feedback based on their authored content
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

user_feedback = {} # key is user, value is feedback
user_feedback_comments_only = {} # key is user, value is feedback

def add_feedback(user_dict, user, fb):
    f = 0
    try:
        f = user_dict[user]
    except:
        pass
    user_dict[user] = f + fb

def process_all_user_blogitems():
    """ iterate through each user and index each news item """
    i=0
    for userid, user in db.user_db.root.items():
        for bi in user.get_blog().get_items():
            add_feedback(user_feedback, bi.author, bi.get_karma_score())
            print "%s) %s BlogItem: %s" % (i, userid, bi.title)
            for c in bi.get_comments():
                add_feedback(user_feedback, c.author, c.get_karma_score())    
                add_feedback(user_feedback_comments_only, c.author, c.get_karma_score())    
            i+=1

def process_all_group_blogitems():
    """ iterate through each group and index each discussion topic """
    i=0
    for groupid, group in db.group_db.root.items():
        for bi in group.get_blog().get_items():
            add_feedback(user_feedback, bi.author, bi.get_karma_score())            
            print "%s) %s BlogItem: %s" % (i, groupid, bi.title)
            for c in bi.get_comments():
                add_feedback(user_feedback, c.author, c.get_karma_score())    
                add_feedback(user_feedback_comments_only, c.author, c.get_karma_score())
            i+=1

def process_all_group_wikipages():
    """ iterate through each group and index each wikipage """
    i=0
    for groupid, group in db.group_db.root.items():
        w = group.get_wiki()
        for wikipagename, wikipage in w.pages.items():
            add_feedback(user_feedback, wikipage.versions[-1].author, wikipage.get_karma_score())
            print "%s) %s WikiPage: %s" % (i, groupid, wikipage.versions[-1].title)
            for c in wikipage.get_comments():
                add_feedback(user_feedback, c.author, c.get_karma_score())    
                add_feedback(user_feedback_comments_only, c.author, c.get_karma_score())
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
    process_all_user_blogitems()
    print ""
    #--------------------------

    print ""
    print "Group BlogItems"
    print "---------------"    
    process_all_group_blogitems()
    print ""
    #--------------------------
    print ""
    print "Group WikiPages"
    print "---------------"  
    process_all_group_wikipages()        
    print ""

    user_feedback_list = user_feedback.items()
    user_feedback_comments_only_list = user_feedback_comments_only.items()

    feedback = qon.util.sort_list(user_feedback_list, lambda x: x[1])
    print "\nTop Users By Feedback on All Authored Content::\n"    
    for x in feedback[:100]:
        print " %s (%s) [%s] " % (x[0].display_name(), x[0].get_karma_score(), x[1])

    feedback = qon.util.sort_list(user_feedback_comments_only_list, lambda x: x[1])
    print "\nTop Users By Feedback on Authored Comments::\n"    
    for x in feedback[:100]:
        print " %s (%s) [%s] " % (x[0].display_name(), x[0].get_karma_score(), x[1])        

    # done
    db.close()
