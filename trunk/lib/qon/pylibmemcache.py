"""
Interface to libmemcache.

Also uses python-memcache if available for missing/broken apis.

Only includes commonly used interfaces.
"""
import cPickle as pickle
import qon.extensions.libmemcache as lmc

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

        self.mc = lmc.mc_new()
        lmc.mc_timeout(self.mc, 30, 0)
        

        # tell libmemcache to ignore fatal errors instead of aborting process
        print "lmc error filter=0x%x" % lmc.mc_err_filter_get()
        
        print lmc.mc_err_filter_add(lmc.MCM_ERR_LVL_ERR + lmc.MCM_ERR_LVL_FATAL)
        
        print "lmc error filter=0x%x" % lmc.mc_err_filter_get()

        
        for server in servers:
            lmc.mc_server_add4(self.mc, server)
        
        # see if we have python memcache
        if _mc:
            self.py_mc = _mc.Client(servers)
        else:
            self.py_mc = None
    
    def set(self, key, value, timeout=0):
        s = pickle.dumps(value, 2)
        if self.debug:
            print "setting key %s" % (key)
        lmc.mc_set(self.mc, key, len(key), s, len(s), timeout, 0)
    
    def get(self, key):
        if self.debug:
            print "getting key %s" % key
        result = lmc.call_mc_aget2(self.mc, key, len(key))
        if result:
            try:
                return pickle.loads(result)
            except:
                print "pylibmemcache: unpickling error for key %s." % key
                return None
        else:
            if self.debug:
                print "get missed key %s" % key
            return None

    def delete(self, key, timeout=0):
        lmc.mc_delete(self.mc, key, len(key), timeout)
    
    def replace(self, key, value, timeout=0):
        s = pickle.dumps(value, 2)
        result = lmc.mc_replace(self.mc, key, len(key), s, len(s), timeout, 0)
        return not result

    def add(self, key, value, timeout=0):
        s = pickle.dumps(value, 2)
        result = lmc.mc_add(self.mc, key, len(key), s, len(s), timeout, 0)
        return not result

    def incr(self, key, amount):
        result = lmc.mc_incr(self.mc, key, len(key), int(amount))
        return result

    def decr(self, key, amount):
        result = lmc.mc_decr(self.mc, key, len(key), int(amount))
        return result

    # python-memcache methods
    
    def flush_all(self):
        lmc.mc_flush_all(self.mc)
        if 0 and self.py_mc:
            self.py_mc.flush()
    
    def get_stats(self):
        return lmc.mc_server_stats(mc, mc.server_list.tqh_first)
