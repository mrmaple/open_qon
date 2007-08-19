"""
$Id: defer.py,v 1.3 2004/12/31 03:42:28 jimc Exp $
:Author:    Jim Carroll

"""
from datetime import datetime
from qon.database import ConflictAvoidingOOBTree

from base import QonPersistent

class DeferralList(QonPersistent):
    """Provides simple timed deferral mechanism.
    
    Maintains a list of keyed times. Client calls defer()
    to add a key and a delay. Subsequent calls to defer()
    with the same key will return True if delay has elapsed,
    or false if not.
    """
    
    persistenceVersion = 1
    
    def __init__(self):
        self.defers = ConflictAvoidingOOBTree()
        
    def upgradeToVersion1(self):
        # upgrade from PersistentMapping

        bt = ConflictAvoidingOOBTree()

        for k,v in self.defers.iteritems():
            bt[k] = v

        del self.defers
        self.defers = bt
        self.version_upgrade_done()
        
    def defer(self, key, delay):
        """Schedule a deferred event labeled by key.
        
        If key already exists, returns True if enough
        time has elapsed since key was originally added.
        Otherwise, add key and return False.
        """
        now = datetime.utcnow()
        
        if self.defers.has_key(key):
            if self.defers[key] <= now:
                del self.defers[key]
                return True
            else:
                return False
        else:
            self.defers[key] = now + delay
            return False
    
    def cancel(self, key):
        """Unschedule a deferred task."""
        if self.defers.has_key(key):
            del self.defers[key]
