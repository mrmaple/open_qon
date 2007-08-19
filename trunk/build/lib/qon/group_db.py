"""
$Id: group_db.py,v 1.66 2007/01/21 17:02:12 jimc Exp $

"""
from datetime import datetime, timedelta
from persistent.list import PersistentList
from qon.base import get_usergroup_database, transaction_commit
from qon.user import HasOwnership, NotEnoughPrivileges, UserGroup, HasEmail
from qon.user_db import GenericDB
from qon.mod import SponsoredQueue
from qon.group import Group
import qon.util

class Invitations(GenericDB):
    """Holds mapping of group invitations."""
    
    def __init__(self):
        GenericDB.__init__(self)
        
    def add_invitation(self, user_email, group):
        if not self.has_key(user_email):
            self[user_email] = PersistentList()
        self[user_email].append(group.get_user_id())
        
    def remove_invitation(self, user_email, group):
        if self.has_key(user_email):
            group_id = group.get_user_id()
            while group_id in self[user_email]:
                self[user_email].remove(group_id)

            if len(self[user_email]) == 0:
                del self[user_email]
    
    def remove_all_user_invitations(self, user, group):
        """Remove invitations from group to all of user's e-mails. Note that user could be a string."""
        if isinstance(user, HasEmail):
            for email in user.email_list():
                self.remove_invitation(email, group)
        else:
            self.remove_invitation(user, group)

    def get_invitations(self, user, group_db):
        """Return groups user has been invited to join.
        As a SIDE EFFECT, removes group invitations if user is already a member.
        """
        gids = []
        for email in user.email_list():
            if self.has_key(email):
                gids.extend(self[email])
        gids = qon.util.unique_items(gids)
        groups = [group_db[g] for g in gids]
        
        # remove groups if user is already a member; this can happen if user
        # adds an e-mail to his account after it was used to invite him into a group
        to_remove = []
        for g in groups:
            if g.is_member(user) or not g.is_invited(user):
                to_remove.append(g)
                self.remove_all_user_invitations(user, g)
        
        for g in to_remove:
            groups.remove(g)
                
        return groups
        
       

