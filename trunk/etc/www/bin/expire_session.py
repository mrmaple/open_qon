#!/www/python/bin/python 
"""
$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/dulcinea/bin/expire_session.py $
$Id: $

Delete sessions whose access time is older than the age passed in as an
argument (in hours).

This script is meant to be run by cron.
"""

import sys, os
from dulcinea import local


def main (prog, args):
    usage = "usage: %s [site] [expire time]" % prog

    if len(args) != 2:
        sys.exit(usage)

    site = os.environ['SITE'] = args[0]
    expiration_hours = float(args[1])

    local.open_database()
    session_mgr = local.get_session_manager()
    expired_count = session_mgr.del_sessions(age=expiration_hours)
    if expired_count:
        get_transaction().commit()

if __name__ == '__main__':
    main(sys.argv[0], sys.argv[1:])
