from xmlrpclib import Server
#from pyxmlrpclib import Server #didn't work
from datetime import datetime, timedelta

if __name__=='__main__':
    calls = 10000
    server = Server("http://localhost:4000");
    start_time = datetime.utcnow()
    x = 1;
    while x <= calls:
        y = server.test.go(x);
        print "%s -> %s" % (x,y)
        x += 1
    elapsed_seconds = max((datetime.utcnow()-start_time).seconds, 1)
    print "---------------------------------------------------"
    print "%s calls in %s seconds => %s calls/sec" % (calls, elapsed_seconds, float(calls) / float(elapsed_seconds))
