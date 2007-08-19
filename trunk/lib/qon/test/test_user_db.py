#!/usr/bin/env python

"""$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/dulcinea/lib/test/test_user.py $
$Id: test_user_db.py,v 1.6 2004/05/06 20:01:03 jimc Exp $

Test for qon.user_db.
"""

from sancho.unittest import TestScenario, parse_args, run_scenarios
from qon.user import User, UserGroup
from qon.user_db import UserDB, UserGroupDB

tested_modules = [ "qon.user_db" ]

class UserDBTest (TestScenario):


    def check_init (self):
        "Check constructor"
        self.test_stmt("UserDB()")
        self.test_stmt("UserGroupDB()")
        
    def check_user(self):
        u = User()
        u.set_user_id('foo')
        db = UserDB()
        self.test_stmt("db.add_user(u)")
        self.test_val("db.get_user('foo')", u)
        self.test_exc("db.add_user(u)", KeyError)
        
        self.test_stmt("db.remove_user('foo')")
        self.test_stmt("db.add_user(u)")
        self.test_val("db.get_user('foo')", u)

    def check_group(self):
        g = UserGroup()
        g.set_group_id('foo')
        db = UserGroupDB()
        self.test_stmt("db.add_usergroup(g)")
        self.test_val("db.get_usergroup('foo')", g)
        self.test_exc("db.add_usergroup(g)", KeyError)
        
        self.test_stmt("db.remove_group('foo')")
        self.test_stmt("db.add_usergroup(g)")
        self.test_val("db.get_usergroup('foo')", g)
      

if __name__ == "__main__":
    (scenarios, options) = parse_args()
    run_scenarios(scenarios, options)
