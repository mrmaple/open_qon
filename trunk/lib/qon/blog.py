"""
$Id: blog.py,v 1.106 2007/05/11 01:17:05 jimc Exp $

Blog blog blog

"""
import sys, zlib
from datetime import datetime, timedelta
from persistent.list import PersistentList
from BTrees import IOBTree, OOBTree
from dulcinea.database import unpack_oid, pack_oid

import qon.karma

from qon.database import ConflictAvoidingIOBTree, ConflictAvoidingOOBTree
from qon.base import QonPersistent, PersistentCache, transaction_commit
from qon.util import CompressedText, coerce_to_list, sort_list, iso_8859_to_utf_8, get_oid
from qon.watch import Watchable, never

def highest_score_items(blogs, count=10):
    """Return list of highest scoring items across multiple blogs.
    
    The order in which tied items are returned is not defined.
    """
    blogs = coerce_to_list(blogs)
    items = []
    for blog in blogs:
        items.extend(blog.highest_score_items(count))
        
    items = sort_list(items, lambda x: x.get_karma_score())
    return items

def recent_items(blogs, count=10, consider_comments=True):
    """Return list of recent items across multiple blogs, most recent first,
    with blogs intermingled.
    
    If consider_comments is True, item's last-modified date takes comment
    postings into account.
    """
    blogs = coerce_to_list(blogs)
    items = []
    for blog in blogs:
        items.extend(blog.recent_items_with_date(count,
            consider_comments=consider_comments))
    items.sort()
    items = [i for date, i in items[-count:]]
    items.reverse()
    return items
    
def recent_items_by_author(blogs, author, count=10, not_by=0):
    """Return list of recent items by author(s) across multiple blogs.
    
    If not_by is not zero, returns the complement (i.e., items not by
    the given author(s).
    
    author may be given as a single User instance or a list of Users.
    """
    blogs = coerce_to_list(blogs)
    items = []
    for blog in blogs:
        items.extend(blog.recent_items_by_author(author, count, not_by))
    
    items = sort_list(items, lambda x: x.last_modified(), count=count)
    return items

def recent_comments_by_author(blogs, author, count=10):
    """Return most recent comments in blogs by author.
    
    Returns list of tuples: (comment, parent item)
    """
    blogs = coerce_to_list(blogs)
    items = []
    for blog in blogs:
        items.extend(blog.recent_comments_by_author(author, count))
    
    bydate = [(i.last_modified(consider_comments=False), i, parent) for i, parent in items]
    bydate.sort()
    
    items = [(i, parent) for date, i, parent in bydate[-count:]]
    items.reverse()
    return items
    
class Reader(QonPersistent):
    """Represents a single user/reader of a Blog.
    
    Uses a conflict-avoiding IO BTree:
        self.read_items[item_id] = (datetime, count)
    """
    
    persistenceVersion = 2
    
    def __init__(self, user):
        self.user = user
        self.read_items = ConflictAvoidingIOBTree()
        
    def upgradeToVersion2(self):
        for k,v in self.read_items.iteritems():
            self.read_items[k] = (v, 0)
        self.version_upgrade_done()
            
    def upgradeToVersion1(self):
        newbt = ConflictAvoidingIOBTree()
        for k,v in self.read_items.iteritems():
            newbt[k] = v
        
        del self.read_items
        self.read_items = newbt
        self.version_upgrade_done()
        
    def read_item(self, item_id, now=None):
        """Notice that I have read item number item_id. Returns self as a convenience."""
        now = now or datetime.utcnow()
        dt, count = self.read_items.get(item_id, (never, 0))
        
        # don't allow changing last_read to anything earlier than it is now
        now = max(now, dt)
        
        self.read_items[item_id] = (now, count + 1)
        return self
        
    def has_read_item(self, item_id, updated=None):
        """Have I read item_id, which was optionally updated at updated?"""
        
        last_read, count = self.read_items.get(item_id, (None, 0))
        if last_read:
            if updated:
                return last_read >= updated
            else:
                return True
        return False

    def last_read(self, item_id):
        """Return the datetime of the last time that the user read a BlogItem"""
        dt, count = self.read_items.get(item_id, (never, 0))
        return dt
        
    def last_read_count(self, item_id):
        """Return (last read datetime, count int)."""
        return self.read_items.get(item_id, (never, 0))
            
        
