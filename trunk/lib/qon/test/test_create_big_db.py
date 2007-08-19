#!/usr/bin/env python
"""$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/toboso/bin/create_db $
$Id: test_create_big_db.py,v 1.4 2007/05/01 11:41:29 jimc Exp $

Create (if necessary) a database and insert a lot of test data into it, for the purpose of
testing the limits of the db.
"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database
from qon.user import User, UserGroup
from qon.group import Group
import random
from qon import api
from datetime import datetime, timedelta

def init_database(db):
    for name, modname, klassname in [
        ('list_db', 'qon.list_db', 'ListDB'),
        ('log_db', 'qon.log', 'LogDB'),
        ('user_db', 'qon.user_db', 'UserDB'),
        ('usergroup_db', 'qon.user_db', 'UserGroupDB'),
        ('session_manager', 'qon.session', 'QonSessionManager'),
        ('group_db', 'qon.group_db', 'GroupDB'),
        ('tags_db', 'qon.tags_db', 'TagsDB'),
        ('tagged_item_db', 'qon.group_db', 'GroupDB'),
        ]:
        if not db.root.has_key(name):
            db.init_root(name, modname, klassname)
        
def add_real_data(db):
    for group in ['admin', 'staff', 'users']:
        if not db.usergroup_db.has_key(group):
            ug = UserGroup(group)
            db.usergroup_db.add_usergroup(ug)
        
    group_admin = db.usergroup_db['admin']
    group_staff = db.usergroup_db['staff']
    group_users = db.usergroup_db['users']

    for (user_id, group_id, name, email) in [
        ('admin', 'admin', "Administrative User", "ned@maplesong.com"),
        ('jimc', 'users', "Jim Carroll", "jim@maplesong.com"),
        ]:
        if not db.user_db.has_key(user_id):
            user = User(user_id)
            user.set_password(user_id)
            user.contact_name = name
            user.add_email(email)
            user.add_to_group(db.usergroup_db[group_id])
        
            db.user_db.add_user(user)

    admin = db.user_db['admin']
    admin.add_to_group(group_staff)
    admin.add_to_group(group_users)
    
    jimc = db.user_db['jimc']
    jimc.add_to_group(group_staff)

    # set database owners
    db.user_db.set_owner(admin)
    db.user_db.set_owning_group(group_admin)
    db.user_db.set_group_perms(['read'])
    db.user_db.set_other_perms(['read'])
    
    db.usergroup_db.set_owner(admin)
    db.usergroup_db.set_owning_group(group_admin)
    db.usergroup_db.set_group_perms(['read'])
    db.usergroup_db.set_other_perms(['read'])

    db.group_db.set_owner(admin)
    db.group_db.set_owning_group(group_admin)
    db.group_db.add_owning_group([group_staff, group_users])
    db.group_db.set_group_perms(['read','write'])
    db.group_db.set_other_perms(['read'])
    
    # create initial groups
    import qon.group_db
    qon.group_db.create_initial_groups()


def create_test_users(db, how_many, print_progress=False, sequential=False):
    """ Create a bunch of test users with userid tu______ and add them to the database
    howmany = how many users to attempt to create
    sequential = True to number the userids in sequence; otherwise, random userids are used
    """

    # don't bother doing it if we already have enough users
    # if len(db.user_db) >= how_many:
    #   return

    progress_interval = calculate_progress_interval(how_many)

    for x in range(1, how_many+1):

        if print_progress and (x % progress_interval == 0):
            print "Creating user %s of %s" % (x, how_many)

        if sequential:
            userid = "tu%s" % x
            if db.user_db.has_key(userid):
                continue
            else:
                user = User("tu%s" % x)
        else:
            user = User()
            while db.user_db.has_key(user.get_user_id()):
                user.generate_user_id("tu")

        user.set_password("password")
        user.contact_name = "%s Smith" % user.get_user_id()
        user.add_email("%s@null.com" % user.get_user_id())

        # add user to the 'users' UserGroup
        user.add_to_group(db.usergroup_db['users'])

        # add user to the database        
        db.user_db.add_user(user)

        get_transaction().commit()        

def create_test_groups(db, how_many, print_progress=False):
    """ Create a bunch of test groups with id tg_______ and add them to the database.
    The groups will be given random parent groups and random owners.
    howmany = how many groups to attempt to create
    """

    id_length = 9    
    
    def create_test_group (user_id, name, desc, owner, parent_id, join_pol, memb_vis):
        group_db = db.group_db
        user_admin = db.user_db['admin']

        if not group_db.has_key(user_id):
            g = group_db.create_group(user_id=user_id,
                name=name,
                description=desc,
                owner=owner)
            group_db.force_accept(g)
            if parent_id:
                group_db.join_group(g, group_db[parent_id], force=1)

        g = group_db[user_id]
        if join_pol:
            api.group_set_join_policy(user_admin, g, join_pol)
        if memb_vis:
            api.group_set_membership_visible(user_admin, g, memb_vis)
        if desc:
            api.group_set_settings(user_admin, g, description=desc)

        # allow members to read and write so that they can make forum posts and new wiki pages        
        g.set_group_perms(['read', 'write'])

        # allow others to read so that they can join
        g.set_other_perms(['read'])

    # don't bother doing it if we already have enough groups
    # if len(db.group_db) >= how_many:
    #  return

    progress_interval = calculate_progress_interval(how_many)
                
    for x in range(1, how_many+1):
        if print_progress and (x % progress_interval == 0):
            print "Creating group %s of %s" % (x, how_many)

        user_id = None
        while db.group_db.has_key(user_id) or not user_id:
            user_id = "tg%s" % str(random.randint(int('1'*id_length), int('9'*id_length)))
        name = "Group %s" % user_id
        desc = "%s is just a test group created by an automated tool for capacity/load testing" % name
        owner = get_random_user(db)
        parent_id = get_random_group(db).get_user_id()

        create_test_group(user_id, name, desc, owner, parent_id, 'open', 'open')

        get_transaction().commit()        

def join_users_to_groups(db, how_many_groups_per_user, print_progress=False):
    """ iterate through each user and join her to a bunch of random groups that were
    previously created. 
    how_many_groups_per_user = the number of groups that each user should join."""

    total_joins=0
    user_num=1
    total_users=len(db.user_db)

    progress_interval = calculate_progress_interval(total_users)
    
    for user_id, user in db.user_db.root.items():
        if print_progress and (user_num % progress_interval == 0):
            print "Joining %s groups for user %s of %s" % (how_many_groups_per_user, user_num, total_users)
        user_num+=1

        for x in range(how_many_groups_per_user):
            g = get_random_group(db)
            if g.can_join(user):
                api.group_join(g,user) # use instead of g.add_member(user) to make sure we add to UserGroup too

                get_transaction().commit()
                total_joins+=1

    return total_joins            
        

def make_forum_posts(db, how_many_items, how_many_comments_per_item, print_progress=False):
    """ randomly make posts/comments to forums.  groups and users are chosen randomly"""

    progress_interval = calculate_progress_interval(how_many_items)

    for x in range(1, how_many_items+1):
        if print_progress and (x % progress_interval == 0):
            print "Making forum item %s of %s (with %s comments each)" % (x, how_many_items, how_many_comments_per_item)

        # choose a random group's blog to post to            
        group = get_random_group(db)
        blog = group.blog

        # choose a random user of the group to be the author        
        author = get_random_user_of_group(group)

        # create the forum item
        title = "Item title"
        summary = "This is a really cool site. I dig it. " * 20
        if author is not None:
            item = api.blog_new_item(blog, author, title, summary, "")

            get_transaction().commit()        

        # make comments to that item
        for y in range(1, how_many_comments_per_item+1):
            
            # choose a random user of the group to be the commentor        
            commentor = get_random_user_of_group(group)

            # create the item comment
            c_summary = "I totally agree.  This site totally rocks.  I am #%s!!!!!" % y
            if commentor is not None:
                api.blog_new_comment(item, commentor, "", c_summary, "")

                get_transaction().commit()            

def make_wiki_pages(db, how_many_pages, how_many_edits_per_page, print_progress=False):
    """ randomly make pages/revisions to wikis.  groups and users are chosen randomly"""

    id_length = 9    

    progress_interval = calculate_progress_interval(how_many_pages)

    for x in range(1, how_many_pages+1):
        if print_progress and (x % progress_interval == 0):
            print "Making wiki page %s of %s (with %s additional revisions each)" % (x, how_many_pages, how_many_edits_per_page)

        # choose a random group's wiki to add to          
        group = get_random_group(db)
        wiki = group.wiki

        # choose a random user of the group to be the author        
        author = get_random_user_of_group(group)

        # create the page
        wp = "wp%s" % str(random.randint(int('1'*id_length), int('9'*id_length)))
        name = "Wiki Page %s" % wp
        title = "Wiki Page %s" % wp
        raw = "This is a test wiki page. " * 100
        if author is not None:
            page = api.wiki_edit_page(wiki, None, name, author, title, raw)

            get_transaction().commit()        

        # make edits to that item
        for y in range(1, how_many_edits_per_page+1):
            
            # choose a random user of the group to be the editor        
            editor = get_random_user_of_group(group)

            # create the item comment
            raw += " This is time #%s that I'm editing this page just for fun!!!" % y
            if editor is not None:
                api.wiki_edit_page(wiki, page, name, editor, title, raw)

                get_transaction().commit()            
    
def calculate_progress_interval(how_many):

    progress_interval = how_many / 10;
    if progress_interval == 0:
        progress_interval = 1
    return progress_interval


def get_random_user(db):
    s = db.user_db.root.keys()
    num = len(s)
    r = random.randint(3, num-1)  # 0 is None, 1 is admin, 2 is jimc, so don't include those
    return db.user_db[s[r]]
        
def get_random_group(db):
    s = db.group_db.root.keys()
    num = len(s)
    r = random.randint(0, num-1)  
    return db.group_db[s[r]]

def get_random_user_of_group(group):
    """ Given a group, return a member of the group.  However, the member must be a user, not a group."""
    members = group.get_members().get_members()

    # sanity check
    if len(members)==0:
        return None
    
    user = None
    x = 0
    while ((not user) or (str(type(user)) != "<class 'qon.user.User'>")) and x<100:
        user = members[random.randint(0, len(members)-1)]
        x += 1
    if str(type(user)) != "<class 'qon.user.User'>":
        return None
    else:
        return user

if __name__ == "__main__":

    # open (and create if necessary) a database file    
    db = open_database("file:/www/var/qon.fs")

    # do the normal initialization    
    init_database(db)
    add_real_data(db)
    get_transaction().commit()

    # specify how much test data to add
    number_of_test_users_to_add = 10
    number_of_test_groups_to_add = 5
    number_of_groups_each_user_should_join = 2
    number_of_forum_topics_to_create = 50
    number_of_comments_to_make_per_forum_topic = 3
    number_of_wiki_pages_to_create = 10
    number_of_edits_to_make_per_wiki_page = 3

    # do users
    start_time=datetime.utcnow()    
    create_test_users(db, how_many=number_of_test_users_to_add, print_progress=True)
    elapsed_seconds = max((datetime.utcnow()-start_time).seconds, 1)
    num_per_second = number_of_test_users_to_add / elapsed_seconds
    print "Created %s users in %s seconds ==> %s / sec" % (number_of_test_users_to_add, elapsed_seconds, num_per_second)

    # do groups
    start_time=datetime.utcnow()
    create_test_groups(db, how_many=number_of_test_groups_to_add, print_progress=True)        
    elapsed_seconds = max((datetime.utcnow()-start_time).seconds, 1)
    num_per_second = number_of_test_groups_to_add / elapsed_seconds
    print "Created %s groups in %s seconds ==> %s / sec" % (number_of_test_groups_to_add, elapsed_seconds, num_per_second)

    # do users joining groups                                                           
    start_time=datetime.utcnow()
    total_joins = join_users_to_groups(db, how_many_groups_per_user=number_of_groups_each_user_should_join, print_progress=True)        
    elapsed_seconds = max((datetime.utcnow()-start_time).seconds, 1)
    num_per_second = total_joins / elapsed_seconds
    print "Did %s group joins in %s seconds ==> %s / sec" % (total_joins, elapsed_seconds, num_per_second)

    # do forum topics and comments                                                           
    start_time=datetime.utcnow()
    make_forum_posts(db, how_many_items=number_of_forum_topics_to_create, how_many_comments_per_item=number_of_comments_to_make_per_forum_topic, print_progress=True)
    elapsed_seconds = max((datetime.utcnow()-start_time).seconds, 1)
    total_posts = number_of_forum_topics_to_create*(number_of_comments_to_make_per_forum_topic+1)
    num_per_second = total_posts / elapsed_seconds
    print "Posted %s messages in %s seconds ==> %s / sec" % (total_posts, elapsed_seconds, num_per_second)

    # do wiki page and revisions                                                           
    start_time=datetime.utcnow()
    make_wiki_pages(db, how_many_pages=number_of_wiki_pages_to_create, how_many_edits_per_page=number_of_edits_to_make_per_wiki_page, print_progress=True)    
    elapsed_seconds = max((datetime.utcnow()-start_time).seconds, 1)
    total_pages_or_revisions = number_of_wiki_pages_to_create*(number_of_edits_to_make_per_wiki_page+1)
    num_per_second = total_pages_or_revisions / elapsed_seconds
    print "Made %s wiki pages/revisions in %s seconds ==> %s / sec" % (total_pages_or_revisions, elapsed_seconds, num_per_second)
                                                           
    db.close()
