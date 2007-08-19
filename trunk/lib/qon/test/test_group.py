#!/usr/bin/env python

"""
$Id: test_group.py,v 1.3 2005/04/12 04:39:13 jimc Exp $
"""

from sancho.utest import UTest
import datetime
import persistent.list

import qon.api
import qon.base
import qon.blog
import qon.defer
import qon.file
import qon.group
import qon.user_db
import qon.wiki

from qon.dbtools import init_database, add_real_data


def open_database():
    return qon.base.open_database('file:test_db.fs')


class NewGroup (UTest):
    """Test formation of new group."""
    
    def __init__ (self, options=None, outfile=None):
        self._user, password = qon.base.get_user_database().new_user_from_email('test@ned.com')
        self._user2, password = qon.base.get_user_database().new_user_from_email('test2@ned.com')
        self._user3, password = qon.base.get_user_database().new_user_from_email('test3@ned.com')
        UTest.__init__(self)

    def check_100_init(self):
        """Check constructor. Should be first case run so other tests can use self._group.
        Cases are run alphabetically.
        """
        
        self._group = qon.api.group_create(self._user, user_id='test',
            name='Test Group',
            owner=self._user,
            description = 'This is the Test Group.')

        assert self._group
        
        # test instance variables
        assert isinstance(self._group, qon.group.Group)
        assert self._group.get_user_id() == 'test'
        assert self._group.name == 'Test Group'
        assert self._group.description == 'This is the Test Group.'
        assert isinstance(self._group.date,  datetime.datetime)
        assert self._group._Group__karma_score == 0
        assert isinstance(self._group._Group__deferrals,  qon.defer.DeferralList)
        assert isinstance(self._group.wiki,  qon.wiki.Wiki)
        assert isinstance(self._group.blog,  qon.blog.Blog)
        assert isinstance(self._group.file_db,  qon.file.FileDB)
        assert isinstance(self._group.trackers,  persistent.list.PersistentList)
        
        # test default assumptions
        assert self._group.anon_read == False
        
        # test users/ownership
        assert self._group.is_owner(self._user)
        assert self._group.is_sponsor(self._user)
        assert not self._group.is_member(self._user)
        
        # test UserGroup
        assert qon.base.get_usergroup_database().get_usergroup('test') in self._group.groups
        
        # test default permissions
        assert 'read' in self._group.get_perms()[0]
        assert 'write' in self._group.get_perms()[0]
        assert 'manage' in self._group.get_perms()[0]
        
        assert 'read' in self._group.get_perms()[1]
        assert not 'write' in self._group.get_perms()[1]
        assert not 'manage' in self._group.get_perms()[1]
        
        assert not 'read' in self._group.get_perms()[2]
        assert not 'write' in self._group.get_perms()[2]
        assert not 'manage' in self._group.get_perms()[2]
        
        assert 'read' in self._group.get_members().get_perms()[0]
        assert 'write' in self._group.get_members().get_perms()[0]
        assert 'manage' in self._group.get_members().get_perms()[0]
        
        assert not 'read' in self._group.get_members().get_perms()[1]
        assert not 'write' in self._group.get_members().get_perms()[1]
        assert not 'manage' in self._group.get_members().get_perms()[1]
        
        assert not 'read' in self._group.get_members().get_perms()[2]
        assert not 'write' in self._group.get_members().get_perms()[2]
        assert not 'manage' in self._group.get_members().get_perms()[2]
        
        # test group properly in database
        assert qon.base.get_group_database()['test'] == self._group
        
        # test initial state
        assert not self._group.is_accepted()
        assert self._group.get_state() == 'pending'
        assert not self._group in qon.base.get_group_database().active_groups()
        assert not self._group in qon.base.get_group_database().recent_groups(datetime.timedelta(days=7))
        assert not self._group in qon.base.get_group_database().rejected_groups()
        assert not self._group in qon.base.get_group_database().limbo_groups()
        assert not self._group in qon.base.get_group_database().active_groups_anon()
        
        # test presence in mod/sponsor queue
        assert not self._group in qon.base.get_group_database().mod_queue.new_items()
        assert self._group in qon.base.get_group_database().mod_queue.pending_items()
        
    def check_ownership(self):
        """Check ownership attributes of group."""
        assert self._group in qon.base.get_group_database().owned_groups(self._user)
        assert self._group in qon.base.get_group_database().users_groups(self._user)
        
        assert not self._group.is_member(self._user)
        assert not self._group in qon.base.get_group_database().member_groups(self._user)
    
    def check_200_sponsor(self):
        """Check sponsorship of group by second user."""
        
        # test not enough sponsors yet (need 5)
        assert not self._group.enough_sponsors()
        assert self._group.min_sponsors == 5

        # for test suite, change min_sponsors to 2
        self._group.min_sponsors = 2
        
        # test sponsoring by owning user, should have no effect
        qon.api.group_sponsor(self._group, self._user)
        assert not self._group.is_accepted()
        assert not self._group.is_member(self._user)
        assert self._group.get_state() == 'pending'
        assert self._group in qon.base.get_group_database().mod_queue.pending_items()
        
        # sponsor by second user
        
        # test UserGroup membership prior to sponsoring
        assert not self._user2.is_member_of_group(qon.base.get_usergroup_database().get_usergroup('test'))
        
        # sponsor by self._user2
        qon.api.group_sponsor(self._group, self._user2)
        
        # test state
        assert self._group.is_accepted()
        assert self._group.get_state() == 'accepted'
        assert self._group in qon.base.get_group_database().active_groups()
        assert self._group in qon.base.get_group_database().recent_groups(datetime.timedelta(days=7))
        assert not self._group in qon.base.get_group_database().rejected_groups()
        assert not self._group in qon.base.get_group_database().limbo_groups()
        
        # test not in anon groups (default state)
        assert not self._group in qon.base.get_group_database().active_groups_anon()
        
        # test removal from mod/sponsor queue
        assert not self._group in qon.base.get_group_database().mod_queue.new_items()
        assert not self._group in qon.base.get_group_database().mod_queue.pending_items()
        
        # test status of sponsoring user
        assert self._group.is_sponsor(self._user2)
        
        # test sponsor is member
        self._is_member(self._group, self._user2)
        
    def check_210_owner_leave(self):
        """Check that a sole owner can't leave group."""
        qon.api.group_leave(self._group, self._user)
        assert self._group.is_owner(self._user)
        assert self._group.is_sponsor(self._user)
        assert not self._group.is_member(self._user)
    
    def check_290_leave(self):
        """Check leaving group by sponsoring user."""
        
        # user is currently a member
        self._is_member(self._group, self._user2)
        
        # user leaves
        qon.api.group_leave(self._group, self._user2)
        
        # user is no longer a member
        self._is_not_member(self._group, self._user2)
        
        # group is still active
        assert self._group.is_accepted()
        
    def check_300_join_no_invite(self):
        """Check joining without invitation."""
        
        try:
            qon.api.group_join(self._group, self._user3)
            assert 0
        except qon.user.NotEnoughPrivileges: pass
    
    def check_310_join(self):
        """Check invite, join."""
        
        # check is not invited
        self._is_not_invited(self._group, self._user3)
        
        # check is not member
        self._is_not_member(self._group, self._user3)
        
        # invite
        self._group.add_invitation('test3@ned.com', self._user)
        
        # check is invited
        self._is_invited(self._group, self._user3)
        
        # decline
        qon.api.group_decline_invitation(self._group, self._user3)
        self._is_not_invited(self._group, self._user3)
        
        # join not invited
        try:
            qon.api.group_join(self._group, self._user3)
            assert 0
        except qon.user.NotEnoughPrivileges: pass
        
        # invite
        self._group.add_invitation('test3@ned.com', self._user)

        # join 
        qon.api.group_join(self._group, self._user3)

        # check joined
        self._is_member(self._group, self._user3)
        
    def check_320_invite(self):
        """Check member can invite."""
        self._is_member(self._group, self._user3)
        
        # default is members cannot invite
        try:
            self._group.add_invitation('test4@ned.com', self._user3)
            assert 0
        except qon.user.NotEnoughPrivileges: pass
        assert not self._group.is_invited('test4@ned.com')
        
        # allow members to invite
        qon.api.group_set_invite_policy(self._user, self._group, 'member')
        
        # now members can invite
        self._group.add_invitation('test4@ned.com', self._user3)
        assert self._group.is_invited('test4@ned.com')
        
        # don't allow members to invite
        qon.api.group_set_invite_policy(self._user, self._group, 'owner')
        try:
            self._group.add_invitation('test5@ned.com', self._user3)
            assert 0
        except qon.user.NotEnoughPrivileges: pass
        assert not self._group.is_invited('test5@ned.com')
        
    def check_390_leave(self):
        """Check leaving group."""
        
        self._is_member(self._group, self._user3)
        qon.api.group_leave(self._group, self._user3)
        self._is_not_member(self._group, self._user3)
        
    def check_400_group_join(self):
        """Check group membership."""

        self._user2.add_karma_bank(10)  # need 10 points to create group
        
        self._group2 = qon.api.group_create(self._user2, user_id='test2',
            name='Test Group 2',
            owner=self._user2,
            description = 'This is the Test Group 2.')

        assert self._group2
        
        self._is_not_member(self._group, self._user2)
        
        # user2 is not a member, so group2 cannot join group
        assert not self._group.can_join(self._group2)
        try:
            qon.api.group_join(self._group, self._group2)
            assert 0
        except qon.user.NotEnoughPrivileges: pass
        
        # user2 joins
        self._group.add_invitation('test2@ned.com', self._user)
        qon.api.group_join(self._group, self._user2)
        self._is_member(self._group, self._user2)

        # group allows members to associate their groups
        assert self._group.members_can_associate_groups()
        assert self._group2.is_owner(self._user2)
        
        # group2 can join now
        assert self._group.can_join(self._group2)
        qon.api.group_join(self._group, self._group2)
        self._is_member(self._group, self._group2)
    
    def check_410_group_owner_leave(self):
        """Check that when a group owner leaves a group, his sole-owned groups leave too."""
        self._is_member(self._group, self._group2)
        
        assert self._group2 in self._group.sole_owned_group_members(self._user2)
        
        qon.api.group_leave(self._group, self._user2)
        self._is_not_member(self._group, self._user2)
        self._is_not_member(self._group, self._group2)
        
        # join up again
        self._group.add_invitation('test2@ned.com', self._user)
        qon.api.group_join(self._group, self._user2)
        qon.api.group_join(self._group, self._group2)
        
    def check_420_group_owner_leave2(self):
        """Check that when a group owner leaves, groups he owns with others remain."""
        self._is_member(self._group, self._group2)
        assert self._group2 in self._group.sole_owned_group_members(self._user2)
        
        # add user3 as owner
        self._group2.add_owner(self._user3)
        assert self._group2.is_owner(self._user3)
        
        # check still sole-owned since user3 is not a member of group
        assert self._group2 in self._group.sole_owned_group_members(self._user2)

        # user 3 joins group
        self._group.add_invitation('test3@ned.com', self._user)
        qon.api.group_join(self._group, self._user3)

        # check no longer sole-owned
        assert not self._group2 in self._group.sole_owned_group_members(self._user2)

        # leave group
        qon.api.group_leave(self._group, self._user2)
        self._is_not_member(self._group, self._user2)
        
        # check group2 still a member
        assert self._group.is_member(self._group2)
        self._is_member(self._group, self._group2)
        self._is_member(self._group, self._user3)
        

    def check_490_group_leave(self):
        self._is_member(self._group, self._group2)
        
        qon.api.group_leave(self._group, self._group2)
        self._is_not_member(self._group, self._group2)
        
        
    def _is_member(self, group, user):
        assert group.is_member(user)
        assert not group.is_invited(user)
        assert user in group.get_member_list()
        assert user.is_member_of_group(qon.base.get_usergroup_database().get_usergroup(group.get_user_id()))
        
    def _is_not_member(self, group, user):
        assert not group.is_member(user)
        assert not user in group.get_member_list()
        assert not user.is_member_of_group(qon.base.get_usergroup_database().get_usergroup(group.get_user_id()))
        
    def _is_not_invited(self, group, user):
        assert not group.is_invited(user)
        assert not group in qon.base.get_group_database().users_invitations(user)
    
    def _is_invited(self, group, user):
        assert group.is_invited(user)
        assert group in qon.base.get_group_database().users_invitations(user)


