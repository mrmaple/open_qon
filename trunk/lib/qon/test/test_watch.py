#!/usr/bin/env python
"""
$Id: test_watch.py,v 1.1 2004/04/19 03:04:06 jimc Exp $
"""
from sancho.unittest import TestScenario, parse_args, run_scenarios

tested_modules = [ "qon.watch" ]

from datetime import datetime
from persistent import Persistent
from watch import Watchable

class PersistentWatchable(Persistent, Watchable):
    def __init__(self):
        Watchable.__init__(self)
        
class NonPersistentWatchable(Watchable):
    def __init__(self):
        Watchable.__init__(self)

class WatchableTest (TestScenario):

    def check_init(self):
        self.test_stmt("PersistentWatchable()")
        self.test_exc("NonPersistentWatchable()", NotImplementedError)

    def check_watchable_changed(self):
        w = PersistentWatchable()
        
        # first change
        now = datetime.utcnow()
        last_change = w._Watchable__last_change
        self.test_stmt("w.watchable_changed()")
        self.test_true("w._Watchable__last_change > now")
        
        # and again
        last_change = w._Watchable__last_change
        self.test_stmt("w.watchable_changed()")
        self.test_true("w._Watchable__last_change > last_change")
    
    def check_changed_since(self):
        w = PersistentWatchable()
        
        now = datetime.utcnow()
        
        # not changed yet
        self.test_false("w.changed_since(now)")
        
        # changed
        self.test_stmt("w.watchable_changed()")
        self.test_true("w.changed_since(now)")
        
        # not changed again
        self.test_false("w.changed_since(datetime.utcnow())")
        
    def check_watchable_seen(self):
        from qon.user import User
        u = User()
        w = PersistentWatchable()
        
        # doesn't really test anything since watchable_seen uses get_user()
        self.test_stmt("w.watchable_seen()")
        
class WatchListTest(TestScenario):
    pass
    # FIXME needs db to test against

if __name__ == "__main__":
    (scenarios, options) = parse_args()
    run_scenarios(scenarios, options)
