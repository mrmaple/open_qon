"""
$Id: group.py,v 1.78 2007/05/01 11:41:29 jimc Exp $
:Author:    Jim Carroll

"""
from datetime import datetime, timedelta
from persistent.list import PersistentList
from persistent.mapping import PersistentMapping
from dulcinea.typeutils import typecheck

from qon.base import QonPersistent, get_group_database, get_user_database
from qon.user import HasEmail, HasUserID, HasOwnership, \
    NotEnoughPrivileges, HasGroupMembership
from qon.mod import Sponsored
import qon.wiki
import qon.tags
import qon.blog
import qon.defer
from qon.file import FileDB
from qon.watch import Watchable
from qon.ticket import TicketTracker
from qon.util import unique_items, iso_8859_to_utf_8
from qon.poll import PollContainer

# these names are not permitted to be used as group names or wiki page names
# FIXME actually enforce this when creating new groups and new wiki pages!!
reserved_names = ['news', 'poll', 'file', 'ws', 'active', 'recent', 'all', 'member', 'manage', 'issues', 'staff', 'about']

class Members(QonPersistent, HasOwnership):
    """Manages member list.
    
    action      permission required
    see members read
    join        write
    invite      manage
    
    Examples:
        open membership, anyone can join: world/other has write permission
        member and owner can invite: owner and group has manage permission
        owner only can invite: owner has manage, group has read/write
        
    Note: even though we use variables named 'user,' groups can also be
    members.
    """
    
    def __init__(self):
        HasOwnership.__init__(self)
        self.__members = []
        
    def add_member(self, user):
        typecheck(user, HasUserID)
        if user not in self.__members:
            self.__members.append(user)
            self._p_changed = 1
        
    def remove_member(self, user):
        if user in self.__members:
            self.__members.remove(user)
            self._p_changed = 1
    
    def is_member(self, user):
        return user in self.__members
        
    def get_members(self):
        return self.__members
    
    can_see_members = HasOwnership.can_read
    can_join = HasOwnership.can_write
    can_invite = HasOwnership.can_manage