class ReaderList(QonPersistent):
    """A list of Readers to go into a Blog.
    
    Structures:
        self.readers[user_id] = Reader()
    """
    
    def __init__(self):
        self.readers = OOBTree.OOBTree()
        
    def read_item(self, user, item_id, now=None):
        """Notice that user has read item_id. Creates a Reader if none exists."""
        return self.get_reader(user, create=True).read_item(item_id, now=now)
        
    def has_read_item(self, user, item_id, updated=None):
        """Have I read this item? Creates a Reader if none exists."""
        return self.get_reader(user, create=True).has_read_item(item_id, updated=updated)
        
    def readers_of_item(self, item_id):
        """Return dict of user_ids[reader] who have read item_id. Expensive."""
        users = {}
        for user_id, reader in self.readers.iteritems():
            if reader.has_read_item(item_id):
                users[user_id] = reader
        return users

    def last_read(self, user, item_id):
        """Return the datetime of the last time that a given user read a BlogItem"""
        reader = self.readers.get(user.get_user_id(), None)
        if reader:
            return reader.last_read(item_id)
        else:
            return never
        
    def get_reader(self, user, create=False):
        """Return user's reader"""
        reader = self.readers.get(user.get_user_id(), None)
        if not reader and create:
            reader = self.new_reader(user)
        return reader
        
    def new_reader(self, user):
        if self.get_reader(user):
            raise KeyError, "reader for user %s already exists" % user.get_user_id()
        
        reader = Reader(user)
        self.readers[user.get_user_id()] = reader
        return reader
            
