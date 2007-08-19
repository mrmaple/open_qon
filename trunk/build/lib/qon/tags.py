"""
$Id: tags.py,v 1.15 2007/06/20 16:20:50 jimc Exp $
Author: Jimc

The first phase is loosely modeled on del.icio.us.  When a tag is applied, it
is tracked globally, and in the content's group, as well as in the user's 
personal tags.

Community-refined goals:

Tags will help people use omidyar.net to:
=========================================

The goals of tagging are to help people use omidyar.net to: 

**1.  re-find content once they stumble upon it the first time by whatever 
    means (a la del.icio.us)** 
    
    A.  enables members to track content they find valuable and want to refer 
    back to 
    
**2.  point to content that others haven't yet seen (like Flickr)** in a 
    way that: 
    
    A.  enables members to synthesize content and make the site more organized 
    
    B.  allows members to indicate their own interests (to make it easy for 
    others to find them through those interests) 
    
**3.  find content they haven't yet seen (another user-created way to 
    traverse the user-created content on omidyar.net)** in a way that: 
    
    A.  enables new members to reach comfort level quickly and encourages 
    mentoring 
    
    B.  enables people to find, discuss with, and collaborate with others who 
    share their interests 
    
    C. facilitates the exchange of resources and services
    
    D. encourages action to make good things happen

**4. track content in between visits to omidyar.net**
    
    A.  enables members to track content on omidyar.net without having to sign 
    on to the community by watching certain tag lists 
    
    B.  enables members to subscribe to tags of interests to watch how others 
    apply the tags 
    
"""

import re, sha, time, random, binascii
from datetime import datetime, timedelta
from dulcinea.typeutils import typecheck, typecheck_seq

from BTrees import IOBTree, OOBTree
from dulcinea.database import unpack_oid, pack_oid
from persistent.list import PersistentList
#from persistent.mapping import PersistentMapping
from qon.base import QonPersistent, get_database, get_group_database, get_tags_database, get_user_database, get_tagged_item_database
from qon.karma import HasKarma

# when this is first introduced to the community, we'll
# only allow tagging in certain groups
_groups_with_tagging = ["tagging_sandbox"] #, "sitedev", "community-general", "sd"]

def group_can_tag (group_short_name):
    # only allow tagging in non-private groups
    can_tag = not get_group_database()[str(group_short_name)].is_private()
    return can_tag

def standardize_tags (tags):
    """ given a list of tags, or tags in a single string,
    returns a standardized list of the
    tags in the same order. returns [tag, tag...]

    underscores are changed to dashes
    commas and slashes are treated as whitespace
    tags become lower case
    """
    std_tags = []

    if type(tags) != list:
        tags = tags.split()
    #

    # changed to spaces
    whitespace_chars = ","
    # changed to dashes
    joining_chars = "_/"
    #tag_blacklist = ['shit', 'piss', 'fuck', 'cunt', 'cocksucker', 'tits', 'motherfucker']
    # no blacklists or censorship of any kind.

    filtered_tags = []
    for tag in tags:
        tag = tag.lower()

        #if tag in tag_blacklist:
        #    continue

        for ws_char in whitespace_chars:
            tag = tag.replace(ws_char, " ").strip()
        for join_char in joining_chars:
            tag = tag.replace(join_char, "-")

        filtered_tags.extend(tag.split())
    #

    # in the last pass, restrict the length
    # if we did this earlier, then comma-separated tags would get truncated
    for tag in filtered_tags:
        # restrict the length
        std_tags.append(tag[:32])

    # now that they're all homogenous, we have to filter out duplicates
    final_tags = []
    for tag in std_tags:
        if tag not in final_tags:
            final_tags.append(tag)

    return final_tags
#

class TagAttributes(QonPersistent):
    """ The attributes for one set of tags for one item by one person.
    """
    def __init__ (self, tags, comment = None):
        self.tags = tags
        self.comment = comment

        # creation date 
        self.date_added = self.date_modified = datetime.utcnow()

        # who else can see this tag?
        # if the array is empty, then everyone can see the tag.
        # Otherwise the user has to be a member of at least 
        # one group in the list. for example, ['sitedev']
    #

    def add_tags (self, tags):
        for tag in tags:
            self.add_tag(tag)
        self._p_changed = 1
    #
    def remove_tags (self, tags):
        for tag in tags:
            self.remove_tag(tag)
        self._p_changed = 1
    #
    def add_tag (self, tag):
        if tag not in self.tags:
            self.tags.append(tag)
            self._p_changed = True
            self.date_modified = datetime.utcnow()
    #
    def remove_tag (self, tag):
        if tag in self.tags:
            self.tags.remove(tag)
            self._p_changed = True
            self.date_modified = datetime.utcnow()
    #
