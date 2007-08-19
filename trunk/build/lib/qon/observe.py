"""
$Id: observe.py,v 1.7 2005/11/22 02:06:32 jimc Exp $
:Author:    Jim Carroll

"""
from persistent.list import PersistentList
from dulcinea.database import unpack_oid
from qon.base import QonPersistent, get_observe_database
from qon.user_db import GenericDB
from qon.util import unique_items

class Dependencies(QonPersistent):
    """Keeps track of dependencies for a client object."""
    
    def __init__(self):
        self.__targets = PersistentList()
        
    def add_dependency(self, target):
        """Register self as being dependent on target."""
        
        # add to my targets list
        self.__targets.append(target)
        
        # tell observe db i'm dependent on target
        get_observe_database().observe(target, self)
    
    def remove_dependency(self, target):
        """I am no longer dependent on target."""
        
        # remove from my targets list
        while target in self.__targets:
            self.__targets.remove(target)
            
        # stop observing
        get_observe_database().stop_observing(target, self)

    def remove_all_dependencies(self):
        """Remove and unregister all dependencies."""
        db = get_observe_database()
        for target in self.__targets:
            db.stop_observing(target, self)
        
        # flush targets list
        del self.__targets[:]
    
    def set_dependencies(self, targets):
        """Register self as being dependent only on list of targets."""
        
        targets = unique_items(targets)
        
        self.remove_all_dependencies()
        
        for target in targets:
            self.add_dependency(target)

    def get_dependencies(self):
        """Return a list of targets I am dependent on."""
        return self.__targets[:]
            
    def up_to_date(self):
        """Return True if none of my targets have changed since I added them
        as a dependency."""
        
        db = get_observe_database()
        for target in self.__targets:
            if not db.up_to_date(target, self):
                return False
        return True
    
    def out_of_date_wrt(self):
        """Return list of objects I am out of date with respect to."""
        
        ood = []
        db = get_observe_database()
        for target in self.__targets:
            if not db.up_to_date(target, self):
                ood.append(target)
        return ood

    def any_caches_disabled(self):
        """Returns True if any of my targets that I depend have their
        caches diabled.  Does not recurse."""
        for target in self.__targets:        
            try:
                if target.cache_disabled():
                    return True
            except AttributeError:
                pass
        return False
    
class ObserveDB(GenericDB):
    """Provides simple tree of keys and their observers.
    
    Persistent objects dependent on other persistent objects call
    observe() when they want to register their dependence. Objects
    which know they are being observed call notify_changed() when
    they are updated.
    
    Doesn't do anything clever with timestamps. Calling observe()
    means the caller believes he is up to date, and wants to be able
    to call up_to_date() to confirm that he is still up to date. When
    notify_changed() is called, it simply invalidates all observers, and
    subsequent calls to up_to_date() will return False.
    """
    
    def __init__(self):
        GenericDB.__init__(self)
    
    def observe(self, target, observer):
        """Register observer as watching/dependent on target."""
        
        assert hasattr(target, '_p_oid'), 'target must be Persistent.'
        assert hasattr(observer, '_p_oid'), 'observer must be Persistent.'
        
        # newly-created objects that are uncommitted may not have OIDs yet
        if not target._p_oid or not observer._p_oid:
            return
        
        key = unpack_oid(target._p_oid)
        observer_oid = unpack_oid(observer._p_oid)
        
        o_list = self.root.get(key, None)
        if o_list is not None:
            if not observer_oid in o_list:
                o_list.append(observer_oid)
        else:
            self[key] = PersistentList([observer_oid])
    
    def stop_observing(self, target, observer):
        """Unregister observer as watching/dependent on target."""
        
        assert hasattr(target, '_p_oid'), 'target must be Persistent.'
        assert hasattr(observer, '_p_oid'), 'observer must be Persistent.'
        
        # newly-created objects that are uncommitted may not have OIDs yet
        if not target._p_oid or not observer._p_oid:
            return

        key = unpack_oid(target._p_oid)
        observer_oid = unpack_oid(observer._p_oid)
        
        o_list = self.root.get(key, None)
        if o_list:
            while observer_oid in o_list:
                o_list.remove(observer_oid)
    
    def notify_changed(self, target):
        """Called by target to notify that it has changed."""
        assert hasattr(target, '_p_oid'), 'target must be Persistent.'

        # newly-created objects that are uncommitted may not have OIDs yet
        if not target._p_oid:
            return

        key = unpack_oid(target._p_oid)
        
        if self.root.has_key(key):
            del self[key]

    def up_to_date(self, target, observer):
        """Return true if observer is up to date with respect to key.
        
        Returns true if observe(key, observer) has been called more
        recently than notify_changed(key).
        """
        assert hasattr(target, '_p_oid'), 'target must be Persistent.'
        assert hasattr(observer, '_p_oid'), 'observer must be Persistent.'

        key = unpack_oid(target._p_oid)
        observer_oid = unpack_oid(observer._p_oid)
        
        o_list = self.root.get(key, None)
        if o_list:
            return observer_oid in o_list
        return False

