"""
Interface to apr_memcache.

Also uses python-memcache if available for missing/broken apis.

Only includes commonly used interfaces.
"""
import cPickle as pickle
import qon.extensions.aprmemcache as amc

try:
    import memcache as _mc
except ImportError:
    _mc = None

class DummyClient(object):
    """A dummy that always returns None."""
    
    def none(self):
        return None
    
    set = none
    get = none
    delete = none
    replace = none
    add = none
    incr = none
    decr = none

class Client (object):

    def __init__(self, servers, debug=0):
        """Init memcache with list of servers."""
        self.debug = debug
        self.apr_pool = amc.py_apr_pool_create()
        self.mc = amc.apr_memcache_create(self.apr_pool, len(servers), 0)
        
        for server in servers:
            (host, port) = server.split(':')
            s = amc.apr_memcache_server_create(self.apr_pool,
                host,
                int(port),
                0,  # min client sockets
                5,  # soft max client connections
                10, # hard max client connections
                60, # seconds ttl client connection
                )
            amc.apr_memcache_add_server(self.mc, s)
        
        # see if we have python memcache
        if _mc:
            self.py_mc = _mc.Client(servers)
        else:
            self.py_mc = None
    
    def set(self, key, value, timeout=0):
        s = pickle.dumps(value, 2)
        amc.apr_memcache_set(self.mc, key, s, len(s), timeout, 0)
    
    def get(self, key):
        result = amc.apr_memcache_getp(self.mc, self.apr_pool, key)
        if result:
            return pickle.loads(result)
        else:
            return None

    def delete(self, key, timeout=0):
        amc.apr_memcache_delete(self.mc, key, timeout)
    
    def replace(self, key, value, timeout=0):
        s = pickle.dumps(value, 2)
        result = amc.apr_memcache_replace(self.mc, key, s, len(s), timeout, 0)
        return not result

    def add(self, key, value, timeout=0):
        s = pickle.dumps(value, 2)
        result = amc.apr_memcache_add(self.mc, key, s, len(s), timeout, 0)
        return not result

    def incr(self, key, amount):
        result = amc.apr_memcache_incr(self.mc, key, int(amount))
        return not result

    def decr(self, key, amount):
        result = amc.apr_memcache_decr(self.mc, key, int(amount))
        return not result

    # python-memcache methods
    
    def flush_all(self):
        if self.py_mc:
            self.py_mc.flush()
    
    def get_stats(self):
        if self.py_mc:
            return self.py_mc.get_stats()
