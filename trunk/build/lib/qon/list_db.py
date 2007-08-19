"""
$Id: list_db.py,v 1.31 2007/03/05 12:23:24 jimc Exp $

"""
from datetime import datetime, timedelta
from persistent.list import PersistentList
from persistent.mapping import PersistentMapping
from BTrees import OOBTree
from qon.base import get_user_database, get_group_database, QonPersistent, get_connection
from qon.user_db import GenericDB
from qon.util import sort_list, del_keys_with_val
import qon.defer as defer
import qon.log

class KarmaStats(QonPersistent):
    """Store user karma stats in separate object."""

    persistenceVersion = 1

    def __init__(self):
        self.total_bank = None
        self.total_user = None
        self.total_topic = None
        self.total_comment = None
        self.total_page = None
        self.user_content_totals = OOBTree.OOBTree()

    def upgradeToVersion1(self):
        self.user_content_totals = OOBTree.OOBTree()
        self.version_upgrade_done()

class ListDB(GenericDB):
    """Maintain various hard-to-compute stats about the community."""

    persistenceVersion = 10

    _list_count = 100
    _watched_items_count = 50
    _personal_news_count = 20
    _update_time = timedelta(hours=1)
    _slow_update_time = timedelta(hours=3)

    def __init__(self):
        GenericDB.__init__(self)
        self.__deferrals = defer.DeferralList()
        self.__top_users = None
        self.__most_friends = None
        self.__most_generous = None
        self.__most_critical = None
        self.__biggest_bank = None
        self.__recent_personal_news = None
        self.__group_stats = None
        self.__newest_users = None
        self.__most_read_items = None
        self.__bottom_users = None
        self.__most_active = None
        self.__most_watched = None
        self.__karma_stats = KarmaStats()
        self.__reverse_ips = None

    def upgradeToVersion10(self):
        self.__reverse_ips = None

    def upgradeToVersion9(self):
        self.__karma_stats = KarmaStats()
        self.__karma_stats.total_bank = self.__karma_total_bank
        self.__karma_stats.total_user = self.__karma_total_user
        self.__karma_stats.total_topic = self.__karma_total_topic
        self.__karma_stats.total_comment = self.__karma_total_comment
        self.__karma_stats.total_page = self.__karma_total_page

        del self.__karma_total_bank
        del self.__karma_total_user
        del self.__karma_total_topic
        del self.__karma_total_comment
        del self.__karma_total_page

        self.version_upgrade_done()

    def upgradeToVersion8(self):
        self.__karma_total_bank = None
        self.__karma_total_user = None
        self.__karma_total_topic = None
        self.__karma_total_comment = None
        self.__karma_total_page = None
        self.version_upgrade_done()

    def upgradeToVersion7(self):
        self.__most_watched = None
        self.version_upgrade_done()

    def upgradeToVersion6(self):
        self.__most_active = None
        self.version_upgrade_done()

    def upgradeToVersion5(self):
        self.__bottom_users = None
        self.version_upgrade_done()

    def upgradeToVersion4(self):
        self.__most_read_items = None
        self.version_upgrade_done()

    def upgradeToVersion3(self):
        self.__newest_users = None
        self.version_upgrade_done()

    def upgradeToVersion2(self):
        self.__group_stats = None
        self.version_upgrade_done()

    def upgradeToVersion1(self):
        self.__recent_personal_news = None
        self.version_upgrade_done()

    def top_users(self):
        if self.__top_users:
            return self.__top_users

        user_db = get_user_database()
        users = user_db.root.values()
        bykarma = sort_list(users, lambda x: x.get_karma_score(),
            count=self._list_count)
        self.__top_users = bykarma
        return self.__top_users

    def bottom_users(self):
        if self.__bottom_users:
            return self.__bottom_users

        user_db = get_user_database()
        users = user_db.root.values()
        bykarma = sort_list(users, lambda x: -(x.get_karma_score()),
            count=self._list_count)
        self.__bottom_users = bykarma
        return self.__bottom_users

    def most_friends(self):
        if self.__most_friends:
            return self.__most_friends

        user_db = get_user_database()
        users = user_db.root.values()

        # elim zeros
        users = [u for u in users if u.positive_karma_givers()]

        byfriends = sort_list(users,
            lambda x: len(x.positive_karma_givers()),
            count=self._list_count)
        self.__most_friends = byfriends
        return self.__most_friends

    def most_generous(self):
        if self.__most_generous:
            return self.__most_generous

        user_db = get_user_database()
        users = user_db.root.values()

        # elim zeros
        users = [u for u in users if u.karma_plus_given()]

        bygiven = sort_list(users,
            lambda x: x.karma_plus_given(),
            count=self._list_count)

        self.__most_generous = bygiven
        return self.__most_generous

    def most_critical(self):
        if self.__most_critical:
            return self.__most_critical

        user_db = get_user_database()
        users = user_db.root.values()

        # elim zeros
        users = [u for u in users if u.karma_minus_given()]

        bygiven = sort_list(users,
            lambda x: x.karma_minus_given(),
            count=self._list_count)

        self.__most_critical = bygiven
        return self.__most_critical

    def biggest_bank(self):
        if self.__biggest_bank:
            return self.__biggest_bank

        user_db = get_user_database()
        users = user_db.root.values()
        bybank = sort_list(users,
            lambda x: x.get_karma_bank_balance(read_only=True),
            count=self._list_count)
        self.__biggest_bank = bybank
        return self.__biggest_bank

    def newest_users(self):
        if self.__newest_users:
            return self.__newest_users

        user_db = get_user_database()
        users = user_db.root.values()

        # elim unnamed users (so that we don't expose new users' email addresses)
        users = [u for u in users if u.contact_name]

        bydate = sort_list(users,
            lambda x: x.get_user_data().member_since(),
            count=self._list_count)

        self.__newest_users = bydate
        return self.__newest_users

    def most_active(self):
        _days_cutoff = 3

        if self.__most_active:
            return self.__most_active

        user_db = get_user_database()
        users = user_db.root.values()

        # elim users who haven't even been on the site in the last 3 days
        cutoff_date = datetime.utcnow() - timedelta(days=_days_cutoff)
        users = [(u, u.get_activity().activity_count(_days_cutoff)) for u in users if u.last_hit and u.last_hit > cutoff_date]

        get_connection().cacheGC()

        byactivity = sort_list(users, lambda x: x[1], count=self._list_count)

        self.__most_active = byactivity
        return self.__most_active


    def most_watched(self):
        """Return list of most-watched objects: [(count, object), ...]"""
        if self.__most_watched:
            return self.__most_watched

        from qon.util import get_oid

        # collect all watched objects
        oids = {}
        for user_id, user in get_user_database().root.iteritems():
            for oid in user.get_watch_list().watched_items_oids():
                oids[oid] = oids.get(oid, 0) + 1

        get_connection().cacheGC()

        # sort them
        bycount = []
        for oid, count in oids.iteritems():
            bycount.append((count, oid))

        del oids
        bycount.sort()

        bycount = bycount[-self._watched_items_count:]
        bycount.reverse()

        # get objects
        watched = []
        for count, oid in bycount:
            try:
                watched.append((count, get_oid(oid)))
            except KeyError:
                # invalid oid
                pass

        # save and return
        self.__most_watched = watched
        return self.__most_watched

    def total_users_pms (self):
        user_db = get_user_database()
        users = user_db.root.values()

        total_pms = 0
        for user in users:
            total_pms += user.get_user_data().get_activity().get_total_pms_sent()
        return total_pms

    def total_group_pms (self):
        """ Get the number of group pms, and the number of recipients of all group pms

        group_pms, group_pm_recipients = self.total_group_pms()
        """
        group_pms, num_recipients = (0,0)
        for user_id, group in get_group_database().root.iteritems():
            group_pms += group.get_total_group_pms()
            num_recipients +=  group.get_total_group_pms() * group.get_num_members()

        return (group_pms, num_recipients)

    def notify_user_changed(self):
        pass
        # don't do this because we don't want users to have to wait for
        # an update. cron-hourly.py takes care of this
        # if self.__deferrals.defer('user', self._slow_update_time):
        #     self.user_stats_force_update()

    def reset_user_lists(self):
        self.__top_users = None
        self.__bottom_users = None
        self.__most_friends = None
        self.__most_generous = None
        self.__most_critical = None
        self.__biggest_bank = None
        self.__newest_users = None
        self.__most_active = None
        self.__most_watched = None
        self.__most_read_items = None
        self.__recent_personal_news = None

    def user_stats_force_update(self):
        self.reset_user_lists()

        def trim_reverse(l):
            l2 = [user for score, user in l[-self._list_count:]]
            l2.reverse()
            return l2

        bykarma = []
        byfriends = []
        bygiven = []
        byneg = []
        bybank = []
        bydate = []
        news_bydate = []

        user_db = get_user_database()
        count = 1
        for user_id, user in user_db.root.iteritems():
            bykarma.append((user.get_karma_score(), user))
            byfriends.append((len(user.positive_karma_givers()), user))
            bygiven.append((user.karma_plus_given(), user))
            byneg.append((user.karma_minus_given(), user))
            bybank.append((user.get_karma_bank_balance(read_only=True), user))

            if user.contact_name:
                bydate.append((user.get_user_data().member_since(), user))

            for item in user.blog.get_items():
                news_bydate.append((item.last_modified(consider_comments=True), item))

            if count % 1000 == 0:
                get_connection().cacheGC()

        # reduce in-memory usage
        get_connection().cacheGC()

        bykarma.sort()
        self.__top_users = trim_reverse(bykarma)
        self.__bottom_users = [user for score, user in bykarma[:self._list_count]]
        del bykarma

        byfriends.sort()
        self.__most_friends = trim_reverse(byfriends)
        del byfriends

        bygiven.sort()
        self.__most_generous = trim_reverse(bygiven)
        del bygiven

        byneg.sort()
        self.__most_critical = trim_reverse(byneg)
        del byneg

        bybank.sort()
        self.__biggest_bank = trim_reverse(bybank)
        del bybank

        bydate.sort()
        self.__newest_users = trim_reverse(bydate)
        del bydate

        news_bydate.sort()
        news_bydate = news_bydate[-self._personal_news_count:]
        self.__recent_personal_news = PersistentList([item for date, item in news_bydate])
        del news_bydate

