"""
$Id: watch.py,v 1.26 2005/06/14 05:47:29 jimc Exp $

"""
from quixote import get_publisher
from datetime import datetime
from persistent import Persistent
from persistent.list import PersistentList
from dulcinea.typeutils import typecheck

from qon.database import ConflictAvoidingOOBTree, ConflictAvoidingPersistentList
from qon.base import get_user, QonPersistent, get_observe_database
from qon.util import get_oid, remove_left_duplicates, format_ago

never = datetime(2001, 1, 1)

class Watchable:
    """Mixin to add to persistent classes that can be watched.
    
    Subclasses must be Persistent.
    Subclasses must implement watchable_name() and watchable_modified_date()
    Subclasses may implement watchable_info() to provide mouse-over text
    Subclasses should call self.watchable_changed() when they change.
    Someone should call self.watchable_seen() when a user 'sees' self.
    For the UI to work, you should also update ui.blocks.util.path_to_obj
    
    Watchables automatically notify the qon.observe.ObserveDB when they have
    changed, in case anyone is dependent on them.
    """
    
    not_watchable = 0   # subclasses may set to suppress Watchable machinery
    
    def __init__(self):
        self.__last_change = datetime.utcnow()
        
        # we rely on _p_oid machinerey
        if not isinstance(self, Persistent):
            raise NotImplementedError, "only Persistent objects are watchable."
            
    def watchable(self):
        """Subclasses may add a not_watchable attribute to suppress Watchable machinery."""
        if hasattr(self, 'not_watchable') and self.not_watchable:
            return False
        return True
    
    def watchable_changed(self, now=None):
        """Call this when object changes in a noticeable way.
        
        If now is not provided, calls datetime.utcnow.
        """
        if not self.watchable():
            return
            
        # we rely on _p_oid machinerey
        if not isinstance(self, Persistent):
            raise NotImplementedError, "only Persistent objects are watchable."

        # notify observe database that this watchable has changed
        get_observe_database().notify_changed(self)        

        self.__last_change = datetime.utcnow()
        self._p_changed = 1
        
    def changed_since(self, dt):
        """Return True if object changed since datetime dt."""
        if not self.watchable():
            return False
            
        if self.__last_change:
            if self.__last_change > dt:
                return True
        return False
        
    def watchable_seen(self):
        """Call this when user sees object"""
        if not self.watchable():
            return
        if get_publisher() is None:
            return
        user = get_user()
        if user is None:
            return
        if hasattr(user, 'get_watch_list'):
            user.get_watch_list().watchable_seen(self)
    
    def watchable_last_change(self):
        """Return datetime this item was last changed."""
        if not self.watchable():
            return never
            
        return self.__last_change or never
    
    def watchable_name(self):
        """Return a name suitable for display."""
        raise NotImplementedError, "subclasses must implement"

    def watchable_info(self):
        """Return summary info text on this item, suitable for mouse-over text for example.
        Default is to return last-modified date."""
        return 'Last updated: %s' % format_ago(self.watchable_modified_date())

    def watchable_modified_date(self):
        """Return a datetime object representing the last modified date/time."""
        return self.watchable_last_change()

class WatchList(QonPersistent):
    """Keep track of a collection of Watchable items by their oids.
    
    Stores last-seen time for each object watched.
    """
    
    persistenceVersion = 3
    
    _max_footprints = 10
    
    def __init__(self):
        self.__items = ConflictAvoidingOOBTree()
        self.__footprints = ConflictAvoidingPersistentList()
        
    def upgradeToVersion3(self):
        """Make footprints persistent. No need to del _v_footprints since it's volatile anyway."""
        self.__footprints = ConflictAvoidingPersistentList()
        self.version_upgrade_done()
        
    def upgradeToVersion2(self):
        newbt = ConflictAvoidingOOBTree(self.__items)
        del self.__items
        self.__items = newbt
        self.version_upgrade_done()
        
    def upgradeToVersion1(self):
        if hasattr(self, '_WatchList__footprints'):
            del self.__footprints
        
    def watch_item(self, item):
        """Add item to watch list. Records current time as last-seen."""
        typecheck(item, Watchable)
        typecheck(item, Persistent)
        if not item.watchable():
            return
            
        if not self.__items.has_key(item._p_oid):
            self.__items[item._p_oid] = datetime.utcnow()
    
    def stop_watching_item(self, item):
        """Remove item from watch list."""
        typecheck(item, Watchable)
        typecheck(item, Persistent)
        if not item.watchable():
            return
        if self.__items.has_key(item._p_oid):
            del self.__items[item._p_oid]
    
    def watchable_seen(self, obj):
        """Called when a watchable item is seen, even if
        it's not in my watchable list."""
        typecheck(obj, Watchable)
        typecheck(obj, Persistent)
        if not obj.watchable():
            return
        if self.__items.has_key(obj._p_oid):
            self.__items[obj._p_oid] = datetime.utcnow()
        
        self.add_footprint(obj)
    
    def changed_items(self, since):
        """Return list of items changed since datetime since."""
        watched = self.watched_items()
        changed = [item for item in watched if item.changed_since(since)]
        return changed
        
    def changed_unseen_items(self):
        """Return list of items changed and unseen since datetime since."""
        changed = self.watched_items()
        return [item for item in changed \
            if self.last_seen(item) < item.watchable_last_change()]
    
    def watched_items(self):
        """Return list of all items being watched."""
        return self._get_items(self.__items.keys())
        
    def watched_items_oids(self):
        """Return list of all item OIDs being watched."""
        return self.__items.keys()
        
    def _get_items(self, oid_list):
        """Return a list of valid watchable items from oid_list"""
        items = []
        for k in oid_list:
            try:
                obj = get_oid(k)
                obj_name = obj.watchable_name()
            except:
                self._lost_oid(k)
            else:
                items.append(obj)
        return items
        
    def _lost_oid(self, oid):
        """We can't find this oid, remove from list."""
        if self.__items.has_key(oid):
            del self.__items[oid]
        while oid in self.__footprints:
            self.__footprints.remove(oid)
        
    def footprints(self):
        """Return list of footprinted items, most recent first."""
        items = self._get_items(self.__footprints)
        items.reverse()
        return items
        
    def add_footprint(self, obj):
        """Add obj to fooprint list."""
        self.__footprints.append(obj._p_oid)
        if len(self.__footprints) > self._max_footprints:
            self.__footprints = ConflictAvoidingPersistentList(self.__footprints[-self._max_footprints:])
        remove_left_duplicates(self.__footprints)
        
    def last_seen(self, item):
        """Return datetime this item was last seen."""
        typecheck(item, Watchable)
        typecheck(item, Persistent)
        return self.__items.get(item._p_oid, never)
        
    def is_watching(self, item):
        """Returns true if item is in watch list."""
        typecheck(item, Watchable)
        typecheck(item, Persistent)
        return item._p_oid in self.__items