class Blog(QonPersistent, Watchable):
    """Contains a blog.
    """
    persistenceVersion = 4
    
    _karma_new_item             = 1
    _inactive_period            = timedelta(days=7) # period after which item is considered inactive
    _inactive_karma_discount    = 1                 # daily karma score decay of inactive items
    
    def __init__(self, ihb):
        """Create a blog belonging to IHasBlog."""
        Watchable.__init__(self)
        self.ihb = ihb
        self.__items = PersistentList()
        self.__main_item = None

    def upgradeToVersion4(self):
        self.__main_item = None
        self.version_upgrade_done()
        
    def upgradeToVersion3(self):
    
        # move all data from ReaderList into BlogItems
        from qon.base import get_user_database
        user_db = get_user_database()
        
        for user_id, reader in self.__reader_list.readers.iteritems():
            user = user_db.get_user(user_id)
            if not user:
                continue
            user_oid = unpack_oid(user._p_oid)
            
            for item_id, data in reader.read_items.iteritems():
                dt, count = data
                item = self.get_item(item_id)
                
                item._BlogItem__user_access[user_oid] = (dt, count)
    
        del self.__reader_list
        self.version_upgrade_done()
        
    def upgradeToVersion2(self):
        self.__reader_list = ReaderList()
        self.version_upgrade_done()
        
    def upgradeToVersion1(self):
        self.ihb = self.group
        del self.group
        self.version_upgrade_done()
        
    def can_pay_for_new_item(self, user):
        return user.can_give_karma(self._karma_new_item)
        
    def new_item(self, author, title, summary, main='', no_mod=1, no_pay=0):
        """Create a new blog item. If no_mod, don't assign negative karma."""
        
        # charge author for new item - don't create item if can't pay
        # no charge for posting to author's blog
        if (not no_pay) and (self is not author.blog):
            try:
                author.pay_karma(self._karma_new_item)
            except qon.karma.NoKarmaToGive:
                return None
        
        # create the item
        item = BlogItem(blog=self,
            author=author,
            title=title,
            summary=summary,
            main=main)
        if not no_mod:
            self.assign_new_karma(item)
        
        # add the item
        self.add_item(item)
        
        # assign activity credit
        author.karma_activity_credit()
        
        # pretend the author has read the item he just created
        item.read_item(author)
        
        # notify IHB that we created an item
        self.ihb.notify_new_item(item)
        return item
        
    def add_item(self, item):
        self.__items.append(item)
        self.watchable_changed(item.date)
    
    def assign_new_karma(self, item):
        """Assign default karma level for new items."""
        
        if self.ihb.is_owner(item.author):
            # owner items get no negative karma
            return
        
        member_count = len(self.ihb.get_member_list())
        karma = member_count // 5
        
        if karma < 2:
            karma = 2
        
        item.add_anon_karma(-karma)
        
    def decay_inactive_items(self):
        """Call this daily to decay karma of inactive items.
        Returns a list of items that got decayed.
        """
        decayed_items = []
        decay_time = datetime.utcnow() - self._inactive_period
        for item in self.__items:
            if item.get_karma_score() > 0:
                if item.watchable_last_change() < decay_time:
                    item.add_anon_karma(-self._inactive_karma_discount)
                    decayed_items.append(item)
        return decayed_items

    def last_modified(self):
        """Return datetime of last modification."""
        sys.stderr.write('WARNING: using deprecated qon.blog.Blog.last_modified.')
        return self.watchable_last_change()
        
    def recent_items(self, count=10, consider_comments=True):
        """Return count most recent items, from newest to oldest."""
        items = [i for date, i in self.recent_items_with_date(count=count,
            consider_comments=consider_comments)]
        items.reverse()
        return items
        
    def recent_items_with_date(self, count=10, consider_comments=True):
        """Return count most recent items as tuples: (date, item).
        
        If consider_comments is True, last-mod date is the latest of a posted
        comment or an edit to the original item. Otherwise, last-mod date is
        date of original posting only, even if the item has been edited.
        """
        if consider_comments:
            # return from cache if possible
            if hasattr(self, '_cached_recent_items_with_date'):
                return self._cached_recent_items_with_date[-count:]

            bydate = [(i.last_modified(consider_comments=consider_comments), i) \
                for i in self.get_items()]
            bydate.sort()

            # cache result
            self._cached_recent_items_with_date = bydate
        else:
            bydate = [(i.date, i) for i in self.get_items()]
            bydate.sort()

        return bydate[-count:]
        
    def unread_items(self, user):
        """Return items which have been unread or updated since last read
        by user. Returns [(i.last_modified(), i), ... for unread items].
        """
        if not user:
            return []

        return [(i.last_modified(), i) for i in self.get_items() \
            if not i.has_read_item(user, updated=i.last_modified())]

    def mark_items_as_read(self, user, as_of=None):
        """Mark all items in this blog as having been read by user.

        If as_of is not None, mark them read as of the provided datetime.
        """

        now = as_of or datetime.utcnow()

        for item in self.get_items():
            item.read_item(user, now)

    def recent_items_by_author(self, author, count=10, not_by=0):
        """Return most recent items by author from newest to oldest."""
        
        author = coerce_to_list(author)
        items = []
        recent_items = self.get_items()
        recent_items.reverse()
        
        bydate = [(i.last_modified(), i) for i in self.get_items() \
            if (not not_by and (i.author in author)) or \
                (not_by and (i.author not in author))]
        bydate.sort()
        
        items = [i for date, i in bydate[-count:]]
        items.reverse()
        return items
        
    def recent_comments_by_author(self, author, count=10):
        """Return most recent comments in this blog by author.
        
        Returns list of tuples: (comment, parent item)
        """
        
        comments = []
        for item in self.get_items():
            com = item.comments_by(author)
            if com:
                comments.extend([(c, item) for c in com])
                
            
        bydate = [(i.last_modified(), i, parent) for i, parent in comments]
        bydate.sort()
        
        items = [(i, parent) for date, i, parent in bydate[-count:]]
        items.reverse()
        return items
        
        
    def highest_score_items(self, count=10):
        """Returns highest scoring items, highest to lowest."""
        
        items = [(i.get_karma_score(), i.date, i) for i in self.get_items() if i.get_karma_score() > 0]
        items.sort()
        items = [i for karma, date, i in items[-count:]]
        items.reverse()
        return items

    def num_items(self):
        # return len(self.get_items())      // slower because it creates a new list
        num = 0
        for item in self.__items:
            if not item.is_deleted():
                num +=1
        return num

    def num_active_items(self, days=3, consider_comments=True):
        """Returns the number of blog items that have been modified or commented on
        in the last X days. Also returns the date of the latest item, in case it's useful"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        items = self.get_items()
        # active_items = [item for item in items if item.last_modified(consider_comments) > cutoff_date]      // slower because it creates a new list
        # return len(active_items)         
        num = 0
        latest_date = never
        for item in items:
            mod = item.last_modified(consider_comments)
            if mod > cutoff_date:
                num += 1
            if mod > latest_date:
                latest_date = mod
        return (num, latest_date)

    def num_old_new_comments(self, user):
        """Return as a tuple number of comments old and new for all undeleted BlogItems"""
        old = new = 0
        
        # we traverse the item list manually, instead of using get_items, in order
        # to save the additional lookup of having to call item_index(item) to retrieve
        # its index.
        item_index = 0
        for i in self.__items:
            if not i.is_deleted():
                last_read = i.last_read(user)
                (i_old, i_new) = i.num_old_new_comments(last_read)
                old += i_old
                new += i_new
            item_index += 1
        return (old, new)
        
    def has_unread_recent_items(self, user, count):
        """Return True if any of count most recent items haven't been read by user."""
        items = self.recent_items(count=count)
        for item in items:
            if not item.has_read_item(user, updated=item.last_modified()):
                return True
        return False
        
    def items_with_reader_counts(self):
        """Return list of items with reader counts: [(count, item), ...]"""
        items = []
        
        for i in self.get_items():
            view_count, num_readers = i.item_views()
            items.append((num_readers, i))
        return items
    
    def in_items(self, item):
        """Return true if item is in my list of items."""
        return item in self.__items
        
    def item_index(self, item):
        return self.__items.index(item)
        
    def get_items(self):
        return [item for item in self.__items if not item.is_deleted()]

    def get_all_items(self):
        return self.__items[:]
        
    def get_item(self, index):
        """Return a blog item by its index/id"""
        try:
            return self.__items[index]
        except IndexError:
            return None

    def get_main_item(self):
        """A Blog's main item is a primary discussion.
        Returns an instance of BlogItem"""
        return self.__main_item

    def set_main_item(self, item):
        """Set the blog's primary BlogItem
        A Blog's main item is a primary discussion."""
        assert(isinstance(item, BlogItem) or item is None)
        self.__main_item = item

    def get_item_count(self):
        """Return number of items, including deleted items."""
        return len(self.__items)
        
    def get_limbo_items(self):
        return [item for item in self.get_items() if item.get_karma_score() < 0]
        
    def notify_karma_changed(self):
        """Notice that karma changed on an item."""
        self.ihb.notify_karma_changed()        

    # Watchable methods
        
    def watchable_name(self):
        return self.ihb.blog_name()
    
    def watchable_changed(self, now=None):
        # remove cached recent_items
        if hasattr(self, '_cached_recent_items_with_date'):
            del self._cached_recent_items_with_date

        # tells group he has changed, too
        Watchable.watchable_changed(self, now)
        self.ihb.watchable_changed(now)        
        
    def watchable_modified_date(self):
        return self.watchable_last_change()

    def can_read(self, user):
        return self.ihb.can_read(user)
    
        
