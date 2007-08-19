"""$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/toboso/lib/base.py $
$Id: base.py,v 1.28 2007/05/01 11:41:29 jimc Exp $
"""
from quixote import get_user, get_publisher
from dulcinea.site_util import get_dbspec
#from dulcinea.base import DulcineaBase, DulcineaPersistent
from persistent import Persistent
from qon.database import QonObjectDatabase

_db = QonObjectDatabase(site='qon')

def get_database():
    return _db

def open_database(dbspec=None):
    if dbspec is None:
        #dbspec = 'file:/www/var/qon.fs'    # local, non-ZEO
        dbspec = get_dbspec("qon")          # ZEO
    _db.open(dbspec=dbspec)
    return _db

def close_database():
    _db.close()

def get_root():
    return _db.root
    
def get_misc_database():
    return _db.misc_db

def get_observe_database():
    return _db.misc_db.get_observe_database()

def get_user_database():
    return _db.user_db

def get_group_database():
    return _db.group_db

def get_usergroup_database():
    return _db.usergroup_db
    
def get_list_database():
    return _db.list_db

def get_session_manager():
    return _db.session_manager

def get_connection():
    return _db.connection
    
def get_log():
    return _db.log

def get_tagged_item_database ():
    return _db.tagged_item_db

def get_tags_database ():
    return _db.tags_db

class QonBase(object):
    """Base class for all Qon non-persistent objects.
    
    Subclasses may still be stored in persistent attributes.
    """
    pass


_versioneds_upgraded = {}

def commit_upgraded_versioneds():
    """Call this at the end of a successful publish request to commit (write to disk)
    any object upgrades that have occurred.
    """
    global _versioneds_upgraded
    changed = 0
    for obj in _versioneds_upgraded.values():
        obj._p_changed = 1
        changed = 1
    _versioneds_upgraded = {}
    if changed:
        transaction_commit(None, 'commit_upgraded_versioneds')

from twisted.persisted import styles

class QonPersistent(Persistent, styles.Versioned):
    """Base class for all Qon persistent objects.
    
    We use Twisted's Versioned mixin for schema-change convenience. However,
    since ZODB loads objects on an as-needed basis, there is no good place to
    call twisted.persisted.styles.doUpgrade; so we upgrade each instance in
    __setstate__ as it is loaded.
    """
    
    def __setstate__(self, state):
        Persistent.__setstate__(self, state)
        self.versionUpgrade()
    
    def __getstate__(self):
        state = Persistent.__getstate__(self)
        return styles.Versioned.__getstate__(self, state)
    
    def version_upgrade_done(self):
        """Subclasses must call this from their upgradeToVersionX methods
        to inform us so our Publisher object can force a write.
        
        This additional machinery is necessary because of how the upgrade
        machinery interacts with ZODB Persistent objects. They both hook into
        __setstate__. When ZODB unpickles an object behind the scenes to make
        it available for an attribute access, it sets _p_changed to None after
        the object is unpickled -- meaning, after __setstate__ has done its work.
        
        Additionally, if a new Persistent object is created and assigned to an
        attribute during __setstate__, it doesn't appear to be watched for changed.
        I don't understand why that is, but this behavior is easy to observe.
        
        We work around all this by keeping track of objects we have upgraded in any
        given session. If the session is run by a QonPublisher (web ui), it will
        call commit_upgraded_versioneds after a successful request, which will force
        upgraded objects (and any new Persistent objects they refer to) to be written
        to disk.
        """
        global _versioneds_upgraded
        _versioneds_upgraded[self._p_oid] = self
        

def transaction_note(user=None, note=''):
    """Set user and description information on the ZODB transaction."""
    import transaction as t
    if not user:
        try:
            user = get_user()
        except:
            user = None
    if user:
        t.get().setUser(user.get_user_id())
    if note:
        t.get().note(note)
    
def transaction_commit(user=None, note=''):
    """Commit the current transaction, adding user and note."""
    transaction_note(user, note)
    import transaction
    
    # new semantics as of 3.3.0c1: if an exception occurs while committing, the current
    # transaction must be aborted explicitly. 
    try:
        transaction.commit()
    except:
        transaction.abort()
        raise


def transaction_abort():
    """Abort the current transaction."""
    import transaction
    transaction.abort()

class PersistentCache(QonPersistent):
    """Generic Persistent caching mechanism."""
    
    persistenceVersion = 2
    
    def __init__(self, get_function=None):
        self.data = None
        self.get_function = get_function
        
        from qon.observe import Dependencies
        self.__depends = Dependencies()
        self.__disable_cache = False           
    
    def upgradeToVersion1(self):
        from qon.observe import Dependencies
        self.__depends = Dependencies()
        self.version_upgrade_done()

    # alex added __disable_cache ability so that directives like on-user-link can
    #  call disable_cache to signify that the cache is not to be used
    def upgradeToVersion2(self):
        self.__disable_cache = False    
        self.version_upgrade_done()
        
    def set(self, data):
        self.data = data
    
    def get(self):
        from quixote.html import htmltext
        
        # check dependencies and cache setting
        if (not self.__depends.up_to_date()) or self.__disable_cache or self.__depends.any_caches_disabled():
            self.data = None
        
        if self.data:
            return self.data
        
        if self.get_function:

            # assume that we'll be able to use the cache
            self.__disable_cache = False

            self.__depends.remove_all_dependencies()

            self.data = self.get_function()
            
            # can't pickle htmltext objects
            if type(self.data) is htmltext:
                self.data = str(self.data)
        
        return self.data
    
    def flush(self):
        """Flush cache. E.g. when something it depends on has changed."""
        self.data = None
        self.__depends.remove_all_dependencies()

    def add_dependency(self, target):
        self.__depends.add_dependency(target)

    def disable_cache(self):
        self.__disable_cache = True

    def cache_disabled(self):
        return self.__disable_cache