#

class HasTags: 
    """This is the tag container. The main tags_db has global tags, people
    have tags (the ones they apply) and every group also Has Tags.

    Anything that needs to track its own tag cloud extends HasTags

    It answers the following:
      - What Taggable objects have the tag 'tag'
      - Who has used tag 'tag'
      - What are the most common tags, and how many has each been used
      - What's the most tagged item, and how many times has it been tagged

    This GenericDB has a root, OOBTree
      self['tag'] : {item._p_oid : { user_id: TagAttributes() }}

    With dictionaries, this would look like:
    >>> tags = {"education": {"item32": {"user 29": "we don't need no"}}}
    >>> tags['education']['item 31'] = {'user 49' : 'highly academic'}
    >>> tags
    {'education': {'item32': {'user 29': "we don't need no"}, 'item 31': {'jimc': 'highly academic'}}}
    >>> 
    >>> tags['education'].keys()
    ['item32', 'item 31']

    """
    #persistenceVersion = 0

    def __init__ (self):
        """ a list of tags, and the number of times they are applied.
        Sorted by the #, for quick checks to see if a new tag belongs
        on the list. (tag_count, tag), number first, least popular first
        for easy sorting. """
        self.tags = OOBTree.OOBTree()
    #

    def tag_item (self, user_id, item_oid, tags, comment):
        """ Add tags for this user, item pair to this container. """
        new_tag_attributes = TagAttributes(tags, comment)

        for tag in tags:
            if not self.tags.has_key(tag):
                self.tags[tag] = OOBTree.OOBTree()

            if not self.tags[tag].has_key(item_oid):
                self.tags[tag][item_oid] = OOBTree.OOBTree()

            self.tags[tag][item_oid][user_id] = new_tag_attributes
        #
    # 

    def get_tagged_items (self, tags):
        """ Get all the items tagged with all of the specified tags.
        """
        if type(tags) is not list:
            tags = [tags]

        all_items = []
        for tag in tags:
            if tag in self.tags:
                if not all_items:
                    all_items = self.tags[tag].keys()
                else:
                    # set intersection
                    all_items = [item for item in all_items if item in self.tags[tag].keys()]
                #
            #
        # 
        return all_items
    #
 
    def get_tags(self):
        """ Get all the tags for this container, unsorted.
        """
        return self.tags.keys()
    #

    def get_tags_n_counts(self, limit=80):
        """ Suitable for a tag cloud, returns [ (tag, count), ...] 
        sorted alphabetically by tag.

        count is the number of people who have used the tag.
        """
        if limit == 0:
            return []

        tags_db = get_tags_database();
  
        counts_n_tags = []
        for tag, items in self.tags.iteritems():
            items_tagged = len(items)
            unique_users = {}
            for item, users in items.iteritems():
                for user_id in users:
                    if not tags_db.is_tagger_naughty(user_id):
                        unique_users[user_id] = 1
            if unique_users:
                counts_n_tags.append( (len(unique_users), items_tagged, tag) )

        # number of items would look like
        #counts_n_tags = [(len(items.keys()), tag) for (tag, items) in self.tags.iteritems()]

        counts_n_tags.sort()
        # now the popular tags are at the end of counts_n_tags
        tags_n_counts = [ (tag, count)for count, items_tagged, tag in counts_n_tags[-limit:] ]
        tags_n_counts.sort()
        # now we have the most popular, alphabetically
        return tags_n_counts
    #

    def get_related_tags_n_counts (self, current_tags, limit=100):
        """ consider items tagged with all of the current tags, 
        and return the tags that also tag that small set.

        The counts returned reflect how many items share that additional 
        tag. (Not number of people style popularity.)
        """
        results = []
        tidb = get_tagged_item_database()

        items_intersection = None
        for tag in current_tags:
            # get the items tagged with this tag
            items = self.get_tagged_items(tag)

            if not items_intersection:
                # start with _only_ tags that are applied by nice taggers
                items_intersection = [item for item in items if tidb.get_item_popularity(item, tag) > 0 ]
            else:
                # iterate over the shrinking intersection to save time
                items_intersection = [item for item in items_intersection if item in items]
            #
        #

        # {tag: count} where count is how many times the tag shows up
        # looking through the item's tags
        related_tags = {}
        for item_oid in items_intersection:
            for tag in tidb.get_tags(item_oid):
                if tag not in current_tags:
                    related_tags[tag] = related_tags.get(tag, 0) + 1
        #

        counts_n_tags = [(ct,tag) for tag, ct in related_tags.iteritems()]

        counts_n_tags.sort()
        # now the popular tags are at the end of counts_n_tags
        tags_n_counts = [ (tag, count)for count, tag in counts_n_tags[-limit:] ]
        tags_n_counts.sort()
        # now we have the most popular, alphabetically
        return tags_n_counts
    #
    
    def remove_tags (self, tags, item_oid, user_id):
        original_tags = {}

        for tag in tags:
            for otag in self.tags[tag][item_oid][user_id].tags:
                original_tags[otag] = 1

            # we always want to remove the user from the tag/item pair
            # since this user no longer has this tag for this item
            del self.tags[tag][item_oid][user_id]
    
            # if no users, remove the item
            if len(self.tags[tag][item_oid]) == 0:
                del self.tags[tag][item_oid]
    
            # if no items, remove the tag from the tags
            if len(self.tags[tag]) == 0:
                del self.tags[tag]
            #
        #
        # 
        tags_to_update = [tag for tag in original_tags.keys() if tag not in tags]
        for update_tag in tags_to_update:
            for tag in tags:
                self.tags[update_tag][item_oid][user_id].remove_tag(tag)
    #
    
    def get_recently_tagged (self, tags, limit=25):
        """ Find the items for the specified tags, and pair them with the most recent
        date that any of the tags were applied, and the user that applied that tag.
        [(date, item, user), ...]
        """
        if type(tags) is not list:
            tags = [tags]

        # for each item, store the most recent date
        item_date = {}
        item_user = {}

        for tag in tags:
            if tag in self.tags:
                if not item_date:
                    for item, users in self.tags[tag].iteritems():
                        for user, ta in users.iteritems():
                            if not item in item_date:
                                item_date[item] = ta.date_modified
                                item_user[item] = user
                            else:
                                if ta.date_modified > item_date[item]:
                                    item_date[item] = ta.date_modified
                                    item_user[item] = user
                                #
                            #
                        #
                    #
                else:
                    # remove the entries that don't share the remaining tags
                    for item in item_date.keys():
                        if item not in self.tags[tag]:
                            del item_date[item]
                            del item_user[item]
                    #
                #
            #
        # 
        dates_n_items = [(date, item, item_user[item]) for item, date in item_date.iteritems()]
        dates_n_items.sort()
        dates_n_items = dates_n_items[-limit:]
        dates_n_items.reverse()
        return dates_n_items
    #
