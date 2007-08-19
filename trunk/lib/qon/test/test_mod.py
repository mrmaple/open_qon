#!/usr/bin/env python

"""$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/dulcinea/lib/test/test_user.py $
$Id: test_mod.py,v 1.3 2004/04/10 00:57:05 Exp $

Test for qon.mod.
"""

from sancho.unittest import TestScenario, parse_args, run_scenarios
from datetime import datetime, timedelta
from qon.user import User
from qon.mod import InvalidState, Voteable
from qon.group import Group
from qon.group_db import GroupDB

tested_modules = [ "qon.mod", "qon.group", "qon.group_db" ]

class VoteableTest (TestScenario):

    def check_init(self):
        self.test_stmt("v = Voteable()")
        self.test_stmt("v = Voteable(min_sponsors=5)")
        self.test_val("v.min_sponsors", 5)

    def check_voting(self):
        self.test_stmt("v = Voteable()")
        v = Voteable()
        u = User()
        self.test_exc("v.add_sponsor('foo')", TypeError)
        self.test_stmt("v.add_sponsor(u)")
        self.test_stmt("v.set_pending()")
        
        end_voting = datetime.utcnow() + timedelta(days=7)
        
        self.test_stmt("v.open_voting(end_voting)")
        self.test_exc("v.vote('foo', 'for')", TypeError)
        self.test_exc("v.vote(u, 'for')", KeyError)            # already voted as sponsor
        
        u2 = User()
        self.test_exc("v.vote('bar', 'against')", TypeError)
        self.test_stmt("v.vote(u2, 'against')")
        self.test_exc("v.vote(u2, 'against')", KeyError)       # already voted
        
        self.test_stmt("v.close_voting()")
        self.test_val("v.get_state()", 'limbo')
        
        self.test_stmt("v.open_voting(end_voting)")
        u3 = User()
        self.test_stmt("v.vote(u3, 'for')")
        self.test_stmt("v.close_voting()")
        self.test_val("v.get_state()", 'accepted')
        
        v = Voteable()
        v.add_sponsor(u)
        self.test_stmt("v.open_voting(end_voting)")
        self.test_exc("v.vote(u, 'against')", KeyError)     # already voted as sponsor
        self.test_stmt("v.vote(u2, 'against')")
        self.test_stmt("v.vote(u3, 'against')")
        u4 = User()
        self.test_stmt("v.vote(u4, 'abstain')")
        self.test_stmt("v.close_voting()")
        self.test_val("v.get_state()", 'rejected')
        
        v = Voteable()
        self.test_exc("v.open_voting(end_voting)", ValueError)        # not enough sponsors
        self.test_exc("v.close_voting()", InvalidState)
        

class GroupTest(TestScenario):

    def check_group(self):
        self.test_stmt("g = Group()")
        self.test_stmt("g.user_id = 'group'")
        self.test_stmt("g.name = 'The Group'")
        self.test_stmt("u = User()")
        self.test_stmt("g.add_owner(u)")
        self.test_stmt("g.add_sponsor(u)")
        self.test_stmt("gdb = GroupDB()")
        self.test_stmt("gdb.add_group(g)")
        
    def check_VoteableQueue(self):
        Group._min_sponsors = 1
        g = Group()
        g.user_id = 'group'
        g.name = 'The Group'
        u = User()
        g.add_owner(u)
        g.add_sponsor(u)
        gdb = GroupDB()
        gdb.add_group(g)
        
        self.test_val("gdb.mod_queue.get_items_by_state('voting')", [g])
        
        self.test_stmt("g.close_voting()")
        self.test_stmt("gdb.mod_queue.voting_closed(g)")
        self.test_val("g.get_state()", 'accepted')
        self.test_true("g in gdb.mod_queue.accepted")
        self.test_false("g in gdb.mod_queue.rejected")
        
        self.test_val("gdb.mod_queue.get_items_by_state('voting')", [])
        
    

if __name__ == "__main__":
    (scenarios, options) = parse_args()
    run_scenarios(scenarios, options)