class GroupDB(GenericDB, HasOwnership):
    """Database for Groups (qon.group.Group).
    
    When a new group is added to the database, it is automatically
    added to the moderation queue.
    
    Users must have write permission on db in order to create groups.
    """
    
    _karma_new_group        = 10    # cost to create new group
    _karma_sponsor_group    = 5     # cost to sponsor group
    _karma_pm_group         = 1     # cost to PM entire group

    def __init__(self):
        GenericDB.__init__(self)
        HasOwnership.__init__(self)
        self.mod_queue = SponsoredQueue()
        self.invitations = Invitations()
        
    def get_group(self, group_id):
        """Return the group with given group_id, or None if not found."""
        return self.root.get(group_id)

    def add_group(self, group):
        self[group.user_id] = group
        self.mod_queue.add_to_queue(group)
        
    def remove_group(self, group):  
        del self[group.user_id]
        self.mod_queue.remove_from_queue(group)
        
        # quit groups that group is a member of
        for g in self.member_groups(group):
            self.leave_group(g, group)
            
        # remove members from group
        for member in group.get_member_list():
            self.leave_group(member, group)

        # remove owners from group
        for owner in group.get_owners():
            self.leave_group(owner, group)
        
        # delete usergroup - must be last, since leave_group needs it
        get_usergroup_database().remove_usergroup(group.user_id)
            
    def active_groups(self):
        return [self[group] for group in self.root.keys() if self[group].get_state() == 'accepted']

    def recently_active_groups(self, user=None, days_cutoff=3):
        cutoff_date = datetime.utcnow() - timedelta(days=days_cutoff)
        return [self[group] for group in self.root.keys() if self[group].can_read(user) and self[group].watchable_last_change() > cutoff_date]        

    def recently_active_tuples(self, user=None, days_cutoff=3):
        """Returns a sorted list of (group, active_discussions, active_pages) tuples
        for groups that have been active in the last X days and are readdable by the given user"""
        cutoff_date = datetime.utcnow() - timedelta(days=days_cutoff)
        readable_active_tuples = [(g, g.blog.num_active_items(days=days_cutoff, consider_comments=True)[0], g.wiki.num_active_pages(days=days_cutoff)[0]) for g in self.active_groups() if g.can_read(user) and g.watchable_last_change() > cutoff_date]        
        sorted_group_tuples = qon.util.sort_list(readable_active_tuples, lambda x: x[0].watchable_last_change())
        return sorted_group_tuples     
    
    def recent_groups(self, age):
        """Recent recently-created groups not older than age."""
        cutoff = datetime.utcnow() - age
        groups = [g for g in self.active_groups() if g.date > cutoff]
        return qon.util.sort_list(groups, lambda x: x.date)
    
    def active_groups_anon(self):
        """Active groups available for anonymous browsing"""
        groups = self.active_groups()
        return [group for group in groups if group.anon_read]
        
    def rejected_groups(self):
        return [self[group] for group in self.root.keys() if self[group].get_state() == 'rejected']

    def limbo_groups(self):
        return [self[group] for group in self.root.keys() if self[group].get_state() == 'limbo']

    def top_level_groups(self):
        """ Return top-level groups.  Currently hard-coded. """        
        top_level_group_ids = ('issues-business', 'issues-cyf', 'issues-education', 'issues-env', \
                               'issues-health', 'issues-pol', 'regional', 'issues-religion', \
                               'issues-soc', 'issues-tech', 'issues-general', \
                               'private', 'public', 'social', 'orgs-general', \
                               'help', 'community-general', 'suggestions', \
                               'general-other')
        top_level = [self.get_group(g) for g in top_level_group_ids]
        return top_level
    
    #
    # permission rules
    #
    can_create_group = HasOwnership.can_write
    
    #
    # group management
    #
    def can_pay_for_new_group(self, user):
        return user.can_give_karma(self._karma_new_group)
        
    def can_pay_to_sponsor_group(self, user):
        return user.can_give_karma(self._karma_sponsor_group)
        
    def can_pay_for_pm_group(self, user):
        return user.can_give_karma(self._karma_pm_group)

    def create_group(self, user_id, name, owner, description='',
        member_perms=[],
        other_perms=[],
        member_join_perms=[],
        other_join_perms=[],
        anon_read=0,
        no_pay=False):
        """Create a new group.
        
        member_perms, other_perms: see qon.group.HasAccessPolicy
        member_join_perms, other_join_Perms: see qon.group.HasMembership
        """
        
        user_id = user_id.lower()
        
        if self.root.has_key(user_id) or get_usergroup_database().has_key(user_id):
            raise KeyError, "Key %s already exists." % user_id

        if not no_pay:
            # charge owner for new group - don't create group if can't pay
            from qon.karma import NoKarmaToGive
            try:
                owner.pay_karma(self._karma_new_group)
            except NoKarmaToGive:
                return None

        group = Group(user_id=user_id, name=name, owner=owner)
        group.add_owner(owner)
        group.add_sponsor(owner)
        group.anon_read = anon_read
        group.description = description
        
        usergroup = UserGroup(group.user_id)
        get_usergroup_database().add_usergroup(usergroup)
        group.set_owning_group(usergroup)
        
        # members must have at least read access -- otherwise, what's the point of membership?
        mem_perms = member_perms
        if 'read' not in mem_perms:
            mem_perms.append('read')
        
        group.set_group_perms(mem_perms)
        group.set_other_perms(other_perms)
        group.get_members().set_group_perms(member_join_perms)
        group.get_members().set_other_perms(other_join_perms)
        
        # flush owner's group list cache
        self._flush_user_data_caches(owner)

        self.add_group(group)
        return group
        
    def add_sponsor(self, group, sponsor):
        """Add sponsor to group. Returns True on success"""
        
        # check if already a sponsor so we don't pay twice
        if group.is_accepted() or (sponsor in group.get_sponsors()):
            return True
        
        # pay for sponsorship
        from qon.karma import NoKarmaToGive
        try:
            sponsor.pay_karma(self._karma_sponsor_group)
        except NoKarmaToGive:
            return False
        
        self.mod_queue.add_sponsor(group, sponsor)
        
        # if group got enough sponsors:
        if group.is_accepted():
            self._sponsors_to_members(group)
        
        return True

    def force_accept(self, group):
        """Force a Sponsored group into accepted state."""
        self.mod_queue.force_accept(group)
        
        # sponsors become members
        if group.is_accepted():
            self._sponsors_to_members(group)
    
    def _sponsors_to_members(self, group):
        if group.is_accepted():
            for user in group.get_sponsors():
                if not group.is_owner(user):
                    self.join_group(user, group, force=1)
    
    #
    # user/owner/sponsor management
    #
    def owned_groups(self, user):
        """Return list of groups owned by owner. owner can be a User or Group."""
        
        if not hasattr(user, '_group_owned_groups'):
            user._group_owned_groups = [self[group] for group in self.root.keys() \
                if self[group].is_owner(user)]
            
        return user._group_owned_groups

    def member_groups(self, user):
        """Return list of groups user is a member of. user can be a User or Group."""
        
        if not hasattr(user, '_group_member_groups'):
            # be sure to use "slow" version of is_member to prevent it recursing back
            user._group_member_groups = [self[group] for group in self.root.keys() \
                if self[group].is_member(user, slow=True)]

        return user._group_member_groups

    def users_groups(self, user):
        """Return groups relevant to user: owned + member, with duplicates removed."""
        return qon.util.unique_items(self.owned_groups(user) + self.member_groups(user))
    
    def users_invitations(self, user):
        """Return groups user has been invited to join."""
        return self.invitations.get_invitations(user, self)
    
    def join_group(self, user, group, force=0):
        """User joins group. Disable can_join check by passing True to force."""
        if not force and not group.can_join(user):
            raise NotEnoughPrivileges
            
        group.add_member(user)
        user.add_to_group(get_usergroup_database().get_usergroup(group.get_user_id()))
        if hasattr(user, 'karma_activity_credit'):
            # groups can join groups, and groups don't have karma_activity_credit
            user.karma_activity_credit()
        
        self._flush_user_data_caches(user)

    def _flush_user_data_caches(self, user):
        if hasattr(user, '_group_owned_groups'):
            del user._group_owned_groups
        if hasattr(user, '_group_member_groups'):
            del user._group_member_groups
            
    def decline_invitation(self, user, group):  
        """Decline an invitation to join group. Removes invitations."""
        if group.is_invited(user):
            group.remove_invitation(user)

    def leave_group(self, user, group):
        group.remove_member(user)
        user.remove_from_group(get_usergroup_database().get_usergroup(group.get_user_id()))
        self._flush_user_data_caches(user)
        
    def set_group_owners(self, group, users):
        """Set users as owners of group."""
        
        # Ensure that if we are removing an existing owner, he remains a member
        for u in group.owners:
            if u not in users:
                group.add_member(u)
                self._flush_user_data_caches(u)

        group.set_owner(users)
        for u in users:
            self._flush_user_data_caches(u)
                    
    def notify_new_user(self, user):
        """Called by user_db when a new user is created."""
        # join to default group
        g = self.root.get('community-general')
        if g:
            self.join_group(user, g)
            
    def notify_email_confirmed(self, user, email):
        """Notice user just confirmed email."""
        
        # make sure user isn't still invited to groups he owns or is a member of
        for g in self.users_groups(user):
            g.remove_invitation(user)

