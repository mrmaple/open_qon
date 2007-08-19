#!/usr/bin/env python
"""
$Id: report_initial_user_activity.py,v 1.7 2006/10/11 05:47:58 alex Exp $
Go through pretty much every object in the DB to gather 'first use' date
about every user.
Also serves as the group report too.
"""

import os
import sys
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database, transaction_commit, get_list_database
from qon.user import User
from qon.group import Group
from qon.wiki import Wiki, WikiPage
from qon.blog import Blog, BlogItem
from datetime import datetime, timedelta

# --------------------------------------------------------------------------------------
# USER REPORT STUFF
# --------------------------------------------------------------------------------------

# for keeping track of first time events
#  key=user, value=date
first_discussion_post = {}
first_wiki_edit = {}
first_wiki_created = {}
first_personal_news_post = {}
first_comment_post = {}
first_group_created = {}
# first_edited_profile = {}
# first_group_joined = {}
# first_use_of_msg_system = {}

# for keeping track of counts
#  key=user, value=count
num_discussion_posts = {}
num_wiki_edits = {}
num_wiki_created = {}
num_personal_news_posts = {}
num_comment_posts = {}
num_group_created = {}
# num_edited_profile = {}
num_group_joined = {}
num_group_owned = {}
# num_use_of_msg_system = {}

# added 2006-10-02
num_discussion_posts_this_month = {}
num_wiki_edits_this_month = {}
num_wiki_created_this_month = {}
num_personal_news_posts_this_month = {}
num_comment_posts_this_month = {}
num_group_created_this_month = {}

# added 2006-10-02
num_page_views = {}

# more counts
#  key=user, value=list
unique_discussions_commented_on = {}
unique_wikipages_edited = {}


# --------------------------------------------------------------------------------------
# GROUP REPORT STUFF
# --------------------------------------------------------------------------------------
group_latest_post = {}
group_num_members = {}
group_num_members_logged_in_last_three_months = {}
group_num_comments = {}
group_num_comments_this_month = {}
group_num_discussions = {}
group_num_discussions_started_this_month = {}
group_num_workspaces = {}

_limit = 99999999999
snapshot_date = datetime(2000, 1, 1)

def get_previous_month():
    if snapshot_date.month > 1:
        return (snapshot_date.year, snapshot_date.month-1)
    return (snapshot_date.year-1, 12)
        
def do_all_users():
    """ iterate through each user and news item """
    i = 1
    for userid, user in db.user_db.root.items():
        if i > _limit:
            break
        
        for bi in user.get_blog().get_items():
            # print "%s) %s BlogItem: %s" % (i, userid, bi.title)

            # first_personal_news_post
            if not first_personal_news_post.has_key(bi.author) or first_personal_news_post[bi.author] > bi.date:
                first_personal_news_post[bi.author] = bi.date

            # num_personal_news_posts              
            if not num_personal_news_posts.has_key(bi.author):
                num_personal_news_posts[bi.author] = 1
            else:
                num_personal_news_posts[bi.author] = num_personal_news_posts[bi.author] + 1

            # num_personal_news_posts_this_month
            if bi.date.month == get_previous_month()[1] and bi.date.year == get_previous_month()[0]:
                if not num_personal_news_posts_this_month.has_key(bi.author):
                    num_personal_news_posts_this_month[bi.author] = 1
                else:
                    num_personal_news_posts_this_month[bi.author] = num_personal_news_posts_this_month[bi.author] + 1

            # num_page_views
            for u, count in bi.get_pageview_counts_per_user():
                if not num_page_views.has_key(u):
                    num_page_views[u] = count
                else:
                    num_page_views[u] = num_page_views[u] + count                
            
            for c in bi.get_comments():

                # first_comment_post                
                if not first_comment_post.has_key(c.author) or first_comment_post[c.author] > c.date:
                    first_comment_post[c.author] = c.date
                    
                # num_comment_posts
                if not num_comment_posts.has_key(c.author):
                    num_comment_posts[c.author] = 1
                else:
                    num_comment_posts[c.author] = num_comment_posts[c.author] + 1

                # num_comment_posts_this_month
                if c.date.month == get_previous_month()[1] and c.date.year == get_previous_month()[0]:           
                    if not num_comment_posts_this_month.has_key(c.author):
                        num_comment_posts_this_month[c.author] = 1
                    else:
                        num_comment_posts_this_month[c.author] = num_comment_posts_this_month[c.author] + 1                    
                    
                if not unique_discussions_commented_on.has_key(c.author):
                    unique_discussions_commented_on[c.author] = [bi]
                elif not bi in unique_discussions_commented_on[c.author]:
                    unique_discussions_commented_on[c.author].append(bi)
                    
            i += 1