class Invitations (UTest):
    """Test management of invitations."""
    
    def __init__ (self, options=None, outfile=None):
        self._user, password = qon.base.get_user_database().new_user_from_email('invite-test@ned.com')

        assert self._user is not None
        assert qon.base.get_group_database().can_create_group(self._user)

        self._group = qon.api.group_create(self._user, user_id='invite-test',
            name='Test Group',
            owner=self._user,
            description = 'This is the Test Group.')

        # force group into accepted state, or else it won't accept new members
        qon.base.get_group_database().force_accept(self._group)

        UTest.__init__(self)
        
    def check_cleanup_invitations(self):
        """Test that invitations are cleaned up after a user adds an e-mail."""
        
        # invite test2 and test3
        self._group.add_invitation('invite-test2@ned.com', self._user)
        self._group.add_invitation('invite-test3@ned.com', self._user)
        
        # test2 signs in
        self._user2, password = qon.base.get_user_database().new_user_from_email('invite-test2@ned.com')
        
        # make sure he is invited
        assert self._group.is_invited(self._user2)
        assert self._group in qon.base.get_group_database().users_invitations(self._user2)

        # he should be able to join
        assert self._group.can_join(self._user2)
        
        # test2 joins
        qon.api.group_join(self._group, self._user2)
        
        # make sure he is no longer invited
        assert not self._group.is_invited(self._user2)
        assert not self._group in qon.base.get_group_database().users_invitations(self._user2)
        
        # test2 adds test3 email
        code = self._user2.add_unconfirmed_email('invite-test3@ned.com')
        assert qon.base.get_user_database().confirm_user_email(self._user2, code)
        
        # make sure test3 email is no longer invited
        assert not self._group.is_invited(self._user2)
        assert not self._group in qon.base.get_group_database().users_invitations(self._user2)
        
if __name__ == "__main__":
    # create test database
    db = open_database()
    init_database(db)
    add_real_data(db)
    
    # run tests
    NewGroup()
    Invitations()
    
    # get rid of database
    get_transaction().abort()
    db.close()
