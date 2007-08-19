#!/usr/bin/env python
"""
$Id: test_all_links.py,v 1.4 2006/01/25 05:57:06 alex Exp $
Go through every (well, almost every) piece of content in the qon DB
and make sure we don't get any kind of error.  Also times each call.
Takes 2.5-3 hours to run.

Does not spider the site like test_http_loadtesting.py.

Note: the best way to use this is to pipe output to a file, then
 grep it for errors and/or SLOW instances, and then look
 in the error.log file.
E.g.: test_all_links.py > output.txt
      grep Error output.txt
      grep SLOW output.txt
      tail /www/log/qon/error.log
"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database, transaction_commit, commit_upgraded_versioneds
from qon.user import User
from qon.group import Group
from qon.wiki import Wiki, WikiPage
from qon.blog import Blog, BlogItem
import urllib2
from qon.ui.blocks.util import path_to_obj
from datetime import datetime, timedelta

_URL_BASE = "http://www.maplesong.com:8081"
_URL_BASE = "https://www.maplesong.com:8443"
_DO_COMMENTS = False  # whether or not to test individual comment URLs
_SLOW_THRESHOLD = 1000

def get_ms(td):
    """ Convert a timedelta to ms """
    return (td.days*86400 + td.seconds)*1000 + td.microseconds/1000

def _fetch_url(i, url):
    url = _URL_BASE + url
    print "%s) %s" % (i, url),
    s_time = datetime.utcnow()
    try:
        f = urllib2.urlopen(url)
        elapsed = get_ms(datetime.utcnow() - s_time)
        slow = ""
        if elapsed > _SLOW_THRESHOLD:
            slow = " (SLOW)"
        print " --> Success. (%s ms%s)" % (elapsed, slow)
    except urllib2.HTTPError, err:
        elapsed = get_ms(datetime.utcnow() - s_time)        
        slow = ""
        if elapsed > _SLOW_THRESHOLD:
            slow = " (SLOW)"
        print " --> %s. (%s ms%s)" % (str(err), get_ms(datetime.utcnow() - s_time), slow)

def do_all_users():
    i = 1
    for userid, user in db.user_db.root.items():
        _fetch_url(i, path_to_obj(user))
        i += 1
    
def do_all_groups():
    i = 1   
    for groupid, group in db.group_db.root.items():
        _fetch_url(i, path_to_obj(group))        
        i += 1
    
def do_all_user_blogitems():
    i = 1
    j = 1
    for userid, user in db.user_db.root.items():
        for bi in user.get_blog().get_items():
            _fetch_url(i, path_to_obj(bi))
            i += 1
            if _DO_COMMENTS:
                for c in bi.get_comments():
                    _fetch_url(str(i) + "." + str(j), path_to_obj(c))                    
                    j += 1
    
def do_all_group_blogitems():
    """ iterate through each group and index each discussion topic """
    i = 1
    j = 1
    for groupid, group in db.group_db.root.items():
        for bi in group.get_blog().get_items():
            _fetch_url(i, path_to_obj(bi))            
            i += 1
            if _DO_COMMENTS:
                for c in bi.get_comments():
                    _fetch_url(str(i) + "." + str(j), path_to_obj(c))                                        
                    j += 1

def do_all_group_wikipages():
    i = 1
    for groupid, group in db.group_db.root.items():
        w = group.get_wiki()
        for wikipagename, wikipage in w.pages.items():
            _fetch_url(i, path_to_obj(wikipage))                        
            i += 1                    
    
def do_all_group_polls():
    """ iterate through each group and index each poll """
    i = 1
    for groupid, group in db.group_db.root.items():
        for p in group.polls.get_polls():
            _fetch_url(i, path_to_obj(p))                                    
            i += 1                    

if __name__ == "__main__":

    # open the ZODB database file    
    #db = open_database("file:/www/var/qon.fs")
    db = open_database()

    # do it
    print ""
    print "Users"
    print "-----"
    do_all_users()
    print ""
    #--------------------------    
    print ""    
    print "User BlogItems"
    print "--------------"
    do_all_user_blogitems()
    print ""
    #--------------------------
    print ""  
    print "Groups"
    print "------"
    do_all_groups()
    print ""
    #--------------------------
    print ""
    print "Group BlogItems"
    print "---------------"    
    do_all_group_blogitems()
    print ""
    #--------------------------
    print ""
    print "Group WikiPages"
    print "---------------"  
    do_all_group_wikipages()        
    print ""
    #--------------------------
    print ""
    print "Group Polls"
    print "---------------"  
    do_all_group_polls()
    print ""

    # done
    transaction_commit()  # just in case, by reading an object in, we updated it
    db.close()