class HasComments:
    """Mixin class providing simple container of comments."""

    __persistenceVersion = 1

    def __init__(self):
        self.__comments = None
        self.__comment_flags = None

    def _upgradeToVersion1(self):
        # make comments attribute private and remove empty PersistentList
        # so that every comment isn't hogging an extra ZODB object.
        if self.comments:
            self.__comments = PersistentList(self.comments)
        else:
            self.__comments = None

        del self.comments

        # build flags list, which is just a cache of the deleted boolean
        comments = self.get_all_comments()
        if comments:
            self.__comment_flags = PersistentList()
            for comment in comments:
                self.__comment_flags.append(comment.is_deleted(use_attr=True))
        else:
            self.__comment_flags = None

    def add_comment(self, comment):
        if not self.__comments:
            self.__comments = PersistentList()

        if not self.__comment_flags:
            self.__comment_flags = PersistentList()

        self.__comments.append(comment)
        self.__comment_flags.append(0)

    def comment_index(self, item):
        if self.__comments:
            return self.__comments.index(item)
        else:
            # raise ValueError as if item were not in list
            raise ValueError
        
    def get_comment(self, comment_index):
        if not self.__comments:
            return None

        try:
            return self.__comments[comment_index]
        except IndexError:
            return None

    def get_comments(self):
        if self.__comments:
            return [item for item in self.__comments if not item.is_deleted()]
        else:
            return []

    def num_comments(self):
        """Return number of undeleted comments."""
        if not self.__comment_flags:
            return 0

        count = 0
        for f in self.__comment_flags:
            if not f:
                count += 1
        return count

    def num_all_comments(self):
        return len(self.get_all_comments())

    def get_all_comments(self):
        if self.__comments:
            return self.__comments[:]
        else:
            return []

    def get_comment_flags(self, item):
        assert self.__comment_flags is not None
        return self.__comment_flags[self.comment_index(item)]

    def set_comment_flags(self, item, val):
        assert self.__comment_flags is not None
        self.__comment_flags[self.comment_index(item)] = val
    
    def comments_by(self, author):
        """Return comments by author if any.
        
        Comments must have `author` attribute.
        """
        if not self.__comments:
            return []
        return [c for c in self.__comments if c.author is author]

    def num_old_new_comments(self, since_when):
        """Return as a tuple number of comments old and new"""
        old = new = 0
        
        # pmo redefine to use get_all_comments instead of get_comments 6/6/05
        for c in self.get_all_comments():
            if c.date <= since_when:
                old += 1
            else:
                new += 1
        return (old, new)

    def is_duplicate(self, comment):
        """ Check to see if the given comment is a duplicate of
        the latest comment """
        if self.__comments and (len(self.__comments) > 0):
            latest_comment = self.__comments[-1]
            if latest_comment.author == comment.author and \
               latest_comment.title == comment.title and \
               latest_comment.get_summary() == comment.get_summary() and \
               latest_comment.get_main() == comment.get_main() and \
               latest_comment.is_deleted() == comment.is_deleted():
                return True
        return False

