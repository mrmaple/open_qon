"""
$Id: tags_db.py,v 1.10 2007/06/27 16:31:31 jimc Exp $
Author: Jimc

Tags db is the root of all tagging data.

"""
from datetime import datetime, timedelta
from qon.base import QonPersistent

#from persistent.list import PersistentList
from BTrees import IOBTree, OOBTree
from dulcinea.database import unpack_oid, pack_oid
from qon.user_db import GenericDB

#from qon.database import ConflictAvoidingOOBTree
from qon.user import HasOwnership, HasUserID
from qon.util import get_oid, distance_lat_long_fast
from qon.base import transaction_commit, transaction_abort
from qon.base import QonPersistent, get_database, get_tags_database, get_tagged_item_database, get_user_database, get_group_database

from qon.tags import HasTags, TagAttributes

def initialize_tagging ():
    """this adds tagging capabilities to the database.  It is meant as documentation
    and should only need to be run once for a database.
    opendb qon
    >>> db.root.tags_db = qon.TagsDB() 
    """
    if not get_database().root.has_key('tags_db'):
        get_database().init_root('tags_db', 'qon.tags_db', 'TagsDB')
    if not get_database().root.has_key('tagged_item_db'):
        get_database().init_root('tagged_item_db', 'qon.tags_db', 'TaggedItemDB')
#

def delete_all_tags (i_am_sure=False):
    if not i_am_sure:
        return

    # globally
    del get_tags_database().tags
    get_tags_database().tags = OOBTree.OOBTree()

    # global reverse mapping
    del get_tagged_item_database().root
    get_tagged_item_database().root = OOBTree.OOBTree()

    # for each group, ensure tags are empty
    for group_id, group in get_group_database().root.iteritems():
        del group.tags
        group.tags = OOBTree.OOBTree()
    #

    for user_id, user in get_user_database().root.iteritems():
        if hasattr(user, 'tags'):
            if len(user.tags) > 0:
                del user.tags
                user.tags = OOBTree.OOBTree()
    #
    get_transaction().commit()
#

#import itertools
def unique_word_counts(words):
    """ given a list of words containing duplicates,
    this returns a list of unique words, and the number
    of occurances for each. 
    returns [ (word, count), ... ]
    """
    # python 2.4 has groupby... lucky bastards
    #word_counts = []
    #for k, group in itertools.groupby(words):
    #    word_counts.append( (k, len(list(group))) )
    #return word_counts

    word_counts = {}
    for word in words:
        word_counts[word] = word_counts.get(word, 0) + 1
    return [ (word, count) for word, count in word_counts.iteritems()]
#

