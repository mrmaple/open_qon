#!/usr/bin/python2.4
"""
$Id: cron-hourly.py,v 1.7 2007/02/03 23:52:50 alex Exp $

Various regular maintenance.
"""
import os, time
from dulcinea import site_util
from qon.base import open_database, get_database, close_database, \
    get_session_manager, get_user_database, get_list_database, \
    transaction_commit, get_group_database
import smtplib
from qon import local

site = 'qon'
config = site_util.get_config()

def update_group_karma():
    group_db = get_group_database()
    for group_id, group in group_db.root.iteritems():
        group._calc_karma_score()
        transaction_commit(None, 'GroupKarmaUpdate')

def update_stats():
    """Update the expensive site-wide stats."""
    list_db = get_list_database()

    list_db.group_stats_force_update()
    transaction_commit(None, 'GroupStatsUpdate')

    list_db.user_stats_force_update()
    transaction_commit(None, 'UserStatsUpdate')
    

def main():
    unsuccessful_recipients = ['jim@oublic.org']
    try:
        import pdb; pdb.set_trace()
        open_database()
        update_stats()
        update_group_karma()
        close_database()
    except Exception, why:
        if 1:
            sender = 'noreply@ned.com'
            subject = "Warning: Hourly cron was unsuccessful"
            body = "To: %s\nFrom: %s\nSubject: %s\n\n%s\n\n" % (",".join(unsuccessful_recipients), sender, subject, why)
            server = smtplib.SMTP('localhost')
            server.sendmail(sender, unsuccessful_recipients, body)

if __name__ == '__main__':
    main()
    