def do_all_groups():
    """ iterate through each group """
    i = 1
    for groupid, group in db.group_db.root.items():
        if i > _limit:
            break
        creator = group.owners[0]

        # first_group_created
        if not first_group_created.has_key(creator) or first_group_created[creator] > group.date:
            first_group_created[creator] = group.date

        # num_group_created
        if not num_group_created.has_key(creator):
            num_group_created[creator] = 1
        else:
            num_group_created[creator] = num_group_created[creator] + 1

        # num_group_created_this_month
        if group.date.month == get_previous_month()[1] and group.date.year == get_previous_month()[0]:                   
            if not num_group_created_this_month.has_key(creator):
                num_group_created_this_month[creator] = 1
            else:
                num_group_created_this_month[creator] = num_group_created_this_month[creator] + 1            

        # num_group_joined, group_num_members, group_num_members_logged_in_last_three_months   
        for u in group.get_member_list():
            if isinstance(u, User):
                # num_group_joined  
                if not num_group_joined.has_key(u):
                    num_group_joined[u] = 1
                else:
                    num_group_joined[u] = num_group_joined[u] + 1

                # group_num_members                    
                if not group_num_members.has_key(group):
                    group_num_members[group] = 1
                else:
                    group_num_members[group] = group_num_members[group] + 1

                # group_num_members_logged_in_last_three_months                
                if (u.last_login) and (u.last_login >= (snapshot_date - timedelta(90))):
                    if not group_num_members_logged_in_last_three_months.has_key(group):
                        group_num_members_logged_in_last_three_months[group] = 1
                    else:
                        group_num_members_logged_in_last_three_months[group] = group_num_members_logged_in_last_three_months[group] + 1                    

        # num_group_owned                    
        for u in group.owners:
            if isinstance(u, User):
                if not num_group_owned.has_key(u):
                    num_group_owned[u] = 1
                else:
                    num_group_owned[u] = num_group_owned[u] + 1                                    
        
    

