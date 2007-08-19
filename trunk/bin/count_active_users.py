#!/usr/bin/env python
"""
$Id: count_active_users.py,v 1.2 2005/03/11 20:25:31 alex Exp $
"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database, transaction_commit
from qon.user import User
from datetime import datetime, timedelta

if __name__ == "__main__":


    # open the ZODB database file
    #db = open_database("file:/www/var/qon.fs")
    db = open_database()

    days = 61
    cutoff_date = datetime.utcnow() - timedelta(days=days)


    i = 0
    j = 0
    k = 0
    l = 0
    n = 0
    
    for userid, user in db.user_db.root.items():
        print "%s) User: %s" % (i, user.display_name())
        last_login = getattr(user, str('last_login'), None)
        last_hit = getattr(user, str('last_hit'), None)
        member_since = user.get_user_data().member_since()
        if (last_login and last_login > cutoff_date) or (last_hit and last_hit > cutoff_date):
            j += 1
            if member_since > cutoff_date:
                n += 1
        elif member_since > cutoff_date:
            l += 1
            assert(not last_login and not last_hit)
        if not last_login and not last_hit:
            k += 1

        i += 1

    print "\n\n%s active users out of %s users in the last %s days" % (j, i, days)
    print "In addition, %s users joined in the last %s days, but never logged in" % (l, days)
    print "Also, of the %s active users, %s joined in the last %s days" % (j, n, days)
    print "%s never logged in" % k

    # done
    transaction_commit()
    db.close()