def create_initial_groups():
    """Create initial top-level groups if they don't already exist."""
    
    from base import get_group_database, get_user_database
    import api
    
    # we want any groups we create in here to be active immediately
    save_min_sponsors = Group._min_sponsors
    Group._min_sponsors = 1
    
    user_db = get_user_database()
    group_db = get_group_database()
    
    user_admin = user_db['admin']
    
    def create_group(user_id, name, desc, owner, parent_id, join_pol, memb_vis, memb_edit=''):
        if not group_db.has_key(user_id):
            g = group_db.create_group(user_id=user_id,
                name=name,
                description=desc,
                owner=owner,
                no_pay=True)
            group_db.force_accept(g)
            if parent_id:
                group_db.join_group(g, group_db[parent_id], force=1)
    
        g = group_db[user_id]
        if join_pol:
            api.group_set_join_policy(user_admin, g, join_pol)
            if join_pol == 'open':
                # if membership is open, allow non-members to read
                api.group_set_other_perms(user_admin, g, 'ro')
        if memb_vis:
            api.group_set_membership_visible(user_admin, g, memb_vis)
        if desc:
            api.group_set_settings(user_admin, g, description=desc)
        if memb_edit:
            api.group_set_member_edit(user_admin, g, memb_edit)
            
        # set date of formation
        create = datetime(2004, 05, 10, 12, 0, 0)
        g.date = create
    
    
    groups = [
        ('top', 'Top', 'This group contains the top-level groups.', user_admin, None, '', 'open', ''),
        ('regional', 'Regional', 'Contains groups with a regional focus.', user_admin, 'top', '', 'open', ''),
        ('orgs', 'Organizations', 'Contains categories of organizations.', user_admin, 'top', '', 'open', ''),
        ('community', 'Community', 'Contains groups that are focused or based on ned.com.', user_admin, 'top', '', 'open', ''),
        ('issues', 'Issues', 'Contains groups focused on particular issues.', user_admin, 'top', '', 'open', ''),
        ('general', 'General', 'Contains groups that don\'t belong in other categories.', user_admin, 'top', 'open', 'open', ''),
        ('general-other', 'General', 'Contains groups that don\'t belong in other categories.', user_admin, 'general', 'open', 'open', ''),
        ('help', 'Help', 'Contains site help.', user_admin, 'community', '', 'open', ''),
        ('community-general', 'Community - General',
            '', user_admin, 'community', 'open', 'open', 'member'),
        ('suggestions', 'Suggestions', 'For community suggestions.', user_admin, 'community-general', '', 'open', ''),
        ('public', 'Public sector',
            'Groups operating in the public sector should join this group.', user_admin, 'orgs', 'open', 'open', 'member'),
        ('private', 'Private sector',
            'Groups operating in the private sector should join this group.', user_admin, 'orgs', 'open', 'open', 'member'),
        ('social', 'Social sector',
            'Groups operating in the social sector should join this group.', user_admin, 'orgs', 'open', 'open', 'member'),
        ('orgs-general', 'Organizations - General',
            "For organizations that don't fit in other categories.", user_admin, 'orgs', 'open', 'open', 'member'),
        ('issues-business', 'Business',
            '', user_admin, 'issues', 'open', 'open', 'member'),
        ('issues-cyf', 'Children - Youth - Families',
            '', user_admin, 'issues', 'open', 'open', 'member'),
        ('issues-education', 'Education',
            '', user_admin, 'issues', 'open', 'open', 'member'),
        ('issues-env', 'Environment - Conservation',
            '', user_admin, 'issues', 'open', 'open', 'member'),
        ('issues-health', 'Health Care',
            '', user_admin, 'issues', 'open', 'open', 'member'),
        ('issues-pol', 'Policy - Politics',
            '', user_admin, 'issues', 'open', 'open', 'member'),
        ('issues-religion', 'Religion',
            '', user_admin, 'issues', 'open', 'open', 'member'),
        ('issues-soc', 'Social Justice - Human Services',
            '', user_admin, 'issues', 'open', 'open', 'member'),
        ('issues-tech', 'Technology',
            '', user_admin, 'issues', 'open', 'open', 'member'),
        ('issues-general', 'Issues - General',
            '', user_admin, 'issues', 'open', 'open', 'member'),
        ('ned', '<ned> Network',
            '', user_admin, '', '', '', ''),
        ('ned-internal', 'Ned - Internal',
            '', user_admin, '', '', '', ''),
        ('sitedev', 'Site Development',
            '', user_admin, 'ned-internal', '', '', ''),
        ]
    
    for user_id, name, desc, owner, parent_id, join_pol, memb_vis, memb_edit in groups:
        create_group(user_id, name, desc, owner, parent_id, join_pol, memb_vis, memb_edit)
    
    # Help group
    g_help = group_db['help']
    api.group_set_anon_read(user_admin, g_help, True)
                            
    # ON groups
    g_on = group_db['ned']
    group_db.join_group(g_on, group_db['private'], force=1)
    group_db.join_group(g_on, group_db['public'], force=1)
    group_db.join_group(g_on, group_db['social'], force=1)
    api.group_set_owners_by_user_id(user_admin, g_on, ['admin', 'jimc'])
    api.group_set_join_policy(user_admin, g_on, 'owner')
    api.group_set_invite_policy(user_admin, g_on, 'owner')
    api.group_set_membership_visible(user_admin, g_on, 'open')
    api.group_set_member_edit(user_admin, g_on, True)
    api.group_set_anon_read(user_admin, g_on, True)
        
    g_on_int = group_db['ned-internal']
    api.group_set_owners_by_user_id(user_admin, g_on_int, ['admin', 'jimc'])
    api.group_set_join_policy(user_admin, g_on_int, 'owner')
    api.group_set_invite_policy(user_admin, g_on_int, 'owner')
    api.group_set_membership_visible(user_admin, g_on_int, 'member')
    api.group_set_member_edit(user_admin, g_on_int, True)
    api.group_set_anon_read(user_admin, g_on_int, False)
    
    g_sitedev = group_db['sitedev']
    api.group_set_owners_by_user_id(user_admin, g_sitedev, ['admin', 'jimc'])
    
    Group._min_sponsors = save_min_sponsors
    