class HasMembership:
    """Mixin class providing membership-related functionality

    Note: even though we use variables named 'user,' groups can also be
    members.
    """
    
    def __init__(self):
        self.__members = Members()
        self.__members_can_associate_groups = True
        self.invited_users = PersistentMapping()
        
    def upgradeToVersion1(self):
        self.__members_can_associate_groups = True
        
    def add_invitation(self, user_or_email, inviter):
        """Invite user_or_email to join group.
        
        Note that invitations can be to any object or to e-mails, though
        usually here they are e-mails.
        """
        
        # don't add invitation if user_or_email is already a member or an owner
        user_object = get_user_database().resolve_user(user_or_email)
        if user_object:
            if self.is_member(user_object):
                return
            if hasattr(self, 'is_owner'):   # use hasattr because is_owner is not a HasMembership method
                if self.is_owner(user_object):
                    return
            
        if self.__members.can_invite(inviter):
            self.invited_users[user_or_email] = inviter
            
            # tell GroupDB about the invitation
            get_group_database().invitations.add_invitation(user_or_email, self)
        else:
            raise NotEnoughPrivileges
            
    def remove_invitation(self, user_or_email):
        """Remove an invitation to user_or_email. Note that user can be a User object or a string."""
        if self.is_invited(user_or_email):
            del self.invited_users[user_or_email]
            get_group_database().invitations.remove_all_user_invitations(user_or_email, self)
            
    def is_invited(self, user_or_email):
        """Returns true if user is invited. As a SIDE EFFECT, replaces e-mail entries
        with actual User objects. This has the effect of not necessarily preserving
        the name of the inviter, in the case where different people have invited the
        same user using different e-mail addresses.
        """
        if user_or_email in self.invited_users:
            return True
            
        if isinstance(user_or_email, HasEmail):
            emails = user_or_email.email_list()
            for email in emails:
                if email in self.invited_users:
                    # replace email with user   XXX this is a little screwy
                    self.invited_users[user_or_email] = self.invited_users[email]
                    del self.invited_users[email]
                    return True
            
        return False
        
    def add_member(self, user):
        """Add user as member. Removes user from invited_users list if applicable.
        Calls self.notify_members_changed if it exists.
        """
        if user in self.invited_users:
            del self.invited_users[user]
            get_group_database().invitations.remove_all_user_invitations(user, self)
        
        if isinstance(user, HasEmail):
            for email in user.email_list():
                if email in self.invited_users:
                    del self.invited_users[email]
                
        self.__members.add_member(user)
        self.notify_members_changed()

    def remove_member(self, user):
        """Remove user (or group) as a member.
        Calls self.notify_members_changed if it exists.
        """
        # If removing a user, ensure remaining members are not groups solely
        # owned by departing member.
        self.remove_sole_owned_groups(user)
        self.__members.remove_member(user)
        self.notify_members_changed()

    def notify_members_changed(self):
        """If subclass defines, called by add_member and remove_member."""
        pass
        
    def sole_owned_group_members(self, user):
        """Return list of group members that are solely owned by user."""
        solo = []
        groups = get_group_database().owned_groups(user)
        for group in groups:
            if self.is_member(group):
                found_other_member = 0
                for owner in group.owners:
                    if owner != user and self.is_member(owner):
                        found_other_member = 1
                        break
                if not found_other_member:
                    solo.append(group)
        return solo
        
    def remove_sole_owned_groups(self, user):
        """Remove groups owned by user unless also owned by another member."""
        sole_owned = self.sole_owned_group_members(user)
        db = get_group_database()
        for g in sole_owned:
            db.leave_group(g, self)
            
    def is_member(self, user_or_email, slow=False):
        user = get_user_database().resolve_user(user_or_email)
        
        if not user:
            # user not in databse
            return False
        
        if slow:
            return self.__members.is_member(user)
        else:
            # group_db can do a faster membership check than my own list of members
            return self in get_group_database().member_groups(user)
    
    def can_join(self, user):
        """Return True if user can join group. If user defines an `owners' attribute,
        like Groups, return True if any one of owners is a member.
        """
        # FIXME is_accepted is a method of HasState, not HasMembership, so use hasattr
        if not self.is_accepted():
            return False
        
        user_is_a_group = hasattr(user, 'owners')
        
        if self.__members.can_join(user) or self.is_invited(user):
            # if user is not a group, we're done
            if not user_is_a_group:
                return True
        
        if user_is_a_group:
            for u in user.owners:
                # Group "user" can join parent group "self" if one of "user"'s owners is
                # an owner of "self," or if "self" allows members to associate groups, and
                # one of "user"'s owners is a member of "self."
                if self.is_owner(u) or (self.__members_can_associate_groups and self.is_member(u)):
                    return True
        
        return False
        
    def can_invite(self, user):
        return self.__members.can_invite(user)
        
    def get_members(self):
        return self.__members
    
    def get_member_list(self):
        return self.__members.get_members()
        
    def members_can_associate_groups(self):
        return self.__members_can_associate_groups
    
    def set_members_can_associate_groups(self, val):
        self.__members_can_associate_groups = val
        
class HasAccessPolicy(HasOwnership):
    """Mixin class providing access-policy and related functions.

    Extends functionality of HasOwnership to allow anonymous users read access

    owner permissions:  read/write/manage
    group permissions:  read: members can read
                        write: members can write/edit
                        manage: members can manage
    other permissions:  read: non-members can read
                        write: non-members can write/edit
                        manage: non-members can manage (not a good idea)

    anon_read is set to allow anonymous (not signed in) users read-only
    
    """

    def __init__(self):
        HasOwnership.__init__(self)
        self.anon_read = 0
        self.set_group_perms(['read'])
        self.set_other_perms(['read'])

    def can_read(self, user):
        if self.anon_read:
            return True
        
        if user and user.is_admin():
            return True
            
        return HasOwnership.can_read(self, user)
        
    def can_edit(self, user):
        if user:
            return user.can_post() and self.can_write(user)
        else:
            # anon users may have write permission somewhere
            return self.can_write(user)