class BlogItem(QonPersistent, qon.karma.HasKarma, Watchable, HasComments):

    persistenceVersion = 6

    def __init__(self, blog, author, title, summary, main='', dont_watch=0):
        qon.karma.HasKarma.__init__(self)
        Watchable.__init__(self)
        HasComments.__init__(self)
        self.blog = blog
        self.__deleted = 0
        self.author = author
        self.title = title
        self.__summary = CompressedText(summary)
        if main:
            self.__main = CompressedText(main)
        else:
            self.__main = None
        self.__cached_html_summary = PersistentCache(self._update_html_cache)
        # history is a string, showing diffs as items are edited
        self.history = None
        self.date = datetime.utcnow()
        self.modified = None
        self.parent_blogitem = None     # for comment, will point to parent blogitem upon add_comment(); otherwise None
        
        if dont_watch:
            """Comments aren't watchable."""
            self.not_watchable = 1
        else:
            # for watchable items only (not comments)
            self.__user_access = ConflictAvoidingOOBTree()

    def upgradeToVersion6(self):
        self.history = None

    def upgradeToVersion5(self):
        self.title = iso_8859_to_utf_8(self.title)

    def upgradeToVersion4(self):
        self.__deleted = self.deleted
        del self.deleted

        # upgrade HasComments
        HasComments._upgradeToVersion1(self)

        # elim __main's CompressedText
        if not self.get_main():
            self.__main = None

        self.version_upgrade_done()        
        
    def upgradeToVersion3(self):
        if not self.not_watchable:
            self.__user_access = ConflictAvoidingOOBTree()

        # get rid of old Readers attribute
        if hasattr(self, '_BlogItem__readers'):
            del self.__readers
        
        self.version_upgrade_done()        
        
    def upgradeToVersion2(self):
        # do self.parent_blogitem 2005-03-17
        self.parent_blogitem = None        
        comments = HasComments.get_all_comments(self)
        for item in comments:
            item.parent_blogitem = self # point comments to point to itself
             
        self.version_upgrade_done()        
                
    def upgradeToVersion1(self):
    
        # compress text
        self.__summary = CompressedText(self.summary)
        self.__main = CompressedText(self.main)
        del self.summary
        del self.main
        
        # create cache
        self.__cached_html_summary = PersistentCache(self._update_html_cache)
        
        self.version_upgrade_done()
            
    def is_deleted(self, use_attr=False):
        if use_attr or not self.parent_blogitem:
            return self.__deleted

        return self.parent_blogitem.get_comment_flags(self)

    def set_deleted(self, val):
        self.__deleted = bool(val)

        # cache/copy deleted attribute into paren't comment_flags
        # for fast lookup to avoid db reading each comment
        if self.parent_blogitem:
            self.parent_blogitem.set_comment_flags(self, bool(val))

        # alex added so that recent items cache for parent blog gets marked as dirty
        self.watchable_changed()        

    def set_deleted_note(self, note):
        self._deleted_note = note

    def get_deleted_note(self):
        return getattr(self, '_deleted_note', None)

    def can_read(self, user):
        return self.blog.ihb.can_read(user)
    
    def can_edit(self, user):
        return (self.author is user) or self.can_manage(user)
    
    def can_delete(self, user):
        """Return True if user can delete this item."""
        
        # managers can always delete
        if self.can_manage(user):
            return True
            
        # authors can only delete if there are no undeleted comments
        if self.num_comments() == 0:
            return self.author is user
        
        return False
    
    def can_manage(self, user):
        """Return True if user can manage this item (usually a group owner)."""
        return self.blog.ihb and self.blog.ihb.can_manage(user)
        
    def can_show(self):
        """Return False if this item should be suppressed due to feedback score."""
        if self.get_karma_score() < qon.karma.min_karma_to_show:
            return False
        
        if self.author.get_karma_score() < qon.karma.min_author_karma:
            return False
        
        return True

    def why_cant_show(self):
        """Only really useful when can_show()==False.  Returns the reason for an item
        not being shown.  Return value is ('item' | 'user', fbscore)"""
        if self.get_karma_score() < qon.karma.min_karma_to_show:
            return ('item', self.get_karma_score())

        if self.author.get_karma_score() < qon.karma.min_author_karma:
            return ('user', self.author.get_karma_score())

        return ()
                            
    def last_modified(self, consider_comments=True):
        if consider_comments:
            # this Watchable changes whenever a comment is added
            dt = self.watchable_last_change()
            if dt is never:
                dt = self.modified or self.date
            return dt
        else:
            return self.modified or self.date
        
    def new_comment(self, author, title, summary, main=''):
        """Create a new comment item and return it."""
        comment = BlogItem(blog=self.blog,
            author=author,
            title=title,
            summary=summary,
            main=main,
            dont_watch=1)
        
        # Check to see if this new comment is a duplicate
        #  of the previous comment.  If so, ignore it, since
        #  it's probably unintended, and just return None.
        if HasComments.is_duplicate(self, comment):
            comment = None
        else:            
            self.add_comment(comment)

            # avoid 'bogus new to me'
            comment.read_item(author, datetime.utcnow())

            author.karma_activity_credit()
        return comment
        
    def notify_karma_changed(self):
        """Called by HasKarma.add_karma."""
        
        # also delegate to watchable_changed
        # self.watchable_changed() # removed by alex to keep blogitems from boldfacing when left feedback
        
        if self.blog and hasattr(self.blog, 'notify_karma_changed'):
            self.blog.notify_karma_changed()

    def add_comment(self, comment):
        comment.parent_blogitem = self        
        HasComments.add_comment(self, comment)
        self.watchable_changed(comment.date)
    
    def watchable_name(self):
        return self.title
    
    def watchable_changed(self, now=None):
        # tells blog he has changed, too
        Watchable.watchable_changed(self, now)
        if self.blog:
            self.blog.watchable_changed(now)

    def watchable_modified_date(self):
        return self.last_modified()

    def can_get_karma_from(self, other):
        return other is not self.author
        
    def get_summary(self):
        return self.__summary.get_raw()
        
    def set_summary(self, raw):
        self._log_summary_change()
        self.__summary.set_raw(raw)
        self.invalidate_html_cache()
        
    def get_main(self):
        if not self.__main:
            return ''
        return self.__main.get_raw()
        
    def set_main(self, raw):
        if not self.__main:
            self.__main = CompressedText()
        self.__main.set_raw(raw)
    
    def _log_summary_change(self):
        import qon.log
        if hasattr(self.blog.ihb, 'get_user_id'):
            qon.log.edit_info('SetSummary\t%s\n%s' % (self.blog.ihb.get_user_id(), self.get_summary()))
        else:
            qon.log.edit_info('SetSummary2\t%s\n%s' % (self.blog.ihb.get_name(), self.get_summary()))

    # HTML cache methods
        
    def add_html_dependency(self, target):
        """Adds target as something self depends on for its HTML cache."""
        self.__cached_html_summary.add_dependency(target)

    def invalidate_html_cache(self):
        self.__cached_html_summary.flush()
        
    def get_cached_html(self):
        return self.__cached_html_summary.get().get_raw()

    def _update_html_cache(self):
        from qon.ui.blocks.wiki import rst_to_html
        return CompressedText(str(rst_to_html(self.get_summary(),
            wiki=self.blog.ihb.get_wiki(),
            container=self)))

    def disable_cache(self):
        self.__cached_html_summary.disable_cache()

    def cache_disabled(self):
        return self.__cached_html_summary.cache_disabled()
    
    def read_item(self, user, now=None):
        """Notice that user has accessed this item.
        
        If we are a comment, we pass this on to our parent item, to
        catch up based on comment's submission date.
        """

        if not hasattr(self, "_BlogItem__user_access"):

            # we don't keep track of user access -- we're a comment,
            # so just pass this on to our parent.
            if self.parent_blogitem:
                return self.parent_blogitem.read_item(user, self.date)
            return
        
        if not user:
            return
            
        now = now or datetime.utcnow()
        user_oid = unpack_oid(user._p_oid)
        
        dt, count = self.__user_access.get(user_oid, (never, 0))
        now = max(now, dt)
        
        # increment hit count
        self.__user_access[user_oid] = (now, count + 1)

    def has_read_item(self, user, updated=None):
        if not hasattr(self, "_BlogItem__user_access"):
            return False
        
        if not user:
            return True
        
        dt, count = self._get_user_access(user)
        if count == 0:
            return False
        
        if updated:
            return dt >= updated
        else:
            return True
    
    def last_read(self, user):
        """Return datetime when user last read this item."""
        dt, count = self._get_user_access(user)
        return dt
    
    def _get_user_access(self, user):
        if not hasattr(self, "_BlogItem__user_access"):
            return (never, 0)
            
        user_oid = unpack_oid(user._p_oid)
        return self.__user_access.get(user_oid, (never, 0))
    
    def item_views(self):
        """Returns (number of views, number of readers).""" 
        
        views = 0
        readers = 0
        for user_oid, (dt, count) in self.__user_access.iteritems():
            if count > 0:   # alex added if on 2006-10-09
                readers += 1
                views += count
        
        return (views, readers)
 
    def get_pageview_counts_per_user(self):
        """return a list of (user, counts)"""
        return_list = []
        for user_oid, (dt, count) in self.__user_access.iteritems():
            if count > 0:
                return_list.append((get_oid(pack_oid(user_oid)), count))
        return return_list
            
    def get_title(self):
        # this is here and in WikiPage
        return self.title
        