#

# 
# format an atem feed for recent tags
def format_atom_tags_feed (tags):
    """Return an Atom Feed for this tag."""

    if type(tags) is list:
        tag = ",".join(tags)
    else:
        tag = tags

    # get the most recent items for this tag
    tags_db = get_tags_database()
    dates_n_items = tags_db.get_items_and_dates(tags)
    dates_n_items.sort()
    dates_n_items = dates_n_items[:-25]
    dates_n_items.reverse()
    most_recent = dates_n_items[0][0]

    feed = qon.atom.Feed()
    feed.title = "Most recent items tagged with %s" % tag
    feed.url = qon.ui.blocks.util.full_url('/home/tags/%s' % tag)
    feed.set_modified(most_recent)
    try2 = """
    # for each item, use ui blocks to format the entries
    for date, item_oid in dates_n_items:
        item = get_oid(item_oid)

        if type(item) is qon.wiki.Wiki:
            # which page is this? most recent?
            wiki_entry = blocks.wiki.format_atom_page(0)
            feed.entries.append(wiki_entry)
        elif type(item) is qon.user.User:
            user_entry = blocks.blog.format_atom_item(item)
            feed.entries.append(user_entry)
        elif type(item) is qon.blog.Blog:
            comment_entry = blocks.blog.format_atom_item(item)
            #blog_entry = blocks.blog.format_atom_item(item)
            feed.entries.append(comment_entry)
    """
    # fill the feed up with items?
    try1 = """
    for date, item in dats_n_items:
        #entry = _create_page_entry(page, add_group_title)
        path_to_item = qon.ui.blocks.util.full_url('/home/tags/%s' % tag)
        entry = qon.atom.Entry(path_to_item)
        entry.title = xml_escape("title here")
        entry.url = path_to_item
        entry.feed = path_to_item + 'atom.xml'
        entry_feed_title = "" #
        entry.id = qon.ui.blocks.util.atom_id(item)
        entry.set_modified(date)
        entry.set_issued(date)
        entry.set_created(item.date)
        author = qon.atom.Person(xml_escape(item.author.display_name()))
        author.url = qon.ui.blocks.util.full_url(qon.ui.blocks.user.path_to_user(item.author))
        entry.author = author

        entry.content = xml_escape(page.get_cached_html2())

        feed.entries.append(entry)
    """
    return feed