def do_all_group_blogitems():
    """ iterate through each group and index each discussion topic """
    i = 1
    for groupid, group in db.group_db.root.items():
        if i > _limit:
            break        
        for bi in group.get_blog().get_items():
            # print "%s) %s BlogItem: %s" % (i, groupid, bi.title)

            # first_discussion_post      
            if not first_discussion_post.has_key(bi.author) or first_discussion_post[bi.author] > bi.date:
                first_discussion_post[bi.author] = bi.date

            # num_discussion_posts       
            if not num_discussion_posts.has_key(bi.author):
                num_discussion_posts[bi.author] = 1
            else:
                num_discussion_posts[bi.author] = num_discussion_posts[bi.author] + 1

            # num_discussion_posts_this_month
            if bi.date.month == get_previous_month()[1] and bi.date.year == get_previous_month()[0]:                   
                if not num_discussion_posts_this_month.has_key(bi.author):
                    num_discussion_posts_this_month[bi.author] = 1
                else:
                    num_discussion_posts_this_month[bi.author] = num_discussion_posts_this_month[bi.author] + 1

            # num_page_views
            for u, count in bi.get_pageview_counts_per_user():
                if not num_page_views.has_key(u):
                    num_page_views[u] = count
                else:
                    num_page_views[u] = num_page_views[u] + count                       

            # group_latest_post
            if not group_latest_post.has_key(group) or group_latest_post[group] < bi.date:
                group_latest_post[group] = bi.date

            # group_num_discussions
            if not group_num_discussions.has_key(group):
                group_num_discussions[group] = 1
            else:
                group_num_discussions[group] = group_num_discussions[group] + 1

            # group_num_discussions_started_this_month
            if bi.date.month == get_previous_month()[1] and bi.date.year == get_previous_month()[0]:                   
                if not group_num_discussions_started_this_month.has_key(group):
                    group_num_discussions_started_this_month[group] = 1
                else:
                    group_num_discussions_started_this_month[group] = group_num_discussions_started_this_month[group] + 1                
                
            for c in bi.get_comments():

                # first_comment_post                
                if not first_comment_post.has_key(c.author) or first_comment_post[c.author] > c.date:
                    first_comment_post[c.author] = c.date

                # num_comment_posts
                if not num_comment_posts.has_key(c.author):
                    num_comment_posts[c.author] = 1
                else:
                    num_comment_posts[c.author] = num_comment_posts[c.author] + 1

                # num_comment_posts_this_month
                if c.date.month == get_previous_month()[1] and c.date.year == get_previous_month()[0]:                         
                    if not num_comment_posts_this_month.has_key(c.author):
                        num_comment_posts_this_month[c.author] = 1
                    else:
                        num_comment_posts_this_month[c.author] = num_comment_posts_this_month[c.author] + 1                    

                if not unique_discussions_commented_on.has_key(c.author):
                    unique_discussions_commented_on[c.author] = [bi]
                elif not bi in unique_discussions_commented_on[c.author]:
                    unique_discussions_commented_on[c.author].append(bi)

                # group_latest_post
                if not group_latest_post.has_key(group) or group_latest_post[group] < c.date:
                    group_latest_post[group] = c.date

                # group_num_comments
                if not group_num_comments.has_key(group):
                    group_num_comments[group] = 1
                else:
                    group_num_comments[group] = group_num_comments[group] + 1

                # group_num_comments_this_month
                if c.date.month == get_previous_month()[1] and c.date.year == get_previous_month()[0]:                   
                    if not group_num_comments_this_month.has_key(group):
                        group_num_comments_this_month[group] = 1
                    else:
                        group_num_comments_this_month[group] = group_num_comments_this_month[group] + 1                        
                    
            i += 1                 

def do_all_group_wikipages():
    """ iterate through each group and index each wikipage """
    i = 1
    for groupid, group in db.group_db.root.items():
        if i > _limit:
            break        
        w = group.get_wiki()
        for wikipagename, wikipage in w.pages.items():
            # print "%s) %s WikiPage: %s" % (i, groupid, wikipage.versions[-1].title)
            version0 = wikipage.versions[0]

            # first_wiki_created            
            if not first_wiki_created.has_key(version0.author) or first_wiki_created[version0.author] > version0.date:
                first_wiki_created[version0.author] = version0.date

            # num_wiki_created                
            if not num_wiki_created.has_key(version0.author):
                num_wiki_created[version0.author] = 1
            else:
                num_wiki_created[version0.author] = num_wiki_created[version0.author] + 1

            # num_wiki_created_this_month
            if version0.date.month == get_previous_month()[1] and version0.date.year == get_previous_month()[0]:                         
                if not num_wiki_created_this_month.has_key(version0.author):
                    num_wiki_created_this_month[version0.author] = 1
                else:
                    num_wiki_created_this_month[version0.author] = num_wiki_created_this_month[version0.author] + 1

            # group_num_workspaces
            if not group_num_workspaces.has_key(group):
                group_num_workspaces[group] = 1
            else:
                group_num_workspaces[group] = group_num_workspaces[group] + 1                    
                    
            for v in wikipage.versions[1:]:

                # first_wiki_edit
                if not first_wiki_edit.has_key(v.author) or first_wiki_edit[v.author] > v.date:
                    first_wiki_edit[v.author] = v.date

                # num_wiki_edits                    
                if not num_wiki_edits.has_key(v.author):
                    num_wiki_edits[v.author] = 1
                else:
                    num_wiki_edits[v.author] = num_wiki_edits[v.author] + 1

                # num_wiki_edits_this_month
                if v.date.month == get_previous_month()[1] and v.date.year == get_previous_month()[0]:                         
                    if not num_wiki_edits_this_month.has_key(v.author):
                        num_wiki_edits_this_month[v.author] = 1
                    else:
                        num_wiki_edits_this_month[v.author] = num_wiki_edits_this_month[v.author] + 1                    

                if not unique_wikipages_edited.has_key(v.author):
                    unique_wikipages_edited[v.author] = [wikipage]
                elif not wikipage in unique_wikipages_edited[v.author]:
                    unique_wikipages_edited[v.author].append(wikipage)
                    
            for c in wikipage.get_comments():
                if not first_comment_post.has_key(c.author) or first_comment_post[c.author] > c.date:
                    first_comment_post[c.author] = c.date
                    
                if not num_comment_posts.has_key(c.author):
                    num_comment_posts[c.author] = 1
                else:
                    num_comment_posts[c.author] = num_comment_posts[c.author] + 1
            i += 1                    