class Group(QonPersistent, HasUserID, HasGroupMembership, Sponsored,
    HasMembership, HasAccessPolicy, Watchable, qon.blog.IHasBlog, qon.tags.HasTags):
    """Encapsulates Group functionality
    
    A group is created by a single user, but sponsored by several. Usually
    a group must obtain a minimum number of co-sponsors before it is presented
    to membership for voting. In the current implementation, VOTING IS DISABLED.
    
    Groups can be members of other groups. Accessors like get_all_owners only look
    one level deep: no recursion.
    """
    
    persistenceVersion = 6
    
    _min_sponsors   = 5         # minimum number of sponsors before group is active (including creator)
    _time_to_sponsor = timedelta(days=14)   # time in which a sponsor must be found
    _rollup_subgroups = False   # disable rolling up of blogs/wikis from subgroups
    
    def __init__(self, user_id, name, owner):
        HasUserID.__init__(self)
        HasGroupMembership.__init__(self)
        Sponsored.__init__(self, self._min_sponsors)
        HasMembership.__init__(self)
        HasAccessPolicy.__init__(self)
        Watchable.__init__(self)
        qon.tags.HasTags.__init__(self)
        self.user_id = user_id
        self.name = name
        self.description = ''
        self.date = datetime.utcnow()
        self.__karma_score = 0
        self.__deferrals = qon.defer.DeferralList()
        
        # set owner, so other modules like Wiki, Blog, etc., will have it
        self.add_owner(owner)

        self.wiki = qon.wiki.Wiki(self)
        self.blog = qon.blog.Blog(self)
        self.file_db = FileDB(self)
        self.polls = PollContainer(self)
        self.trackers = PersistentList()

        # track the number of PMs sent to members of this group
        self.total_group_pms = 0

    def upgradeToVersion6(self):
        qon.tags.HasTags.__init__(self)
        self.version_upgrade_done()

    def upgradeToVersion5(self):
        self.total_group_pms = 0
        self.version_upgrade_done()

    def upgradeToVersion4(self):
        self.name = iso_8859_to_utf_8(self.name)
        self.description = iso_8859_to_utf_8(self.description)

    def upgradeToVersion3(self):
        self.polls = PollContainer(self)
        self.version_upgrade_done()
        
    def upgradeToVersion2(self):
        HasMembership.upgradeToVersion1(self)
        
    def upgradeToVersion1(self):
        self.date = datetime.utcnow()
        
    def can_read(self, user):
        if HasAccessPolicy.can_read(self, user):
            return True
        
        if not self.is_accepted():
            # while the group is not accepted, allow full access
            return True
        return False

    def is_private(self):
        '''Returns true if this non-members have no access to the group.
        Added 03/15/2006 by Alex'''
        return len(self.get_perms()[2]) == 0
        
    def display_name(self):
        return self.name
        
    def get_all_blogs(self):
        """Returns list of all blogs in all sub-groups, including this one.
        Also includes blogs of wiki pages.
        """
        if not self._rollup_subgroups:
            return [self.blog]
            
        blog_list = [g.blog for g in self.get_group_members()]
        blog_list.append(self.blog)
        return blog_list
        
    def get_all_wikis(self):
        if not self._rollup_subgroups:
            return [self.wiki]
            
        wiki_list = [g.wiki for g in self.get_group_members()]
        wiki_list.append(self.wiki)
        return wiki_list
        
    def get_all_owners(self):
        """Returns list of owners of all groups contained within this one, including this one."""
        if not self._rollup_subgroups:
            return self.owners
            
        owners = [g.owners for g in self.get_group_members()]
        owners.extend(self.owners)
        return owners

    def get_group_members(self):
        """Return members that are groups."""
        if not hasattr(self, '_cache_group_members'):
            self._cache_group_members = [g for g in self.get_member_list() if isinstance(g, Group)]
        return [g for g in self._cache_group_members if g.is_accepted()]

    def recent_changes(self, count=10):
        """Return list of recently changed items, newest first. Items
        will be WikiPages or BlogItems.
        """
        
        recent_blog = qon.blog.recent_items(self.get_all_blogs(), count=count)
        recent_wiki = qon.wiki.recent_items(self.get_all_wikis(), count=count)
        bydate = []
        for i in recent_blog + recent_wiki:
            bydate.append((i.watchable_last_change(), i))
        bydate.sort()
        bydate.reverse()
        
        return [i for date, i in bydate]

    def get_num_members(self):
        """return the number of unique members."""
        return len(unique_items(self.owners + self.get_member_list()))

    def get_total_group_pms(self):
        return self.total_group_pms

    def group_pm_sent(self):
        self.total_group_pms += 1


    def rollup_member_groups(self):
        """Return True if member groups should be rolled up into this group,
        for display or navigational purposes.
        """
        return self._rollup_subgroups
        
    def notify_karma_changed(self):
        """Notice that karma changed in my blog."""
        # this used to call self._calc_karma_score using an hourly defer, moved
        # into cron-hourly.
        self._karma_changed = True
        pass
        
    def notify_members_changed(self):
        if hasattr(self, '_cache_group_members'):
            del self._cache_group_members
        
        # my karma needs to be recalculated if membership changes
        self.notify_karma_changed()
    
    def watchable_name(self):
        return self.name
        
    def watchable_modified_date(self):
        return self.watchable_last_change()
            
    def can_get_karma_from(self, other):
        return not self.is_owner(other)
        
    def get_karma_score(self):
        """Return implied karma."""
        return self.__karma_score

    def _calc_karma_score(self):
        """Calculate implied karma."""
        
        if not hasattr(self, '_karma_changed') or not self._karma_changed:
            return
            
        karma = 0
        
        group_members = self.get_group_members()
        
        for u in unique_items(self.owners + self.get_member_list()):
            if u not in group_members:
                karma += u.get_karma_score()
        
        for i in self.blog.get_items():
            karma += i.get_karma_score()
        
        self.__karma_score = karma
        del self._karma_changed

    def reserved_group_id(cls, group_id):
        """Returns True if group_id is a reserved name. NOTE: does not check for valid
        format otherwise. Use HasUserID.valid_user_id.
        
        >>> Group.reserved_group_id('_reserved')
        True
        >>> Group.reserved_group_id('_')
        True
        >>> Group.reserved_group_id('u123')
        True
        >>> Group.reserved_group_id('jimc')
        True
        >>> Group.reserved_group_id('admin')
        True
        >>> Group.reserved_group_id('uabc')
        False
        >>> Group.reserved_group_id('a_b')
        False
        """
        
        group_id = group_id.lower()
        
        # reserve anything with initial underscore
        if group_id.startswith('_'):
            return True
        
        # reserve something that looks like the start of a user id (uX where X is numeric)
        try:
            if group_id.startswith('u') and int(group_id[1]) in range(10):
                return True
        except (IndexError, ValueError):
            pass
            
        # reserve some special names
        if group_id in ['jimc', 'admin', 'browse', 'active', 'recent', 'all']:
            return True
        
        return False
    
    reserved_group_id = classmethod(reserved_group_id)
    
    # delegation of owner/group changes to Members()
    
    def add_owner(self, user):
        HasAccessPolicy.add_owner(self, user)
        self.get_members().add_owner(user)
        
    def remove_owner(self, user):
        HasAccessPolicy.remove_owner(self, user)
        self.get_members().remove_owner(user)
        
    def set_owner(self, user):
        HasAccessPolicy.set_owner(self, user)
        self.get_members().set_owner(user)
        
    def add_owning_group(self, group):
        HasAccessPolicy.add_owning_group(self, group)
        self.get_members().add_owning_group(group)

    def remove_owning_group(self, group):
        HasAccessPolicy.remove_owning_group(self, group)
        self.get_members().remove_owning_group(group)

    def set_owning_group(self, group):
        HasAccessPolicy.set_owning_group(self, group)
        self.get_members().set_owning_group(group)
        
    # IHasBlog methods not implemented by other base classes
    
    def blog_name(self):
        return self.display_name() + ' Discussions'

    def get_name(self):
        return self.name
    
    def get_blog(self):
        return self.blog
        
    def get_wiki(self):
        return self.wiki
        
# ---------------------------------------------------------------------

def _test():
    import doctest, group
    return doctest.testmod(group)
    
if __name__ == "__main__":
    _test()
