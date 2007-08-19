#!/usr/bin/env python

"""$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/dulcinea/lib/test/test_user.py $
$Id: test_user.py,v 1.8 2004/04/10 00:57:05 jimc Exp $

Test for qon.user.
"""

from sancho.unittest import TestScenario, parse_args, run_scenarios
from qon.user import HasPassword, HasUserID, HasGroupMembership, \
    HasOwnership, HasEmail, User, UserGroup

tested_modules = [ "qon.user" ]

class UserTest (TestScenario):

    def check_HasPassword(self):
        self.test_stmt("HasPassword()")
        hp = HasPassword()
        self.test_stmt("hp.set_password('secret')")
        self.test_true("hp.valid_password('secret')")
        self.test_false("hp.valid_password('bogus')")
        
        self.test_stmt("hp.generate_password()")
        self.test_false("hp.valid_password('guess')")
        self.test_stmt("p = hp.generate_password() ; assert hp.valid_password(p)")

    def check_HasUserID(self):
        self.test_stmt("HasUserID()")
        huid = HasUserID()
        self.test_val("huid.user_id", None)
        self.test_exc("huid.set_user_id('$#&@^')", ValueError)
        self.test_stmt("huid.set_user_id('foo')")
        self.test_val("huid.user_id", "foo")
        
        self.test_stmt("huid.generate_user_id()")
        
    def check_UserGroup(self):
        self.test_stmt("UserGroup()")
        g = UserGroup()
        self.test_stmt("g.set_group_id('staff')")
        self.test_val("g.get_group_id()", 'staff')
        
        self.test_stmt("admin = UserGroup('admin')")
        self.test_val("admin.get_group_id()", 'admin')

    def check_HasGroupMembership(self):
        self.test_stmt("HasGroupMembership()")
        g = HasGroupMembership()
        staff = UserGroup()
        staff.set_group_id('staff')
        admin = UserGroup()
        admin.set_group_id('admin')
        other = UserGroup()
        other.set_group_id('other')
        
        self.test_exc("g.is_member_of_group('staff')", TypeError)
        self.test_exc("g.add_to_group('staff')", TypeError)
        self.test_exc("g.remove_from_group('staff')", TypeError)
        
        
        self.test_stmt("g.add_to_group(staff)")
        self.test_true("g.is_member_of_group(staff)")
        self.test_true("staff in g.group_list()")
        
        self.test_stmt("g.add_to_group(admin)")
        self.test_true("g.is_member_of_group(admin)")
        self.test_true("admin in g.group_list()")
        
        self.test_false("g.is_member_of_group(other)")
        self.test_stmt("g.remove_from_group(staff)")
        self.test_false("g.is_member_of_group(staff)")
        self.test_stmt("g.remove_from_all_groups()")
        self.test_false("g.is_member_of_group(admin)")
        self.test_exc("g.remove_from_group([other, staff])", TypeError)  # can't remove list
        
        g.remove_from_all_groups()
        self.test_stmt("g.add_to_group([staff, admin])")
        self.test_true("g.is_member_of_group(staff)")
        self.test_true("g.is_member_of_group(admin)")
        self.test_false("g.is_member_of_group(other)")
        
    def check_HasEmail(self):
        self.test_stmt("HasEmail()")
        g = HasEmail()
        self.test_stmt("g._consistency_check()")
        self.test_false("g.has_email('staff')")           # not member of group
        self.test_stmt("g.add_email('staff')")                 # add to staff
        self.test_true("g.has_email('staff')")            # is member of staff
        self.test_true("'staff' in g.email_list()")              # staff in group list
        self.test_stmt("g.add_email('admin')")                 # add to admin
        self.test_true("g.has_email('admin')")            # is member of admin
        self.test_true("'admin' in g.email_list()")              # admin in group list
        self.test_false("g.has_email('other')")           # not member of other
        self.test_stmt("g.remove_email('staff')")            # remove from staff
        self.test_false("g.has_email('staff')")           # not member of staff
        self.test_stmt("g.remove_all_emails()")               # remove all groups
        self.test_false("g.has_email('admin')")           # not member of any group
        self.test_exc("g.remove_email(['foo'])", TypeError)  # can't remove list
        
        g.remove_all_emails()
        self.test_stmt("g.add_email(['one', 'two'])")          # add group list
        self.test_true("g.has_email('one')")
        self.test_true("g.has_email('two')")
        self.test_false("g.has_email('staff')")
        
        
    def check_HasOwnership(self):
        self.test_stmt("HasOwnership()")
        ho = HasOwnership()
        
        foo = User()
        foo.set_user_id('foo')
        
        staff = UserGroup()
        staff.set_group_id('staff')

        self.test_stmt("ho.add_owner(foo)")
        self.test_stmt("ho.add_owning_group(staff)")
        self.test_stmt("ho.set_owner_perms(['read', 'write'])")
        self.test_stmt("ho.set_group_perms('read')")
        self.test_exc("ho.test_perm('fooble', User())", KeyError)
        
        u = User('foo')
        nobody = User('nobody')
        self.test_false("ho.can_read(u)")
        self.test_true("ho.can_read(foo)")
        self.test_false("ho.can_read(nobody)")
        self.test_false("ho.can_write(u)")
        self.test_true("ho.can_write(foo)")
        self.test_false("ho.can_write(nobody)")
        
        nobody.add_to_group(staff)
        self.test_true("ho.can_read(nobody)")
        self.test_false("ho.can_write(nobody)")
        
        self.test_stmt("ho.remove_owner(foo)")
        self.test_false("ho.can_read(foo)")
        self.test_false("ho.can_write(foo)")
        
        # check 'other' perms
        nobody = User()
        ho = HasOwnership()
        self.test_false("ho.can_read(nobody)")
        self.test_stmt("ho.set_other_perms('read')")
        self.test_true("ho.can_read(nobody)")
        self.test_false("ho.can_write(nobody)")
        self.test_stmt("ho.set_other_perms('write')")
        self.test_true("ho.can_write(nobody)")
        self.test_false("ho.can_manage(nobody)")
        self.test_stmt("ho.set_other_perms('manage')")
        self.test_true("ho.can_manage(nobody)")
        
        # FIXME not finished        
        
    def check_init (self):
        "Check constructor"
        self.test_stmt("User()")
        self.test_exc("u = User() ; u.set_user_id('f#$^')", ValueError)
        
        self.test_stmt("User('foo')")
        u = User('fooble')
        self.test_val("u.get_user_id()", 'fooble')
        
        u = User()
        self.test_val("u.user_id", None)
        self.test_stmt("u.set_user_id('foo')")
        self.test_val("u.user_id", "foo")
      

if __name__ == "__main__":
    (scenarios, options) = parse_args()
    run_scenarios(scenarios, options)
