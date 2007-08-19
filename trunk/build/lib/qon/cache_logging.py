"""
$Id: cache_logging.py,v 1.3 2006/01/16 05:22:22 alex Exp $
"""
import os
from ZEO.ClientStorage import ClientStorage
from ZEO.cache import ClientCache, FileCache
import qon.local
from ZODB.DB import DB
from ZODB.Connection import Connection

MB = 1024**2


class QonClientStorage(ClientStorage):
    """
    subclass of ClientStorage that fixes the cache_size bug, and optionally
    uses QonClientCache for cache instrumentation (instead of plain ClientCache).
    qon.local.CACHE_INSTRUMENTATION determines whether or not an instrumented cache is used.
    """

    def __init__(self, addr, storage='1', cache_size=20 * MB,
                 name='', client=None, debug=0, var=None,
                 min_disconnect_poll=5, max_disconnect_poll=300,
                 wait_for_server_on_startup=None, # deprecated alias for wait
                 wait=None, wait_timeout=None,
                 read_only=0, read_only_fallback=0,
                 username='', password='', realm=None):


        # swap out the ClientCache with QonClientCache if desired.
        self.ClientCacheClass = ClientCache
        if qon.local.CACHE_INSTRUMENTATION:
            self.ClientCacheClass = QonClientCache
            
        ClientStorage.__init__(self, addr, storage, cache_size, \
                               name, client, debug, var, \
                               min_disconnect_poll, max_disconnect_poll, \
                               wait_for_server_on_startup, \
                               wait, wait_timeout, \
                               read_only, read_only_fallback, \
                               username, password, realm)

        # fix the cache_size bug that we manually patched previously.
        # once ZEO's code is fixed, we can remove everything after
        #  this line of code in this routine.
        if self._cache:
            self._cache.close()
            del self._cache

        # Decide whether to use non-temporary files
        if client is not None:
            dir = var or os.getcwd()
            cache_path = os.path.join(dir, "%s-%s.zec" % (client, storage))
        else:
            cache_path = None

        # create the cache            
        self._cache = self.ClientCacheClass(cache_path, size=cache_size) # this here is that actual cache_size fix
        self._cache.open()


class QonClientCache(ClientCache):
    """
    subclass of ClientCache that uses QonFileCache instead of FileCache
    """

    def __init__(self, path=None, size=None, trace=False):
        ClientCache.__init__(self, path, size, trace)

        self.fc.close()
        del self.fc
        self.fc = QonFileCache(size or 10**6, self.path, self)

class QonFileCache(FileCache):    
    """
    subclass of FileCache that keeps track of all objects that have been
    added to and accessed from ZEO's cache
    """

    def __init__(self, maxsize, fpath, parent, reuse=True):
        FileCache.__init__(self, maxsize, fpath, parent, reuse)
        
        self.added_oids = []
        self.accessed_oids = []

    def add(self, object):
        FileCache.add(self, object)

        oid, tid = object.key
        self.added_oids.append((object.size, oid))

    def access(self, key):
        obj = FileCache.access(self, key)

        if obj:
            oid, tid = key
            self.accessed_oids.append((obj.size, oid))

        return obj            


    def get_formatted_cache_stats(self):
        """
        returns a string the shows # of objects retrieved from cache and # of objects loaded from ZODB
        since the last time this function was called.
        set VERBOSE_CACHE_LOGGING=True if you want to see the actual objects (tons of output!)
        """
        
        from qon.util import get_oid

        # create the verbose version while tallying up data for the summary version        
        verbose_accessed = ''
        verbose_added = ''
        accessed_tally = {}
        added_tally = {}
        self.accessed_oids.sort(lambda x, y: x[0]-y[0])
        self.added_oids.sort(lambda x, y: x[0]-y[0])            
        for size, oid in self.accessed_oids:
            if qon.local.VERBOSE_CACHE_LOGGING:
                verbose_accessed += "\n --(%d bytes) %s" % (size, str(get_oid(oid)))
            self._tally(accessed_tally, type(get_oid(oid)), size)
        for size, oid in self.added_oids:
            if qon.local.VERBOSE_CACHE_LOGGING:
                verbose_added += "\n --(%d bytes) %s" % (size, str(get_oid(oid)))
            self._tally(added_tally, type(get_oid(oid)), size)
        if qon.local.VERBOSE_CACHE_LOGGING:
            verbose_combined = '\n%d OBJECTS RETRIEVED FROM CACHE:\n%s\n\n%d OBJECTS LOADED FROM ZODB:\n%s\n====================================================\n' \
                               % (len(self.accessed_oids), verbose_accessed, len(self.added_oids), verbose_added)
            
        # ok, now let's finish off the summary version
        accessed = ''
        added = ''
        accessed_keys = accessed_tally.keys()
        accessed_keys.sort(lambda x, y: accessed_tally[x][1]-accessed_tally[y][1])
        added_keys = added_tally.keys()
        added_keys.sort(lambda x, y: added_tally[x][1]-added_tally[y][1])
        
        for t in accessed_keys:
            accessed += "\n --(%d bytes) (%d) %s" % (accessed_tally[t][1], accessed_tally[t][0], t)
        for t in added_keys:
            added += "\n --(%d bytes) (%d) %s" % (added_tally[t][1], added_tally[t][0], t)
        combined = '\n%d OBJECTS RETRIEVED FROM CACHE:\n%s\n\n%d OBJECTS LOADED FROM ZODB:\n%s\n====================================================\n' \
                   % (len(self.accessed_oids), accessed, len(self.added_oids), added)

        # reset oid lists to prepare for next call    
        self.clear_oid_lists()

        if qon.local.VERBOSE_CACHE_LOGGING:
            return verbose_combined
        else:
            return combined

    def clear_oid_lists(self):
        self.accessed_oids = []
        self.added_oids = []        

    def _tally(self, tally, t, size):
        if tally.has_key(t):
            tally[t][0] += 1
            tally[t][1] += size
        else:
            tally[t] = [1, size]            