# ---------------------------------------------------------------------

def upgradeFixMemberPerms():
    """Fix duplicate permissions in member list perms."""
    from base import get_group_database
    
    for g in get_group_database().root.values():
        m = g.get_members()
        perms = m.get_perms()
        
        # new code will call unique_items on perms
        m.set_other_perms(perms[2])
        m.set_group_perms(perms[1])
        m.set_owner_perms(perms[0])
    

def upgradeAddInvitations():
    from base import get_group_database, get_user_database
    from persistent.mapping import PersistentMapping
    user_db = get_user_database()
    db = get_group_database()
    
    db.invitations = Invitations()
    for g in db.root.values():
        g.invited_users = PersistentMapping(g.invited_users)
        for email in g.invited_users.keys():
            db.invitations.add_invitation(email, g)
            
    # remove lingering invitations from when our code was dumb and left them
    for g in db.root.values():
        for email in g.invited_users.keys():
            try:
                user = user_db.get_user_by_email(email)
            except KeyError:
                pass
            else:
                if g.is_member(user):
                    del g.invited_users[email]
                    db.invitations.remove_all_user_invitations(user, g)

def upgradeFixInvitations():
    """Remove any lingering invitations to users who are members of groups they are invited to."""
    from base import get_group_database, get_user_database
    
    user_db = get_user_database()
    group_db = get_group_database()
    
    for user in user_db.root.values():
        for g in group_db.users_groups(user):
            g.remove_invitation(user)
            group_db.invitations.remove_all_user_invitations(user, g)