#        self.top_users()
#        self.bottom_users()
#        self.most_friends()
#        self.most_generous()
#        self.most_critical()
#        self.biggest_bank()
#        self.newest_users()

        self.most_active()
        self.most_watched()
        self.most_read_items()
#        self.recent_personal_news()
        self.__deferrals.cancel('user')

    # -------------------------------------------------------------------

    def get_reverse_ips(self):
        """Returns BTree: ip -> [(datetime, user), ...]"""
        if not self.__reverse_ips or self.__deferrals.defer('reverse_ips', self._slow_update_time):

            self.__reverse_ips = OOBTree.OOBTree()

            for user_id, user in get_user_database().root.iteritems():
                ips = user.get_ip_addresses().iteritems()
                for ip, dt in ips:
                    if not self.__reverse_ips.has_key(ip):
                        self.__reverse_ips[ip] = []

                    self.__reverse_ips[ip].append((dt, user))

        return self.__reverse_ips


    # -------------------------------------------------------------------

    def karma_total_bank(self):
        if self.__karma_stats.total_bank is not None:
            return self.__karma_stats.total_bank

        total = 0
        for user_id, user in get_user_database().root.iteritems():
            total += user.get_karma_bank_balance(read_only=True)

        self.__karma_stats.total_bank = total

        qon.log.stats_info('KarmaStats\tbank:%d' % total)

        return self.__karma_stats.total_bank

    def karma_total_user(self):
        """Returns (total positive, total negative)."""
        if self.__karma_stats.total_user is not None:
            return self.__karma_stats.total_user

        total_plus = 0
        total_minus = 0
        for user_id, user in get_user_database().root.iteritems():
            total_plus += user.karma_plus_received()
            total_minus += user.karma_minus_received()

        self.__karma_stats.total_user = (total_plus, total_minus)
        qon.log.stats_info('KarmaStats\tuser:%d,%d' % self.__karma_stats.total_user)
        return self.__karma_stats.total_user

    def karma_total_topic(self):
        """Returns (total positive, total negative)."""
        if self.__karma_stats.total_topic is not None:
            return self.__karma_stats.total_topic

        self.calc_karma_total_blogitems()
        return self.__karma_stats.total_topic

    def karma_total_comment(self):
        """Returns (total positive, total negative)."""
        if self.__karma_stats.total_comment is not None:
            return self.__karma_stats.total_comment

        self.calc_karma_total_blogitems()
        return self.__karma_stats.total_comment

    def calc_karma_total_blogitems(self):
        """Compute karma totals for all discussion topics and comments."""

        def process_topic(item):
            totals['topic_plus'] += item.karma_plus_received()
            totals['topic_minus'] += item.karma_minus_received()

        def process_comment(comment):
            totals['comment_plus'] += comment.karma_plus_received()
            totals['comment_minus'] += comment.karma_minus_received()

            # capture comment karma for user: a positive total and a negative total
            author_id = comment.author.get_user_id()
            score = comment.get_karma_score()

            if score != 0:
                # get current totals
                _tot = user_comment_karma.get(author_id, (0, 0))

                if score > 0:
                    user_comment_karma[author_id] = (_tot[0] + score, _tot[1])
                elif score < 0:
                    user_comment_karma[author_id] = (_tot[0], _tot[1] + score)


        totals = dict(topic_plus=0, topic_minus=0, comment_plus=0, comment_minus=0)
        user_comment_karma = {}

        for user_id, group in get_group_database().root.iteritems():
            for item in group.blog.get_all_items():
                process_topic(item)
                for comment in item.get_all_comments():
                    process_comment(comment)
            get_connection().cacheGC()

        # personal news
        for user_id, user in get_user_database().root.iteritems():
            for item in user.get_blog().get_all_items():
                process_topic(item)
                for comment in item.get_all_comments():
                    process_comment(comment)
            get_connection().cacheGC()


        self.__karma_stats.total_topic = (totals['topic_plus'], totals['topic_minus'])
        self.__karma_stats.total_comment = (totals['comment_plus'], totals['comment_minus'])
        qon.log.stats_info('KarmaStats\ttopic:%d,%d' % self.__karma_stats.total_topic)
        qon.log.stats_info('KarmaStats\tcomment:%d,%d' % self.__karma_stats.total_comment)

        self.__karma_stats.user_content_totals = OOBTree.OOBTree(user_comment_karma)

    def karma_user_content_totals(self, user):
        """Returns totals of user-authored comments only: (total positive scores, total negative scores)."""
        return self.__karma_stats.user_content_totals.get(user.get_user_id(), (0, 0))

    def karma_top_user_content(self):
        """Return list of top contributers sorted by net: (net, user, positive, negative)."""

        bynet = [(pos+neg, user_id, pos, neg) \
            for user_id, (pos, neg) in \
            self.__karma_stats.user_content_totals.iteritems()]

        bynet.sort()
        bynet = bynet[-self._list_count:]
        bynet.reverse()

        user_db = get_user_database()
        return [(tot, user_db.get_user(user_id), pos, neg) \
            for tot, user_id, pos, neg in bynet]


    def karma_total_page(self):
        """Returns (total positive, total negative)."""
        if self.__karma_stats.total_page is not None:
            return self.__karma_stats.total_page

        total_plus = 0
        total_minus = 0
        for user_id, group in get_group_database().root.iteritems():
            for name, page in group.wiki.pages.iteritems():
                total_plus += page.karma_plus_received()
                total_minus += page.karma_minus_received()

        self.__karma_stats.total_page = (total_plus, total_minus)
        qon.log.stats_info('KarmaStats\tpage:%d,%d' % self.__karma_stats.total_page)
        return self.__karma_stats.total_page

    def reset_karma_lists(self):
        self.__karma_stats.total_bank = None
        self.__karma_stats.total_user = None
        self.__karma_stats.total_topic = None
        self.__karma_stats.total_comment = None
        self.__karma_stats.total_page = None

    def karma_stats_force_update(self):
        self.reset_karma_lists()
        self.karma_total_bank()
        self.karma_total_user()
        self.karma_total_topic()
        self.karma_total_comment()
        self.karma_total_page()

    # -------------------------------------------------------------------

    def group_stats(self, force=0, ignore_out_of_date=False):

        # force update every self._slow_update_time; cron-hourly.py
        if force or self.__deferrals.defer('group_stats', self._slow_update_time):
            if not ignore_out_of_date:
                self.__group_stats = None

        if self.__group_stats:
            return self.__group_stats

        num_groups = num_topics = num_comments = \
            num_pages = num_revisions = 0

        for user_id, g in get_group_database().root.iteritems():
            num_groups += 1
            items = g.blog.get_items()
            num_topics += len(items)

            for i in items:
                num_comments += i.num_comments()

            for page_id, page in g.wiki.pages.iteritems():
                num_pages += 1
                num_revisions += len(page.versions)

            get_connection().cacheGC()

        gs = PersistentMapping()
        gs['users'] = len(get_user_database().root.keys())
        gs['groups'] = num_groups
        gs['topics'] = num_topics
        gs['comments'] = num_comments
        gs['pages'] = num_pages
        gs['revisions'] = num_revisions
        gs['update_time'] = datetime.utcnow()

        group_pms, group_pm_recipients = self.total_group_pms()
        gs['total_group_pms'] = group_pms
        gs['total_group_pm_recipients'] = group_pm_recipients

        self.__group_stats = gs

        # log it
        qon.log.stats_info('GroupStats\tusers:%(users)s\tgroups:%(groups)s\ttopics:%(topics)s\tcomments:%(comments)s\tpages:%(pages)s\trevisions:%(revisions)s\tgroup_pms%(total_group_pms)s\tgroup pm recipients:%(total_group_pm_recipients)s' % gs)

        return self.__group_stats

    def group_stats_force_update(self):
        self.group_stats(force=1)
        self.__deferrals.cancel('group_stats')

    def recent_personal_news(self):
        """Return list of recent personal news BlogItems."""
        if self.__recent_personal_news:
            plist = self.__recent_personal_news[:]
            plist.reverse()
            return [i for i in plist if not i.is_deleted()]
        else:
            user_db = get_user_database()

            bydate = []
            for user_id, user in user_db.root.iteritems():
                for item in user.blog.get_items():
                    bydate.append((item.last_modified(consider_comments=True), item))

            get_connection().cacheGC()
            bydate.sort()
            bydate = bydate[-self._personal_news_count:]

            # store in oldest-to-newest order
            self.__recent_personal_news = PersistentList([item for date, item in bydate])

            # return in newest-to-oldest order
            bydate.reverse()
            return [item for date, item in bydate]

    def notify_personal_news_added(self, item):
        """Notice that a personal news item (BlogItem) was created."""
        plist = self.__recent_personal_news
        if not plist:
            plist = PersistentList()
        plist.append(item)
        plist = plist[-self._personal_news_count:]
        self.__recent_personal_news = plist

    def most_read_items(self):
        """Return list of most-widely-read discussion items and user news items."""
        _days_cutoff = 3

        if self.__most_read_items:
            return self.__most_read_items

        items = []

        # discussions
        for group_id, group in get_group_database().root.iteritems():
            items.extend(group.blog.items_with_reader_counts())

        get_connection().cacheGC()

        # user news
        for user_id, user in get_user_database().root.iteritems():
            items.extend(user.blog.items_with_reader_counts())

        get_connection().cacheGC()

        # weed out items that haven't been updated in the last 3 days
        # (or else this list doesn't change much, and shows very old content)
        cutoff_date = datetime.utcnow() - timedelta(days=_days_cutoff)
        items = [i for i in items if not i[1].is_deleted() and i[1].last_modified(consider_comments=True) > cutoff_date]

        items.sort()
        items = items[-self._watched_items_count:]
        items.reverse()
        self.__most_read_items = items
        return items

