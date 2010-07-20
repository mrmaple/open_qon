#!/usr/bin/env python
"""
$Id: count_active_users.py,v 1.2 2005/03/11 20:25:31 alex Exp $
"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database, transaction_commit
from qon.user import User
from datetime import datetime, timedelta

def get_number_two(a):
    return a[2] or datetime(1990, 1, 1)

if __name__ == "__main__":
    # open the ZODB database file
    #db = open_database("file:/www/var/qon.fs")
    db = open_database()

    i = 0
    us = []
    
    for userid, user in db.user_db.root.items():
        last_login = getattr(user, str('last_login'), None)
        last_hit = getattr(user, str('last_hit'), None)
        member_since = user.get_user_data().member_since()
        us.append( (user.display_name(), userid, last_login, last_hit, member_since) )
        #print "%s) User: %s since: %s last_login: %s " % (i, user.display_name(), member_since, last_login)       
        i += 1
    db.close()

    us.sort(key=get_number_two)

    for u in us:
	print "user: %s id: %s last_login: %s, last_hit: %s, member_since: %s" % u 