def cleanup_invitations():
    """Remove duplicate and redundant invitations from global list and individual groups."""
    
    from base import get_group_database, get_user_database

    def user_name(user_or_email):
        if isinstance(user_or_email, HasEmail):
            return user_or_email.display_name()
        else:
            return user_or_email
    
    group_db = get_group_database()
    user_db = get_user_database()
    
    # sanity check and clean each group's invitation list
    for g in group_db.root.values():
        for user_or_email in g.invited_users.keys():
            user = user_db.resolve_user(user_or_email)
            if user:
                if g.is_member(user) or g.is_owner(user):
                    print "%s is already a member of %s, removing invitation." % (
                        user_name(user),
                        g.name)
                    g.remove_invitation(user_or_email)

    # check and clean global list
    for (email, invites) in group_db.invitations.root.iteritems():
        user = user_db.resolve_user(email)
        if user:
            for group_id in invites:
                g = group_db[group_id]
                if g.is_member(user) or g.is_owner(user):
                    print "%s is a member of %s, removing global invitation." % (
                        user_name(user),
                        g.name)
                    group_db.invitations.remove_all_user_invitations(user, g)
    
    # remove duplicate group entries in global list
    for (email, invites) in group_db.invitations.root.iteritems():
        invites = qon.util.unique_items(invites)
        group_db.invitations.root[email] = invites

def flush_user_data_cache(user):
    from base import get_group_database
    get_group_database()._flush_user_data_caches(user)
    
def flush_all_owners_data_cache():
    """Flush all group owners' data caches."""
    from base import get_group_database
    
    group_db = get_group_database()
    
    for group_id, group in group_db.root.iteritems():
        for user in group.owners:
            flush_user_data_cache(user)