# Above this line is stuff pertaining to instrumenting ZEO's disk-based ClientCache
# -------------------------------------------------------------------------------------------   
# Below this line is stuff pertaining to the Connection's in-memory PickleCache
#  NOTE: QonConnection is *NOT* currently used by database.py -- it didn't work because 
#  I don't think Connection.get() is the normal way objects are fetched from the cache.
#  TBD: find another way.

def analyze_object_cache(con):
    '''
    Spits out tallies of the item types in the object cache of the given connection.
    This routine works fine on *both* ordinary Connections, and
    a QonConnections.
    Two lists are returned:  one for ghost items, and the other for non-ghost items    
    '''
    debug_info = con._cache.debug_info()
    ghost_tally = {}
    non_ghost_tally = {}
    for oid, x, t, state in debug_info:
        if state == -1: # a state of -1 is ghost, 0 or 1 are non ghost
            if ghost_tally.has_key(t):
                ghost_tally[t] += 1
            else:
                ghost_tally[t] = 1
        else:
            if non_ghost_tally.has_key(t):
                non_ghost_tally[t] += 1
            else:
                non_ghost_tally[t] = 1

    ghosts = []
    non_ghosts = []
    ghost_keys = ghost_tally.keys()
    ghost_keys.sort(lambda x, y: ghost_tally[y]-ghost_tally[x])
    non_ghost_keys = non_ghost_tally.keys()
    non_ghost_keys.sort(lambda x, y: non_ghost_tally[y]-non_ghost_tally[x])
    
    for k in ghost_keys:
        ghosts.append("(%d) %s" % (ghost_tally[k], k))

    for k in non_ghost_keys:
        non_ghosts.append("(%d) %s" % (non_ghost_tally[k], k))        

    return (ghosts, non_ghosts)        

class QonConnection(Connection):
    """
    subclass of Connection that is instrumented so that we can see
    track cache hit % on a Connection's object cache.
    """    
    def __init__(self, version='', cache_size=400,
        cache_deactivate_after=None, mvcc=True, txn_mgr=None,
        synch=True):

        self.cache_hits = 0
        self.cache_misses = 0

        Connection.__init__(self, version, cache_size, cache_deactivate_after,\
                            mvcc, txn_mgr, synch)

    def get(self, oid):
        """Return the persistent object with oid 'oid'.

        If the object was not in the cache and the object's class is
        ghostable, then a ghost will be returned.  If the object is
        already in the cache, a reference to the cached object will be
        returned.

        Applications seldom need to call this method, because objects
        are loaded transparently during attribute lookup.

        :return: persistent object corresponding to `oid`

        :Parameters:
          - `oid`: an object id

        :Exceptions:
          - `KeyError`: if oid does not exist.  It is possible that an
            object does not exist as of the current transaction, but
            existed in the past.  It may even exist again in the
            future, if the transaction that removed it is undone.
          - `ConnectionStateError`:  if the connection is closed.
        """
        if self._storage is None:
            # XXX Should this be a ZODB-specific exception?
            raise ConnectionStateError("The database connection is closed")

        obj = self._cache.get(oid, None)
        if obj is not None:
            self.cache_hits += 1            # Added by Alex
            return obj
        obj = self._added.get(oid, None)
        if obj is not None:
            self.cache_hits += 1            # Added by Alex
            return obj

        p, serial = self._storage.load(oid, self._version)
        obj = self._reader.getGhost(p)

        obj._p_oid = oid
        obj._p_jar = self
        obj._p_changed = None
        obj._p_serial = serial

        self._cache[oid] = obj
        self.cache_misses += 1              # Added by Alex        
        return obj
        

class QonDB(DB):
    """
    subclass of ZODB.DB whose open() routine returns an QonConnection rather
    than a plain Connection. See above to see what's cool about a QonConnection.
    """
    klass = QonConnection   # that was easy.  thanks ZODB.        