if __name__ == "__main__":

    snapshot_date = datetime(int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))
    print 'using snapshot date of ' + str(snapshot_date) + ' Pacific Time\n'

    # open the ZODB database file    
    #db = open_database("file:/www/var/qon.fs")
    db = open_database()

    # do it

    do_all_users()
    do_all_group_blogitems()
    do_all_group_wikipages()        
    do_all_groups()

    # --------------------------------------------------------------------------------------
    # USER REPORT STUFF
    # --------------------------------------------------------------------------------------    

    sorted_users = []
    for userid, u in db.user_db.root.items():

        if not first_discussion_post.has_key(u):
            first_discussion_post[u] = 'Never'
        if not first_wiki_edit.has_key(u):
            first_wiki_edit[u] = 'Never'
        if not first_wiki_created.has_key(u):
            first_wiki_created[u] = 'Never'
        if not first_personal_news_post.has_key(u):
            first_personal_news_post[u] = 'Never'
        if not first_comment_post.has_key(u):
            first_comment_post[u] = 'Never'
        if not first_group_created.has_key(u):
            first_group_created[u] = 'Never'
        if not num_group_created.has_key(u):
            num_group_created[u] = 0
        if not num_discussion_posts.has_key(u):
            num_discussion_posts[u] = 0
        if not num_wiki_edits.has_key(u):
            num_wiki_edits[u] = 0
        if not num_wiki_created.has_key(u):
            num_wiki_created[u] = 0
        if not num_personal_news_posts.has_key(u):
            num_personal_news_posts[u] = 0
        if not num_comment_posts.has_key(u):
            num_comment_posts[u] = 0
        if not num_group_joined.has_key(u):
            num_group_joined[u] = 0            
        if not num_group_owned.has_key(u):
            num_group_owned[u] = 0
        if not unique_discussions_commented_on.has_key(u):
            unique_discussions_commented_on[u] = []
        if not unique_wikipages_edited.has_key(u):
            unique_wikipages_edited[u] = []
        if not num_discussion_posts_this_month.has_key(u):
            num_discussion_posts_this_month[u] = 0
        if not num_wiki_edits_this_month.has_key(u):
            num_wiki_edits_this_month[u] = 0
        if not num_wiki_created_this_month.has_key(u):
            num_wiki_created_this_month[u] = 0            
        if not num_personal_news_posts_this_month.has_key(u):
            num_personal_news_posts_this_month[u] = 0
        if not num_comment_posts_this_month.has_key(u):
            num_comment_posts_this_month[u] = 0
        if not num_group_created_this_month.has_key(u):
            num_group_created_this_month[u] = 0
        if not num_page_views.has_key(u):
            num_page_views[u] = 0  

        sorted_users.append(u)

    sorted_users.sort(lambda x, y: cmp(num_page_views[y], num_page_views[x]))
        

    print 'userid' + '\t' + 'class' + '\t' + 'member since' + '\t' + '1st discussion post' + '\t' + '1st page edit' + '\t' + '1st page created' + '\t'\
          + '1st personal news post' + '\t' + '1st comment post' + '\t' + '1st group created' + '\t' + 'num groups created' + '\t'\
          + 'num discussion posts' + '\t' + 'num pages edited' + '\t' + 'num pages created' + '\t' + 'num personal news posts' + '\t'\
          + 'num comments posted' + '\t' + 'num groups joined'  + '\t' + 'num groups owned'    + '\t' + 'page views'    + '\t'\
          + 'last login'  + '\t' + 'last login in 30 days?' + '\t' + 'last login in 60 days?' + '\t' + 'last login in 90 days?' + '\t' + 'feedback' + '\t' + 'feedback bucket' + '\t'\
          + 'bank' + '\t' + 'unique discussions commented on' + '\t' + 'unique pages edited' + '\t' + 'friends' + '\t'\
          + 'pos fb spent' + '\t' + 'neg fb spent' + '\t' + 'comment fb' + '\t'\
          + 'num groups created this month' + '\t' + 'num discussion posts this month' + '\t' + 'num pages edited this month' + '\t'\
          + 'num pages created this month' + '\t' + 'num personal news posts this month' + '\t' + 'num comments posted this month' + '\t'\
          + 'comments this month bucket'
  
    for u in sorted_users:

        pos, neg = get_list_database().karma_user_content_totals(u)

        # user class        
        year = str(u.member_since().year)
        month = u.member_since().month
        if month < 10:
            month = "0" + str(month)
        else:
            month = str(month)
        user_class = year + "-" + month

        # feedback bucket - 2006-10-09
        #  0 = 0
        #  1 = 1 to 4
        #  2 = 5 to 9
        #  3 = 10 to 24
        #  4 = 25 to 49
        #  5 = 50 to 74
        #  6 = 75 to 99
        #  7 = 100 to 199
        #  8 = 200+           
        feedback_bucket = 0
        if u.get_karma_score() >= 200:
            feedback_bucket = 8
        elif u.get_karma_score() >= 100:
            feedback_bucket = 7
        elif u.get_karma_score() >= 75:
            feedback_bucket = 6
        elif u.get_karma_score() >= 50:
            feedback_bucket = 5
        elif u.get_karma_score() >= 25:
            feedback_bucket = 4
        elif u.get_karma_score() >= 10:
            feedback_bucket = 3
        elif u.get_karma_score() >= 5:
            feedback_bucket = 2
        elif u.get_karma_score() >= 1:
            feedback_bucket = 1
        else:
            feedback_bucket = 0

        # comments this month bucket - 2006-10-09
        #  0 = 0
        #  1 = 1 to 4
        #  2 = 5 to 9
        #  3 = 10 to 19
        #  4 = 20+         
        comments_this_month_bucket = 0
        if num_comment_posts_this_month[u] >= 20:
            comments_this_month_bucket = 4
        elif num_comment_posts_this_month[u] >= 10:
            comments_this_month_bucket = 3
        elif num_comment_posts_this_month[u] >= 5:
            comments_this_month_bucket = 2
        elif num_comment_posts_this_month[u] >= 1:
            comments_this_month_bucket = 1
        else:
            comments_this_month_bucket = 0

        # login_30days, login_60days, login_90days
        login_30days = "0"
        login_60days = "0"
        login_90days = "0"
        if (u.last_login) and (u.last_login >= (snapshot_date - timedelta(30))):
            login_30days = "1"
        if (u.last_login) and (u.last_login >= (snapshot_date - timedelta(60))):
            login_60days = "1"
        if (u.last_login) and (u.last_login >= (snapshot_date - timedelta(90))):
            login_90days = "1"          
        
        print u.get_user_id() + '\t' + user_class + '\t' + str(u.member_since()) + '\t' + str(first_discussion_post[u]) + '\t' + str(first_wiki_edit[u]) + '\t' + str(first_wiki_created[u]) + '\t'\
              + str(first_personal_news_post[u]) + '\t' + str(first_comment_post[u]) + '\t' + str(first_group_created[u]) + '\t' + str(num_group_created[u]) + '\t'\
              + str(num_discussion_posts[u]) + '\t' + str(num_wiki_edits[u]) + '\t' + str(num_wiki_created[u]) + '\t' + str(num_personal_news_posts[u]) + '\t'\
              + str(num_comment_posts[u]) + '\t' + str(num_group_joined[u]) + '\t' + str(num_group_owned[u]) + '\t'  + str(num_page_views[u]) + '\t'\
              + str(u.last_login) + '\t' + login_30days + '\t' + login_60days + '\t' + login_90days + '\t' + str(u.get_karma_score()) + '\t' + str(feedback_bucket) + '\t'\
              + str(u.get_karma_bank_balance(True)) + '\t' + str(len(unique_discussions_commented_on[u])) + '\t' + str(len(unique_wikipages_edited[u])) + '\t' + str(len(u.positive_karma_givers())) + '\t'\
              + str(u.karma_plus_given()) + '\t' + str(u.karma_minus_given()) + '\t' + str(pos+neg) + '\t'\
              + str(num_group_created_this_month[u]) + '\t' + str(num_discussion_posts_this_month[u]) + '\t' + str(num_wiki_edits_this_month[u]) + '\t'\
              + str(num_wiki_created_this_month[u]) + '\t' + str(num_personal_news_posts_this_month[u]) + '\t' + str(num_comment_posts_this_month[u]) + '\t'\
              + str(comments_this_month_bucket)


    # --------------------------------------------------------------------------------------
    # GROUP REPORT STUFF
    # --------------------------------------------------------------------------------------    

    avg_members_per_group = 0
    avg_members_logged_in_last_90_days_per_group = 0
    avg_comments_per_group = 0
    avg_comments_this_month_per_group = 0
    avg_discussions_per_group = 0    
    avg_discussions_this_month_per_group = 0
    avg_workspaces_pages_per_group = 0
    
    avg_members_per_group_wo_comgen = 0
    avg_members_logged_in_last_90_days_per_group_wo_comgen = 0
    avg_comments_per_group_wo_comgen = 0
    avg_comments_this_month_per_group_wo_comgen = 0
    avg_discussions_per_group_wo_comgen = 0    
    avg_discussions_this_month_per_group_wo_comgen = 0
    avg_workspaces_pages_per_group_wo_comgen = 0

    sorted_groups = []
    for groupid, group in db.group_db.root.items():
        
        if not group_latest_post.has_key(group):
            group_latest_post[group] = 'Never'
        if not group_num_members.has_key(group):
            group_num_members[group] = 0
        if not group_num_members_logged_in_last_three_months.has_key(group):
            group_num_members_logged_in_last_three_months[group] = 0
        if not group_num_comments.has_key(group):
            group_num_comments[group] = 0
        if not group_num_comments_this_month.has_key(group):
            group_num_comments_this_month[group] = 0
        if not group_num_discussions.has_key(group):
            group_num_discussions[group] = 0
        if not group_num_discussions_started_this_month.has_key(group):
            group_num_discussions_started_this_month[group] = 0
        if not group_num_workspaces.has_key(group):
            group_num_workspaces[group] = 0

        avg_members_per_group += group_num_members[group]
        avg_members_logged_in_last_90_days_per_group += group_num_members_logged_in_last_three_months[group]
        avg_comments_per_group += group_num_comments[group]
        avg_comments_this_month_per_group += group_num_comments_this_month[group]
        avg_discussions_per_group += group_num_discussions[group]    
        avg_discussions_this_month_per_group += group_num_discussions_started_this_month[group]
        avg_workspaces_pages_per_group += group_num_workspaces[group]

        if (groupid != 'community-general'):
            avg_members_per_group_wo_comgen += group_num_members[group]
            avg_members_logged_in_last_90_days_per_group_wo_comgen += group_num_members_logged_in_last_three_months[group]
            avg_comments_per_group_wo_comgen += group_num_comments[group]
            avg_comments_this_month_per_group_wo_comgen += group_num_comments_this_month[group]
            avg_discussions_per_group_wo_comgen += group_num_discussions[group]    
            avg_discussions_this_month_per_group_wo_comgen += group_num_discussions_started_this_month[group]
            avg_workspaces_pages_per_group_wo_comgen += group_num_workspaces[group]            
            
        sorted_groups.append(group)

    num_groups = len(sorted_groups)
    avg_members_per_group /= num_groups
    avg_members_logged_in_last_90_days_per_group /= num_groups
    avg_comments_per_group /= num_groups
    avg_comments_this_month_per_group /= num_groups
    avg_discussions_per_group /= num_groups
    avg_discussions_this_month_per_group /= num_groups
    avg_workspaces_pages_per_group /= num_groups

    avg_members_per_group_wo_comgen /= (num_groups-1)
    avg_members_logged_in_last_90_days_per_group_wo_comgen /= (num_groups-1)
    avg_comments_per_group_wo_comgen /= (num_groups-1)
    avg_comments_this_month_per_group_wo_comgen /= (num_groups-1)
    avg_discussions_per_group_wo_comgen /= (num_groups-1)
    avg_discussions_this_month_per_group_wo_comgen /= (num_groups-1)
    avg_workspaces_pages_per_group_wo_comgen /= (num_groups-1) 

    sorted_groups.sort(lambda x, y: cmp(group_num_members[y], group_num_members[x]))


    print '\n\n'
    print 'groupid' + '\t' + 'latest post' + '\t' + 'latest post in 30 days?' + '\t' + 'latest post in 60 days?' + '\t' + 'latest post in 90 days?' + '\t'\
          + 'num members' + '\t' + 'num members logged in last 90 days' + '\t'\
          + 'num comments' + '\t' + 'num comments this month' + '\t'\
          + 'num discussions' + '\t' + 'num discussions started this month' + '\t'\
          + 'num workspaces'

    for group in sorted_groups:
          
        # lastpost_30days, lastpost_60days, lastpost_90days
        lastpost_30days = "0"
        lastpost_60days = "0"
        lastpost_90days = "0"
        if (group_latest_post[group] != 'Never') and (group_latest_post[group] >= (snapshot_date - timedelta(30))):
            lastpost_30days = "1"
        if (group_latest_post[group] != 'Never') and (group_latest_post[group] >= (snapshot_date - timedelta(60))):
            lastpost_60days = "1"
        if (group_latest_post[group] != 'Never') and (group_latest_post[group] >= (snapshot_date - timedelta(90))):
            lastpost_90days = "1"
            
        print group.get_user_id() + '\t' + str(group_latest_post[group]) + '\t' + str(lastpost_30days) + '\t' + str(lastpost_60days) + '\t' + str(lastpost_90days) + '\t'\
              + str(group_num_members[group]) + '\t' + str(group_num_members_logged_in_last_three_months[group]) + '\t'\
              + str(group_num_comments[group]) + '\t' + str(group_num_comments_this_month[group]) + '\t'\
              + str(group_num_discussions[group]) + '\t' + str(group_num_discussions_started_this_month[group]) + '\t'\
              + str(group_num_workspaces[group])

    print '\n'
    print '\t' + 'averages overall' + '\t' + 'avearages w/o community-general'
    print 'members' + '\t' + str(avg_members_per_group) + '\t' + str(avg_members_per_group_wo_comgen)
    print 'members logged in last 90 days' + '\t' + str(avg_members_logged_in_last_90_days_per_group) + '\t' + str(avg_members_logged_in_last_90_days_per_group_wo_comgen)
    print 'comments' + '\t' + str(avg_comments_per_group) + '\t' + str(avg_comments_per_group_wo_comgen)
    print 'comments this month' + '\t' + str(avg_comments_this_month_per_group) + '\t' + str(avg_comments_this_month_per_group_wo_comgen)
    print 'discussions' + '\t' + str(avg_discussions_per_group) + '\t' + str(avg_discussions_per_group_wo_comgen)
    print 'discussions started this month' + '\t' + str(avg_discussions_this_month_per_group) + '\t' + str(avg_discussions_this_month_per_group_wo_comgen)
    print 'workspace pages' + '\t' + str(avg_workspaces_pages_per_group) + '\t' + str(avg_workspaces_pages_per_group_wo_comgen)

    
    
        
    # done
    transaction_commit()
    db.close()