class IHasBlog:
    """Abstract class defining required interface for any class which contains a blog.
    
    Be sure to refer to this class behind of any other base classes that override
    these methods; usually at the end (right-most) position in list of subclasses.
    """
    
    def can_manage(self, user):
        "can user manage the blog?"""
        raise NotImplementedError

    def can_edit(self, user):
        "Can user edit/write the blog?"""
        raise NotImplementedError

    def can_read(self, user):
        "can user read/comment the blog?"""
        raise NotImplementedError

    def is_accepted(self):
        """Am I 'active'?"""
        raise NotImplementedError
        
    def get_owners(self):
        """Who are my owners? Returns a list."""
        raise NotImplementedError
    
    def is_owner(self, user):
        """Is user one of my owners?"""
        raise NotImplementedError
        
    def get_blog(self):
        """Who is my blog?"""
        raise NotImplementedError
        
    def get_wiki(self):
        """Who is my wiki?"""
        raise NotImplementedError
        
    def get_name(self):
        """What is my name?"""
        raise NotImplementedError
    
    def get_all_owners(self):
        """Who are all my owners, including any enclosed member groups?
        
        Returns a list.
        """
        raise NotImplementedError

    def get_all_blogs(self):
        """Who are all my blogs, including any enclosed member groups?
        
        Returns a list.
        """
        raise NotImplementedError
        
    def get_member_list(self):
        """Who are all of my members? Returns a list. """
        raise NotImplementedError

    # optional notifications
    
    def notify_new_item(self, item):
        """Notice that a new item was created."""
        pass
        
    # optional customization
    
    def can_create_item(self):
        """Return False if users should not be allowed to create new topics."""
        return True
    
    def can_delete_item(self, item):
        """Return False if item can't be deleted."""
        return True
    
    # The following methods are optional and are here based on dependance
    # on other modules.
    
    def rollup_member_groups(self):
        """Should my UI display member groups (subgroups)?"""
        return False
        
    def notify_karma_changed(self):
        """Notice that something I depend on has changed its karma."""
        pass
        
    def watchable_changed(self, now=None):
        """Notice that something I depend on has changed. Normally defined
        by Watchable mixin."""
        pass
        
    def blog_name(self):
        """Return a name suitable for display to user. I probably don't
        need to implement this if my Blog isn't Watchable.
        """
        pass


