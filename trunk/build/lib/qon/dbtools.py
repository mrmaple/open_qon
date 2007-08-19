"""
$Id: dbtools.py,v 1.3 2005/04/12 04:45:46 jimc Exp $
"""

from dulcinea.database import pack_oid, unpack_oid
from qon.base import get_user_database
from qon.user import User, UserGroup
import qon.api

def init_database(db):
    for name, modname, klassname in [
        ('list_db', 'qon.list_db', 'ListDB'),
        ('log_db', 'qon.log', 'LogDB'),
        ('user_db', 'qon.user_db', 'UserDB'),
        ('usergroup_db', 'qon.user_db', 'UserGroupDB'),
        ('session_manager', 'qon.session', 'QonSessionManager'),
        ('group_db', 'qon.group_db', 'GroupDB'),
        ('misc_db', 'qon.user_db', 'MiscDB'),
        ]:
        db.init_root(name, modname, klassname)
        
def add_real_data(db):
    for group in ['admin', 'staff', 'users']:
        ug = UserGroup(group)
        db.usergroup_db.add_usergroup(ug)
        
    group_admin = db.usergroup_db['admin']
    group_staff = db.usergroup_db['staff']
    group_users = db.usergroup_db['users']

    for (user_id, group_id, name, email) in [
        ('admin', 'admin', "Administrative User", "ned@maplesong.com"),
        ('jimc', 'users', "Jim Carroll", "jimc@maplesong.com"),
        ]:
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

def check_users(db):
    user_db = get_user_database()
    for obj in db.iterate():
        if type(obj) is User:
            user = user_db.get_user(obj.get_user_id())
            if not user:
                try:
                    user = user_db.retired_users[obj.get_user_id()]
                    retired = True
                except:
                    retired = False
                
                if retired:
                    print "Retired:  0x%x: %s" % (unpack_oid(obj._p_oid), obj)
                else:
                    print "NOT FOUND: 0x%x: %s" % (unpack_oid(obj._p_oid), obj)


def find_user_id(db, user_id):
    user_db = get_user_database()
    for obj in db.iterate():
        if type(obj) is User:
            if obj.get_user_id() == user_id:
                print "0x%x: %s" % (unpack_oid(obj._p_oid), obj)


def essential_content(db):
    """ Add front page parameters, user agreement, and other basics
    that are referenced in the code. """
    wiki = db.group_db.get_group('sitedev').wiki
    author = db.user_db.get_user('admin')

    name = "front_page_parameters"
    title = name
    qon.api.wiki_edit_page(wiki, None, name, author, name, front_page_params)

    name = "homepage_welcome"
    title = name
    qon.api.wiki_edit_page(wiki, None, name, author, name, homepage_welcome)


front_page_params = """
This page defines the search parameters used to generate the "Front Page News" on the homepage.

 * **subtitle**: the subtitle that appears below Front Page News
 * **howMany**: the number of items to display
 * **type**: the types of content to include.  Valid choices are Discussion, DiscussionComment, Usernews, UsernewsComment, Poll, User, Group, Wikipage.
 * **sort**: date or karma
 * **minKarma**: the minimum feedback score
 * **maxAgeInSeconds**: the time window (in seconds) that an item must have been updated.  Good choices here are 259200 (3 days), 604800 (1 week), and 1209600 (2 weeks), but you can insert any value you like here.
 * **minCreationWeeks**: Creation date of an item must be after x weeks ago.
 * **tag_cloud_size**: The number of clouds to show on the front page.  It will show only the most popular tags.  Set it to zero to remove the tag cloud from the front page.
 * **tag_cloud_message**:A message that appears just before the tag cloud on the front page.  It must be a single line (don't hit return.)

--------------------------------------------

subtitle=Recent Highly Rated Discussions

howMany=12

type=Discussion

type=Usernews

type=Poll

sort=karma

minKarma=10

maxAgeInSeconds=604800

minCreationWeeks=4.0

tag_cloud_size=40

tag_cloud_message=<div class="indent-small">Tags are words or labels that members can use to bookmark or draw attention to content. Here's <A HREF="/group/tagging_sandbox/ws/Tagging%20FAQ/">more about tagging.</A></div>
"""


homepage_welcome = """
<!-- Begin Editable Welcome Message -->
<h1>Welcome to ned</h1>

<div class="indent-small">

<P>
ned is a community of activists and social entrepreneurs who are focused
on making the world a better place, and develping friendships and 
working relationships with others all over the world.
</P>

</div>
<!-- End Editable Welcome Message -->
"""
