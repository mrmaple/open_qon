#!/usr/local/bin/python
"""
$Id: cron.py,v 1.20 2007/06/20 16:20:50 jimc Exp $

Various regular maintenance.
"""
import os, time
os.environ['SITE'] = 'qon'      # must appear before import qon.api

from dulcinea import site_util
from qon.base import open_database, get_database, close_database, \
    get_session_manager, get_user_database, get_list_database, \
    get_group_database, transaction_commit, get_tagged_item_database, get_tags_database

import qon.api
import smtplib
from datetime import datetime, timedelta
from qon import local


KEEP_UPLOAD_TEMPS = 24*60*60    # seconds to keep uploaded files in temp dir
SESSION_EXPIRE_HOURS = 7*24     # hours to keep sessions


site = 'qon'
config = site_util.get_config()

def purge_unsponsored_groups():
    """Remove groups which haven't been sponsored in a timely manner."""
    qon.api.group_purge_unsponsored()
    transaction_commit(None, 'PurgeUnsponsoredGroups')

def purge_mail_messages():
    """Manage users' inboxes."""
    _commit_increment = 100
    count = _commit_increment
    for user_id, user in get_user_database().root.iteritems():
        user.trash_old_messages()
        user.purge_old_messages()
        count -= 1

        if count == 0:
            transaction_commit(None, 'PurgeMailMessages')
            count = _commit_increment

    if count > 0:
        transaction_commit(None, 'PurgeMailMessages')

def clean_upload_dir():
    """Remove temporary upload files."""
    upload_dir = config.get(site, 'upload_dir',
        fallback=None)
    if upload_dir:
        now = time.time()
        for f in os.listdir(upload_dir):
            if now - os.stat(os.path.join(upload_dir, f)).st_mtime > KEEP_UPLOAD_TEMPS:
                os.unlink(os.path.join(upload_dir, f))


def decay_inactive_discussions():
    qon.api.group_decay_inactive_karma()
    # commits in group_decay_inactive_karma

def pack_database():
    """Pack the database."""
    db = get_database()
    db.pack()
    
def expire_sessions():
    """Expire user sessions."""
    expired_count = get_session_manager().del_sessions(
        age=SESSION_EXPIRE_HOURS)
    if expired_count:
        transaction_commit(None, 'ExpireSessions')
    

def update_stats():
    get_list_database().karma_stats_force_update()
    transaction_commit(None, 'KarmaStatsUpdate')

def publish_stats():
    """Call after update_stats to publish to a wiki page."""
    
    _stats_group = 'community-general'
    _stats_page = 'user_statistics'
    _stats_author = 'admin'
    
    from datetime import datetime
    from qon.ui.blocks.util import format_datetime_utc_ymd
    
    group_db = get_group_database()
    group = group_db.get_group(_stats_group)
    if group:
        wiki = group.get_wiki()
        try:
            page = wiki.pages[_stats_page]
        except KeyError:
            return
        
        # build new text to publish stats
        # date, num_users, num_groups, num_topics, num_comments, num_pages, num_revisions,
        # total_bank, total_user_pos, total_user_neg, total_topic_pos, total_topic_pos,
        # total_comment_pos, total_comment_neg, total_page_pos, total_page_neg
        # jimc: added: total PMs, group PMs, group PM recipients total increases from 15 to 18
        # added total tags, total tagged items for 20 total fields
        stats_fmt = ['%d' for i in range(20)]       # fields
        stats_fmt = ','.join(stats_fmt)             # comma-separated
        
        # indent and date is first field
        stats_fmt = '    %s,' % format_datetime_utc_ymd(datetime.utcnow()) + stats_fmt + '\n'
        
        # fill in stats
        list_db = get_list_database()
        group_stats = list_db.group_stats(force=True, ignore_out_of_date=False)
        #group_stats = list_db.group_stats(ignore_out_of_date=True)

        tidb = get_tagged_item_database()
        tags_db = get_tags_database()
        total_items_tagged = len(tidb)
        total_tags = len(tags_db.tags)

        stats = stats_fmt % (
            group_stats['users'],
            group_stats['groups'],
            group_stats['topics'],
            group_stats['comments'],
            group_stats['pages'],
            group_stats['revisions'],
            list_db.karma_total_bank(),
            list_db.karma_total_user()[0],
            list_db.karma_total_user()[1],
            list_db.karma_total_topic()[0],
            list_db.karma_total_topic()[1],
            list_db.karma_total_comment()[0],
            list_db.karma_total_comment()[1],
            list_db.karma_total_page()[0],
            list_db.karma_total_page()[1],
            # total pms, for groups, and number of group pm recipients
            list_db.total_users_pms(),
            group_stats['total_group_pms'],
            group_stats['total_group_pm_recipients'],
            total_tags,
            total_items_tagged,
            )
        
        # author is admin user
        author = get_user_database().get_user(_stats_author)
        
        # get current revision
        raw = page.versions[-1].get_raw()
        
        # append stats line
        raw += stats
        
        # set new revision - will commit
        qon.api.wiki_edit_page(wiki, page, page.name, author, page.versions[-1].title, raw)

def main():
    successful_recipients = ['jim@oublic.org']
    unsuccessful_recipients = ['jim@oublic.org']
    try:
        start = datetime.utcnow()
    
        open_database()

        # create a Publisher object for qon.api
        from qon.ui.util import create_publisher
        publisher = create_publisher()
    
        clean_upload_dir()
        expire_sessions()
        purge_mail_messages()
        purge_unsponsored_groups()
        decay_inactive_discussions()
        update_stats()
        publish_stats()
        pack_database()

        close_database()
        td = datetime.utcnow() - start

        time_in_sec = td.days*86400 + td.seconds

        if 1:
            sender = 'noreply@ned.com'
            subject = "Daily cron was successful"
            msg = 'Completed in %s seconds.' % time_in_sec
            body = "To: %s\nFrom: %s\nSubject: %s\n\n%s\n\n" % (",".join(successful_recipients), sender, subject, msg)
            server = smtplib.SMTP('localhost')
            server.sendmail(sender, successful_recipients, body)        

    except Exception, why:
        if 1:        
            sender = 'noreply@ned.com'
            subject = "Warning: Daily cron was unsuccessful"
            body = "To: %s\nFrom: %s\nSubject: %s\n\n%s\n\n" % (",".join(unsuccessful_recipients), sender, subject, why)
            server = smtplib.SMTP('localhost')
            server.sendmail(sender, unsuccessful_recipients, body)


if __name__ == '__main__':
    main()
    
