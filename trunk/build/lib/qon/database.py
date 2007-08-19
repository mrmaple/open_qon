"""
$Id: database.py,v 1.17 2007/02/18 15:04:39 jimc Exp $
"""
import os
from BTrees import OOBTree, IOBTree
from ZODB.DB import DB
from persistent.list import PersistentList
from dulcinea.database import ObjectDatabase
from dulcinea.site_util import get_config

MB = 1024**2

class QonObjectDatabase(ObjectDatabase):
    
    def __init__(self, site):
        ObjectDatabase.__init__(self)
        
        if site is None:
            site = os.environ.get('SITE', None)
        self.site = site

    def _open_client (self, location):
        """Open 'location' (a (hostname, port_number) tuple) as a ZEO
        ClientStorage, and then open a ZODB database around that.  Return
        a (database, connection) tuple.
        
        We override dulcinea.database.ObjectDatabase._open_client to support
        username/password.
        """
        host, port = location
        if host == "":
            # If the specified hostname is the empty string, then
            # 'localhost' is used.
            location = ('localhost', port)
            
        site_config = get_config()
        username = site_config.get(self.site, 'zeo-username', fallback='')
        password = site_config.get(self.site, 'zeo-password', fallback='')

        # we use QonClientStorage instead of ClientStorage to:
        #  1. workaround ClientStorage's cache_size bug
        #  2. enable cache instrumentation (if qon.local.CACHE_INSTRUMENTATION is True)
        from qon.cache_logging import QonClientStorage        
        self.storage = QonClientStorage(location,
            var='/var/tmp',
            wait=0,
            cache_size=150*MB,
            username=username,
            password=password)
        
        db = DB(self.storage)
        
        return (db, db.open())

    # alex added to increase object cache size (dulcinea sets it to 10000)
    def open(self, dbspec):
        ObjectDatabase.open(self, dbspec)

        # increase the maximum number of objects cached
        #site_config = get_config()
        #size = site_config.get(self.site, 'object-cache-size', fallback='50000')
        size=200000
        self.set_cache_size(size)                                 

class ConflictAvoidingOOBTree(OOBTree.OOBTree):
    """A special type of OOBTree that silently ignores conflicts, blindly
    accepting new data."""
    
    def _p_resolveConflict(self, oldState, savedState, newState):
        return newState

class ConflictAvoidingIOBTree(IOBTree.IOBTree):
    """A special type of IOBTree that silently ignores conflicts, blindly
    accepting new data."""
    
    def _p_resolveConflict(self, oldState, savedState, newState):
        return newState

class ConflictAvoidingPersistentList(PersistentList):
    """A special type of PersistentList that silently ignores conflicts, blindly
    accepting new data."""
    
    def _p_resolveConflict(self, oldState, savedState, newState):
        return newState