# --------------------------------------------------------------
# One-time upgrades
#
# Upgrades that don't require a bump in persitenceVersion; these
# are probably called from the command-line
# --------------------------------------------------------------

def check_items():
    """Check that all reachable BlogItems have their parent_blogitem field
    correctly set."""

    from base import get_group_database, get_user_database

    def check_item():
        """Check if item is properly in its blog's item list."""
        try:
            index = item.blog.item_index(item)
        except ValueError:
            print "ERROR: item /group/%s/%s not found in blog." % (
                item.blog.ihb.get_user_id(),
                item)

    def check_comments():
        comment_count = 0
        for comment in item.get_all_comments():
            if comment.parent_blogitem is not item:
                print "ERROR: /group/%s/%d/%d/ has invalid parent_blogitem." \
                    % (group_id, item_count, comment_count)
            comment_count += 1
    
    count = 0
    item_count = 0
    for group_id, group in get_group_database().root.iteritems():
        for item in group.get_blog().get_items():
            item_count += 1
            check_item()
            check_comments()
        
        for page_name, page in group.get_wiki().pages.iteritems():
            for item in page.blog.get_items():
                item_count += 1
                check_item()
                check_comments()
        
        count += 1
        print "Checked %d groups, %d items, %s" % (count, item_count, group_id)
        
    
    count = 0
    item_count = 0
    for user_id, user in get_user_database().root.iteritems():
        for item in user.get_blog().get_items():
            item_count += 1
            check_item()
            check_comments()

        if count % 500 == 0:
            print "Checked %d users, %d items" % (count, item_count)
        count += 1

    print "Checked %d users, %d items" % (count, item_count)
        
def upgrade_visit_all_blogs():
    from base import get_group_database, get_user_database, commit_upgraded_versioneds
    
    count = 0
    item_count = 0
    for group_id, group in get_group_database().root.iteritems():
        for item in group.get_blog().get_items():
            item_count += 1
        
        for page_name, page in group.get_wiki().pages.iteritems():
            for item in page.blog.get_items():
                item_count += 1
        
        count += 1
        commit_upgraded_versioneds()
        print "Touched %d groups, %d items, %s" % (count, item_count, group_id)
        
    
    count = 0
    item_count = 0
    for user_id, user in get_user_database().root.iteritems():
        for item in user.get_blog().get_items():
            item_count += 1

        if count % 500 == 0:
            print "Touched %d users, %d items" % (count, item_count)
            commit_upgraded_versioneds()
        count += 1

    commit_upgraded_versioneds()
        
    

def upgrade_blog_raw_text_format():
    """Compress all blog item text fields."""
    from base import get_group_database
    import transaction
    group_db = get_group_database()
    for g in group_db.root.values():
        for bi in g.blog.get_items():
            if not hasattr(bi, '_BlogItem__summary'):
                bi.set_summary(bi.get_summary())
                bi._p_changed = 1
        transaction.commit(True)
