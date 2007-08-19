#!/usr/bin/env python
"""
$Id: report_watch_list_usage.py,v 1.1 2006/03/01 08:29:08 alex Exp $
Report watch list usage.
"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database, transaction_commit
from qon.user import User
from datetime import datetime, timedelta

if __name__ == "__main__":

    data = {}

    # open the ZODB database file
    #db = open_database("file:/www/var/qon.fs")
    db = open_database()

    i = 1
    for userid, user in db.user_db.root.items():
        num_watched = len(user.get_watch_list().watched_items())
        if num_watched > 20:
            key = 20
        else:
            key = num_watched
        if data.has_key(key):
            data[key] = data[key] + 1
        else:
            data[key] = 1
        print "%s) User: %s: %s" % (i, user.display_name(), num_watched)

        i += 1

    # print out results
    for i in range(21):
        if not data.has_key(i):
            data[i] = 0
        print "%s\t%s" % (i, data[i])

    # done
    transaction_commit()
    db.close()
