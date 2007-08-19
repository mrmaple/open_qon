#!/usr/bin/env python
"""
$Id: move_ws_comments_to_page.py,v 1.2 2005/01/13 06:32:57 pierre Exp $
This script moves all workspace page comments to the pages themselves.
It is meant to be run in conjunction with the removal of the workspace
page comments feature.
"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database, transaction_commit, transaction_abort
from qon.user import User
from qon.group import Group
from qon.wiki import Wiki, WikiPage
from qon.blog import Blog, BlogItem               
from qon.ui.blocks.util import format_datetime
import qon.api
from qon import search
from datetime import timedelta

if __name__ == "__main__":

    # open the ZODB database file    
    #db = open_database("file:/www/var/qon.fs")
    db = open_database()

    # set batch mode to true so that we work synchronously and don't autocommit
    search.searchengine.set_batch_mode(True)

    admin_user = db.user_db['admin']     

    """ iterate through each group and its wiki pages """
    i = 0
    for groupid, group in db.group_db.root.items():
        print "Processing %s" % groupid
        w = group.get_wiki()
        # group_owner = group.owners[0]
        for wikipagename, wikipage in w.pages.items():
            transaction_abort() # don't commit something stray from previous wikipage (e.g. a deleted comment where we got an error after the deletion)
            comments = wikipage.get_comments()  # returns all non-deleted comments
            if len(comments) > 0:
                try:
                    # print "=========================================================="            
                    # print "[%s] %s" % (groupid, wikipage.versions[-1].title)
                    added_text = '\n\nComments\n--------\n\n'
                    for c in comments:
                        added_text += "* **%s**, %s\n\n" % (c.author.display_name(), format_datetime(c.last_modified()))
                        indented_summary = " " + c.get_summary().replace('\n', '\n ') + '\n\n'
                        added_text += indented_summary

                        # let's delete the comments so that if we have to re-run this script, we won't duplicate any comments
                        # qon.api.blog_delete_item(c)
                        c.deleted = True

                    # print added_text                                
                            
                    # create a new revision, adding the comments at the end, with admin as author
                    # Note: didn't use qon.api.wiki_edit_page because I need to hack the edit date to keep
                    #  from flooding the What's New tab with these edits
                    # qon.api.wiki_edit_page(w, wikipage, None, admin_user, wikipage.versions[-1].title, wikipage.versions[-1].get_raw() + added_text)
                    hacked_edit_time = wikipage.versions[-1].date + timedelta(seconds=1)
                    wikipage.new_revision(author=admin_user, title=wikipage.versions[-1].title, raw=wikipage.versions[-1].get_raw() + added_text)
                    wikipage.versions[-1].set_date(hacked_edit_time)  # hack the edit date to be 1 second after the last revision's
                    wikipage._Watchable__last_change = hacked_edit_time
                    admin_user.notify_authored_item(wikipage)        

                     # now that we're completely done with this wikipage, let's commit the new revision and the deleted comments
                    transaction_commit()

                    # tell search about the changes              
                    qon.search.searchengine.notify_edited_wiki_page(wikipage)

                    i += 1

                except:
                    print " ERROR PROCESSING [%s] %s" % (groupid, wikipage.versions[-1].title)                        

        # commit to search at end                      
        search.searchengine.commit_documents()

    # just in case
    transaction_commit()

    print "\nEdited %s workspace pages." % i
            
    # done
    db.close()