class TaggerKarma(HasKarma):
    """ Because a Tagger is a user, and a user already ISA HasKarma object,
    we can't just mix it in.  We have to compose a new object, and that 
    object still has to know what the user id is, so it knows when to hide
    the feedback giving capability, so people don't give themselves tagging
    feedback."""
    def __init__ (self, tagger_id):
        self.tagger_id = tagger_id
        HasKarma.__init__(self)

    def can_get_karma_from(self, other):
        return other != self.tagger_id
    #
# 
tagger_naughty_threshold = -10

class Tagger:
    """ One which applies tags. A user is a Tagger. 
    When the user is active, this will be used for the personal
    tag cloud, and its results.

    self.tags[tag] : [item_oid, item_oid,...]

    For each tag, we know how many times they've applied it by the length
    of the item list.
    """
    def __init__ (self):
        self.tags = OOBTree.OOBTree()
        self.tag_karma = TaggerKarma(self.get_tagger_id())

    def tagger_upgradeToVersion1 (self):
        # karma is a new addition
        self.tag_karma = TaggerKarma(self.get_tagger_id())

    def get_tagger_id (self):
        raise UnimplementedException("you need to implement your get_tagger_id()")

    def tag_item (self, tags, item_oid):

        for tag in tags:
            if not self.tags.has_key(tag):
                self.tags[tag] = [item_oid]
            else:
                if item_oid not in self.tags[tag]:
                    self.tags[tag].append(item_oid)
                    self.tags._p_changed = 1
                    self._p_changed = 1
                #
            #
        # 
    #      

    def get_tagged_items (self, tag = None):
        """returns a list of item_oid for each item that has been tagged with the given tag."""
        if tag:
            #return self.tags[tag].keys()
            return self.tags[tag]
        else:
            all_items = []
            for tag, items in self.tags.iteritems():
                for item in items:
                    if item not in all_items:
                        all_items.append(item)
                    #
                # 
            return all_items
        #
    #

    def remove_tags (self, tags, item):
        for tag in tags:
            self.tags[tag].remove(item)
            self.tags._p_changed = True

            if len(self.tags[tag]) == 0:
                del self.tags[tag]
            #
        #
    #

    #def get_tagged_items (self, tag):
    #    return self.tags[tag]
    #

    def get_tagged_items_tags (self, current_tags):
        """ consider items tagged with all of the current tags, 
        and return the tags that also tag that small set."""
        results = []
        tidb = get_tagged_item_db()

        items_intersection = None
        for tag in current_tags:
            # get the items tagged with this tag
            items = self.tags[tag]

            if items_intersection:
                # iterate over the shrinking intersection to save time
                items_intersection = [item for item in items_intersection if item in items]
            else:
                items_intersection = items
            #
        #
        for item_oid in items_intersection:
            # get the tags that have been applied to those items
            tags = tidb.get_tags(item_oid)
            results.extend( [t for t,count in tags] )
        #
        return results
    #
    # 
    def get_tags_n_counts (self, current_tags = None):
        return self.get_tag_cloud(current_tags)
     
    def get_tag_cloud (self, current_tags = None):
        """ returns an on-ordered array of tags, and counts for each tag. 
        [(tag, count), (tag, count)...]"""
        results = []

        # if they've specified current_tags, then we only consider 
        # tags that also tag items tagged with the current tags
        subtags = None
        if current_tags:
            subtags = get_tagged_items_tags(current_tags)

        for tag, item_list in self.tags.iteritems():
            if not subtags or tag in subtags:
                results.append( (tag, len(item_list)) )
            
        return results
    #
# 