class TaggedItemDB(GenericDB):
    """
    This provides a reverse tag mapping, so for an item, we can 
    ask who has tagged it, with which tags.

    There's only one globlal reverse mapping, groups don't need
    to have their own.

    "the item's tree of users" - Pierre

    self [item._p_oid]: { user_id: TagAttributes }}

    """
    def __init__(self):
        GenericDB.__init__(self)

    def add_item (self, item_oid, user_id, tag_attributes):
        """ add a reverse mapping from an object to each 
        user that's tagged it, and their tag attributes.
        """
        assert isinstance(tag_attributes, TagAttributes)
        if not self.has_key(item_oid): 
            self[item_oid] = OOBTree.OOBTree()
        self[item_oid][user_id] = tag_attributes
    #

    def remove_item_user (self, item_oid, user_id):
        del self[item_oid][user_id]

        if len(self[item_oid]) == 0:
            del self[item_oid]
        #
    #

    def get_tags (self, item_oid, user_id = None):
        """ given an item, return all the tags, and the number 
        of times that tag was applied. 
        returns [tag, tag,... ] 
        """
        tags = {}

        if self.has_key(item_oid):
            if user_id:
                if self[item_oid].has_key(user_id):
                    for tag in self[item_oid][user_id].tags:
                        tags[tag] = 1
            else:
                # for all users
                tags_db = get_tags_database()
                for user_id, attribs in self[item_oid].iteritems():
                    if not tags_db.is_tagger_naughty(user_id):
                        for tag in attribs.tags:
                            tags[tag] = 1
                # 
            # 
        # 
        return tags.keys()
    #
    
    def get_tags_n_counts (self, item_oid, user_id = None):
        """ given an item, return all the tags, and the number 
        of times that tag was applied. 
        returns [ (tag, count),... ] 
        """
        tags = []
        all_tags = []

        tags_db = get_tags_database()

        if self.has_key(item_oid):
            if user_id:
                if self[item_oid].has_key(user_id):
                    tags.extend(self[item_oid][user_id].tags)
            else:
                # for all users (except the naughty taggers)
                for user_id, attribs in self[item_oid].iteritems():
                    if not tags_db.is_tagger_naughty(user_id):
                        tags.extend(attribs.tags)

            # [ (tag, count),... ]
            tags = unique_word_counts(tags)

        return tags
    #

    def get_tag_attributes (self, item_oid, user_id):
        if self.has_key(item_oid) and self[item_oid].has_key(user_id):
            return self[item_oid][user_id]
        else:
            # a null TagAttributes (think null object pattern)
            return TagAttributes([])
        #
    #

    def get_item_popularity(self, item_oid, specific_tags=None):
        """More popular items are tagged by more people.
        returns: number of people who have tagged this item."""
        if not self.has_key(item_oid):
            return 0
        tags_db = get_tags_database()
        if specific_tags:
            if type(specific_tags) != list:
                specific_tags = [specific_tags]
            count = 0
            for user_id, attributes in self[item_oid].iteritems():
                if not tags_db.is_tagger_naughty(user_id):
                    common_tags = [tag for tag in specific_tags if tag in attributes.tags]
                    if common_tags:
                        count += 1
                    #
                #
            #
            return count
        else:
            if self.has_key(item_oid):
                return len(self[item_oid].keys())
            else:
                return 0
        #
    #

    def get_item_taggers (self, item_oid, specific_tags=None):
        tags_db = get_tags_database()
        if specific_tags:
            if type(specific_tags) != list:
                specific_tags = [specific_tags]
            taggers = []
            for user_id, attributes in self[item_oid].iteritems():
                common_tags = [tag for tag in specific_tags if tag in attributes.tags]
                if common_tags and not tags_db.is_tagger_naughty(user_id):
                    taggers.append(user_id)
                #
            #
            return taggers
        else:
            if self.has_key(item_oid):
                return self[item_oid].keys()
            else:
                return []
        #
    #
#

class TagsDB(HasTags, QonPersistent):
    """
    This is the global tags 'root' in ZODB

    It answers the following:
      - What Taggable objects have the tag 'tag'
      - Who has used tag 'tag'
      - What are the most common tags, and how many has each been used
      - What's the most tagged item, and how many times has it been tagged

    This GenericDB has a root, OOBTree
      self['tag'] : {item._p_oid : { user_id: TagAttributes() }}

    """
    persistenceVersion = 1

    def __init__ (self):
        HasTags.__init__(self)

        # dictionary of user_ids for taggers that 
        # have so much negative tag feedback that we want
        # to hide their tags from the public.
        self.naughty_taggers = {}
    #

    def upgradeToVersion1 (self):
        self.naughty_taggers = {}
    #

    def set_tagger_naughty (self, user_id):
        if not user_id in self.naughty_taggers:
            self.naughty_taggers[user_id] = 1
            self._p_changed = 1
        #
    #

    def set_tagger_nice (self, user_id):
        if user_id in self.naughty_taggers:
            del self.naughty_taggers[user_id]
            self._p_changed = 1
        #
    #

    def is_tagger_naughty (self, user_id):
        return user_id in self.naughty_taggers
    #

    def tag_item (self, user_id, item_oid, tags, comment):
        if not tags:
            return

        # update this tag container to hold these tags for this item
        HasTags.tag_item(self, user_id, item_oid, tags, comment)

        # update the reverse mapping with the new tag attributes
        # for any tag, get the new attributes object
        new_attributes = self.tags[tags[0]][item_oid][user_id]
        tidb = get_tagged_item_database()
        tidb.add_item(item_oid, user_id, new_attributes) 
    # 

    def remove_tags (self, tags, item_oid, user_id):
        if not tags:
            return

        tidb = get_tagged_item_database()

        # what tags does this item,user have before removal?
        item_tags = tidb.get_tags(item_oid, user_id)

        HasTags.remove_tags(self, tags, item_oid, user_id)

        remaining_tags = [tag for tag in item_tags if tag not in tags]
        if remaining_tags:
            atag = remaining_tags[0] # an arbitrary tag
            if 1: #atag in self.tags and item_oid in self.tags[atag] and user_id in self.tags[atag][item_oid]:
                new_attributes = self.tags[atag][item_oid][user_id]
                tidb.add_item(item_oid, user_id, new_attributes)
        else:
            # if all attributes are gone, remove this item,user from the tidb
            tidb.remove_item_user(item_oid, user_id)
        #
    #
#


