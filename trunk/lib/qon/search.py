"""
$Id: search.py,v 1.32 2007/06/11 15:40:22 jimc Exp $

Search routines that provide the api for search.
Specify the particular engine you want to use at the bottom of this file.
"""
import qon.group # for qon.group.Group
import qon.user # for qon.user.User
import qon.blog # for qon.blog.BlogItem
import qon.wiki # for qon.wiki.WikiPage

import ui.blocks.util  # for path_to_obj
import ui.blocks.blog  # for path_to_comment

import qon.base # for get_group_database, get_user_database
from qon.base import get_tagged_item_database
import string   # for maketrans and translate
import re       # for compile
from datetime import datetime, timedelta
from qon.watch import never
import base64

# regular expression pattern for matching:
#  1) a long (>=3) string of - characters
#  2) rst directives of the form ".. xxxxx::"
#  3) ::
#  4) all _ or ` or |
#  5) a string of 2 or more *, +, =, ~characters
#  6) :xxxx: xxx\n
# used for beautifying preview text
uglystuff = re.compile('[*+=~]{2,}|[-]{3,}|\.\. .+?(\Z|\n)|__ .+?(\Z|\n)|:\w+: \w+(\Z|\n)|::|[_`\|]+')

class SearchEngine:
    """
    Abstract class for handling searching and indexing of qon documents.
    Subclasses (e.g. SearchLupy and SearchLucene) must override:
      search()
      _queue_document()
      commit_documents()      
      reset_index()
      _optimize_index()
      _delete_document()

    Application code should call:
      search() to perform a search
      notify_*() to notify the search engine that a document needs to be (re)indexed
      commit_documents() to have documents committed to the search db
      set_batch_mode() to set whether or not to index in batch mode
    """

    def __init__(self):
        self._preview_length = 250

        # batch mode proccess should set these to false
        self.async = True   # if set to True, lucene will spawn thread to index document (good for real-time indexing)
        self.commit_immediately = True  # if set to True, lucene will commit document immediately rather than batching (good for real-time indexing)
        self.always_try_deleting_first = False  # if set to True, we'll set/override the 'existing' parameter in queue_document to True so that we'll always try deleting the document first -- good if you need to re-run parts of batch indexing

    def search(self, results, user, types, query, sort='relevance', minKarma='any', minDate='any', group='any', start=1, end=20):
        """
        Handles a query from a user.
        Returns a list of SearchResults suitable for display.
        The list contains only those items that the user is allowed to read.
        The value of sort can be either 'relevance' or 'date' or 'karma'
        The list contains only those results from start to end, inclusive (1-based).
        Set minkarma and/or minDate to 'any' to ignore these parameters.
        Set group to 'any' to ignore, otherwise can be 'mygroups' or a group id.
        types: list of allowed types ("User", "Group", "Usernews", "UsernewsComment", "Discussion", "DiscussionComment", "Wikipage", Poll) -- if vector is empty, allow ALL types
        """
        pass


    def notify_new_wiki_page(self, wikipage):
        """
        Handles the case when a new wiki page is created.
        Called by api.wiki_edit_page() and api.wiki_new_page_like()
        Also called by search_reindex_all.py script.
        """    
        self._generate_document_for_wiki_page(wikipage, False)

    def notify_edited_wiki_page(self, wikipage):
        """
        Handles the case when an existing wiki page is edited.
        Note that we index only the latest revision.
        Called by api.wiki_edit_page()
        """        
        self._generate_document_for_wiki_page(wikipage, True)

    def notify_deleted_wikipage(self, page):
        """
        Handles the case when a wikipage is deleted.
        Called by api.wiki_delete_page()
        """
        self._delete_document(self._encode_oid(page._p_oid))             

    def notify_new_blog_item(self, blogitem):
        """
        Handles the case when a new discussion topic or user news item is created.
        Called by api.blog_new_item()
        Also called by search_reindex_all.py script.    
        """

        # Let's deduce what kind of Blog this is.  It can be any of the following:
        #  qon.group.Group = a group's discussion blog
        #  qon.wiki.WikiPage = a wiki page's comments
        #  qon.user.User = a user's personal news
        t = type(blogitem.blog.ihb)
        assert ((t is qon.group.Group) or (t is qon.wiki.WikiPage) or (t is qon.user.User))

        # create a new Discussion Topic or a new qon.user.User News
        #  (a qon.wiki.WikiPage's qon.blog.BlogItem is just a placeholder for comments, so let's not bother with it)
        if (t is qon.group.Group) or (t is qon.user.User):
            self._generate_document_for_blog_item(blogitem, False, t) 

    def notify_new_blog_comment(self, blogitem, comment, updateBlogItem=False):
        """
        Handles the case when a comment is made to a discussion topic,
        user news item, or wiki page.
        Called by api.blog_new_comment()
        blogitem is the parent BlogItem, not the comment itself
        """

        t = type(blogitem.blog.ihb)
        assert ((t is qon.group.Group) or (t is qon.wiki.WikiPage) or (t is qon.user.User))

        # when a Discussion Topic gets a comment, just regenerate the document for the Discussion Topic
        # when a qon.user.User News gets a comment, regenerate the document for the User News
        if updateBlogItem:
            if (t is qon.group.Group) or (t is qon.user.User):
                self._generate_document_for_blog_item(blogitem, True, t)

        # also, as of 2005-03-11, we now index comments separately, so do that here
        if (t is qon.group.Group) or (t is qon.user.User):
            self._generate_document_for_blog_comment(blogitem, comment, False, t)        

        # when a wiki page gets a comment, just regenerate the document for the wiki page
        # (should never happen anymore, because we disabled workspace comments)
        if (t is qon.wiki.WikiPage):
            wikipage = blogitem.blog.ihb
            self._generate_document_for_wiki_page(wikipage, True)
     
    def notify_edited_blog_item(self, blogitem):
        """
        Handles the case when a discussion topic or user news item is edited.
        Called by api.blog_edit_item()
        """

        t = type(blogitem.blog.ihb)
        # (a qon.wiki.WikiPage's qon.blog.BlogItem is just a placeholder for comments, so it shouldn't ever get edited)
        # assert (t is not qon.wiki.WikiPage)
        # assert ((t is qon.group.Group) or (t is qon.user.User))

        # when a Discussion Topic gets edited, just update the document for the Discussion Topic
        # when a qon.user.User News gets edited, regenerate the document for theUser News  
        if (t is qon.group.Group) or (t is qon.user.User):
            self._generate_document_for_blog_item(blogitem, True, t)

    def notify_edited_blog_comment(self, blogitem):
        """
        Handles the case when a discussion topic or user news comment is edited.
        Called by api.blog_edit_item()
        """

        t = type(blogitem.blog.ihb)
        # (a qon.wiki.WikiPage's qon.blog.BlogItem is just a placeholder for comments, so it shouldn't ever get edited)
        # assert (t is not qon.wiki.WikiPage)
        # assert ((t is qon.group.Group) or (t is qon.user.User))

        # when a Discussion Topic gets edited, just update the document for the Discussion Topic
        # when a qon.user.User News gets edited, regenerate the document for theUser News  
        if (t is qon.group.Group) or (t is qon.user.User):
            self._generate_document_for_blog_comment(blogitem.parent_blogitem, blogitem, True, t)

    def notify_deleted_blog_item(self, blogitem):
        """
        Handles the case when a discussion topic or user news item is deleted.
        Called by api.blog_delete_item()
        """
        self._delete_document(self._encode_oid(blogitem._p_oid))             

    def notify_deleted_blog_comment(self, blogitem):
        """
        Handles the case when a discussion topic or user news comment is deleted.
        Called by api.blog_delete_item()
        """
        self._delete_document(self._encode_oid(blogitem._p_oid))         

    def notify_new_user(self, user):
        """
        Handles the case when a new user is created through the api.
        Does not handle the case when they are created manually or through create_db
        Called by api.user_new()
        Also called by search_reindex_all.py script.    
        """
        self._generate_document_for_user(user, False)

    def notify_edited_user(self, user):
        """
        Handles the case when an existing user's info is edited.
        Called by api.user_set_settings(), api.user_set_primary_email()
        """
        self._generate_document_for_user(user, True)

    def notify_deleted_user(self, user):
        """
        Handles the case when a group is deleted.
        Called by api.user_delete()
        """
        self._delete_document(self._encode_oid(user._p_oid))             
        
        
    def notify_new_group(self, group):
        """
        Handles the case when a new group is created.
        Does not handle the case when they are created manually or through create_db    
        Called by api.group_create()
        Also called by search_reindex_all.py script.    
        """
        self._generate_document_for_group(group, False)   
        
    def notify_edited_group(self, group):
        """
        Handles the case when an existing group's info is edited.
        Called by api.group_set_settings()
        """      
        self._generate_document_for_group(group, True)

    def notify_deleted_group(self, group):
        """
        Handles the case when a group is deleted.
        Called by api.group_delete()
        """
        self._delete_document(self._encode_oid(group._p_oid))             
        
        
    def notify_karma_given(self, to):
        """
        Handles the case when a searchable entity's karma changes.
        Called by api.karma_give_good() and api.karma_give_bad() and api.group_decay_inactive_karma()
        """
        t = type(to)
        if t is qon.wiki.WikiPage:
            self.notify_edited_wiki_page(to)
        if t is qon.blog.BlogItem:
            if not to.parent_blogitem:     # to determine if it's a comment or not
                self.notify_edited_blog_item(to)
            else:
                self.notify_edited_blog_comment(to)
        if t is qon.user.User:
            self.notify_edited_user(to)

    def notify_new_poll(self, poll):
        """
        Handles the case when a poll is created.
        Called by api.poll_create() and api.poll_create_custom()
        """
        self._generate_document_for_poll(poll, False)
        
    def notify_poll_vote(self, poll):
        """
        Handles the case when a poll is created.
        Called by api.poll_vote()
        """        
        self._generate_document_for_poll(poll, True)

    def notify_poll_cancel(self, poll):
        """
        Handles the case when a poll is cancelled.
        Called by api.poll_cancel()
        """        
        self._generate_document_for_poll(poll, True)

    def commit_documents(self):
        # called to index all documents that have been queued up.
        #  the qon.api__ functions all call this immediately after each notify__() call,
        #  but the script search_reindex_all.py calls it only after a big batch of docs
        pass

    def set_async(self, b):
        self.async = b

    def set_commit_immediately(self, b):
        self.commit_immediately = b

    def set_always_try_deleting_first(self, b):
        self.always_try_deleting_first = b
    
# ----------------------------------------------------------------------

    def _generate_document_for_blog_item(self, blogitem, existing, t):
        fields = []

        # don't use watchable_modified_date() now that comments live separately from blog items
        last_edited_date = blogitem.modified
        if not last_edited_date:
            last_edited_date = blogitem.date

        # gather fields that are consistent across all types of blogs
        # fields are in the form of [name, value, isStored, isIndexed, isTokenized]
        fields.append(['title', blogitem.title, False, True, True])
        fields.append(['karma', str(blogitem.get_karma_score()).zfill(6), False, True, False])
        fields.append(['u_name', blogitem.author.display_name(), False, True, True])
        fields.append(['date', str(get_unix_timestamp(last_edited_date)), False, True, False])   # index it so that we can sort by it.  add T to fix Lucene range query bug
        fields.append(['oid', self._encode_oid(blogitem._p_oid), True, True, False])

        # create the main text for indexing
        # (title + summary + author name)
        text = "%s %s %s" % (blogitem.title, blogitem.get_summary(), blogitem.author.display_name())
        fields.append(['text', text, False, True, True])

        # create the preview text    
        preview = self._generate_preview_text(blogitem.get_summary())
        fields.append(['preview', preview, True, False, False])

        # gather fields that differ depending on the type of blog    
        if t is qon.group.Group:
            group = blogitem.blog.ihb
            fields.append(['type', 'Discussion', True, True, True])
            fields.append(['g_name', group.display_name(), False, True, True])
            
        if t is qon.user.User:
            fields.append(['type', 'Usernews', True, True, True])             

        # index on tags
        tidb = get_tagged_item_database()
        tags = " ".join(tidb.get_tags(blogitem._p_oid))
        fields.append(['tags', tags, False, True, False])

        # send the document for indexing        
        self._queue_document(fields, existing)

    def _generate_document_for_blog_comment(self, blogitem, comment, existing, t):
        fields = []

        # don't use watchable_modified_date() now that comments live separately from blog items
        last_edited_date = comment.modified
        if not last_edited_date:
            last_edited_date = comment.date        

        # gather fields that are consistent across all types of blogs
        # fields are in the form of [name, value, isStored, isIndexed, isTokenized]
        fields.append(['title', comment.title, False, True, True])
        fields.append(['karma', str(comment.get_karma_score()).zfill(6), False, True, False])
        fields.append(['u_name', comment.author.display_name(), False, True, True])
        fields.append(['date', str(get_unix_timestamp(last_edited_date)), False, True, False])   # index it so that we can sort by it
        fields.append(['oid', self._encode_oid(comment._p_oid), True, True, False])

        # create the main text for indexing
        # (title + summary + author name)
        tidb = get_tagged_item_database()
        tags = " ".join(tidb.get_tags(comment._p_oid))
        text = "%s %s %s %s" % (comment.title, comment.get_summary(), comment.author.display_name(), tags)
        fields.append(['text', text, False, True, True])

        # create the preview text    
        preview = self._generate_preview_text(comment.get_summary())
        fields.append(['preview', preview, True, False, False])

        # gather fields that differ depending on the type of blog    
        if t is qon.group.Group:
            group = blogitem.blog.ihb
            fields.append(['type', 'DiscussionComment', True, True, True])           
            fields.append(['g_name', group.display_name(), False, True, True])
            
        if t is qon.user.User:
            fields.append(['type', 'UsernewsComment', True, True, True])              

        # send the document for indexing        
        self._queue_document(fields, existing)        

    def _generate_document_for_wiki_page(self, wikipage, existing):
        latest_version = wikipage.versions[-1]
        group = wikipage.wiki.group
        
        fields = []    

        # fields are in the form of [name, value, isStored, isIndexed, isTokenized]
        fields.append(['title', latest_version.title, False, True, True])
        fields.append(['karma', str(wikipage.get_karma_score()).zfill(6), False, True, False])
        fields.append(['u_name', latest_version.author.display_name(), False, True, True])    
        fields.append(['date', str(get_unix_timestamp(latest_version.date)), False, True, False])    # index it so that we can sort by it
        fields.append(['oid', self._encode_oid(wikipage._p_oid), True, True, False])
        fields.append(['type', 'Wikipage', True, True, True])                       
        fields.append(['g_name', group.display_name(), False, True, True])

        # create the main text to index (title + __raw + comments + commenting authors names + name + last editor name)
        tidb = get_tagged_item_database()
        tags = " ".join(tidb.get_tags(wikipage._p_oid))
        comments = wikipage.get_comments()
        text = "%s %s %s %s %s %s" % (latest_version.title, latest_version.get_raw(), ''.join(["%s %s " % (x.get_summary(), x.author.display_name()) for x in comments]), wikipage.name, latest_version.author.display_name(), tags)
        fields.append(['text', text, False, True, True])    

        # create the preview text    
        preview = self._generate_preview_text(latest_version.get_raw())
        fields.append(['preview', preview, True, False, False])

        # send the document for indexing        
        self._queue_document(fields, existing)

    def _generate_document_for_user(self, user, existing):
        fields = []    

        # fields are in the form of [name, value, isStored, isIndexed, isTokenized]
        fields.append(['karma', str(user.get_karma_score()).zfill(6), False, True, False])
        fields.append(['u_name', user.display_name(), False, True, True])
        fields.append(['date', str(get_unix_timestamp(user.get_user_data().member_since())), False, True, False])    # index it so that we can sort by it            
        fields.append(['oid', self._encode_oid(user._p_oid), True, True, False])
        fields.append(['type', 'User', True, True, True])                   

        # create the main text to index (bio + email addresses + name)
        tidb = get_tagged_item_database()
        tags = " ".join(tidb.get_tags(user._p_oid))
        text = "%s %s %s %s %s" % (user.bio, user.location, " ".join(user.email_list()), user.display_name(), tags)
        fields.append(['text', text, False, True, True])    

        # create the preview text    
        preview = self._generate_preview_text(user.bio)
        fields.append(['preview', preview, True, False, False])

        # send the document for indexing        
        self._queue_document(fields, existing)


    def _generate_document_for_group(self, group, existing):
        fields = []    

        # fields are in the form of [name, value, isStored, isIndexed, isTokenized]
        fields.append(['karma', str(group.get_karma_score()).zfill(6), False, True, False])    
        fields.append(['g_name', group.display_name(), False, True, True])
        fields.append(['date', str(get_unix_timestamp(group.date)), False, True, False])    # index it so that we can sort by it        
        fields.append(['oid', self._encode_oid(group._p_oid), True, True, False])
        fields.append(['type', 'Group', True, True, True])                     

        # create the main text to index (description + group userid + name)
        text = "%s %s %s" % (group.description, group.get_user_id(), group.display_name())
        fields.append(['text', text, False, True, True])

        # create the preview text    
        preview = self._generate_preview_text(group.description)
        fields.append(['preview', preview, True, False, False])

        # send the document for indexing        
        self._queue_document(fields, existing)

    def _generate_document_for_poll(self, poll, existing):
        group = poll.container.ihb
        
        fields = []    

        # fields are in the form of [name, value, isStored, isIndexed, isTokenized]
        fields.append(['title', poll.title, False, True, True])
        fields.append(['karma', "0".zfill(6), False, True, False])            
        fields.append(['u_name', poll.creator.display_name(), False, True, True])    
        fields.append(['date', str(get_unix_timestamp(poll.date)), False, True, False])    # index it so that we can sort by it
        fields.append(['end_date', str(get_unix_timestamp(poll.end_date)), False, True, False])    # index it so that we can sort by it
        fields.append(['oid', self._encode_oid(poll._p_oid), True, True, False])
        fields.append(['type', 'Poll', True, True, True])                       
        fields.append(['g_name', group.display_name(), False, True, True])

        # create the main text to index (title + description + creator + choices)
        choices = poll.get_data().choices
        text = "poll polls %s %s %s %s" % (poll.title, poll.get_description(), poll.creator.display_name(), ''.join(["%s " % x for x in choices]))
        fields.append(['text', text, False, True, True])       

        # create the preview text    
        preview = self._generate_preview_text(poll.get_description())
        fields.append(['preview', preview, True, False, False])

        # send the document for indexing        
        self._queue_document(fields, existing)        

    def _queue_document(self, fields, existing):
        """ queue up a document for indexing """
        pass

    def _reset_index(self):
        pass

    def _optimize_index(self):
        pass

    def _delete_document(self, oid):
        pass

    def _get_field_value(self, fields, name):
        for x in fields:
            if x[0] == name:
                return x[1]
        return None

    def _generate_preview_text(self, text):
        """ Truncates the text and filters out ugly characters for
        preview display purposes"""
        if text is None:
            return ""

        # filter out ugly stuff like directives and ------, ======, etc...
        preview = uglystuff.sub('', text)
        
        if len(preview) > self._preview_length:
            preview = preview[:self._preview_length] + "..."

        return preview

    def _can_read(self, d, user):
        try:
            obj = qon.util.get_oid(d.get('oid'))
        except:
            return False                # every oid not found, just return False
        return obj.can_read(user)       # every obj needs a can_read() method

    def _matches_groups(self, document, user, group):
        if group=='any':
            return True
        document_group = _get_group(document)
        if not document_group:
            return False     # this document doesn't even belong to a group
        if group=='mygroups':
            # case in which user wants to search only his groups            
            return document_group.is_member(user) or document_group.is_owner(user)

        # check for specific group        
        return document_group.get_user_id()==group
                                          
    # necessary for a bug in apache xmlrpc which won't handle control character 26 (hex 1A)
    # actually I later modified this to remove all potentially bad characters
    #  see: http://www.mail-archive.com/rpc-user@xml.apache.org/msg00750.html
    # we should be able to get rid of this once apache xmlrpc is fixed.
    # we also use this for lupy too, since lupy has trouble with wierdo characters
    #  unless you convert them to unicode first, but then when we get the unicode
    #  string back, we have trouble printing it
    # Oct 2 2005: also added Unicode check
    def _remove_bad_characters(self, s):
    #   s.replace('\x1A', ' ')
        if type(s) is unicode:
            s = s.encode('ascii', 'xmlcharrefreplace')
        else:
            s = str(s)
            s = string.translate(s, _bad_char_translation_table)
        return s

    # lucene doesnt like binary strings
    def _encode_oid(self, o):
        return base64.encodestring(o)[:-1]      # chop off trailing \n

    def _decode_oid(self, e):
        return base64.decodestring(e)

# ----------------------------------------------------------------------

class SearchResult:
    """
    Class to represent a search result.
    Contains a union of all fields from all the differnt document types.
    For a given type, only a subset of the fields will actually be used.
    """

    def __init__(self, doc, score):
        self.score = score
        self.preview = doc.get('preview')
        self.type = str(doc.get('type'))
        self.obj = qon.util.get_oid(doc.get('oid'))
        self.group = _get_group(doc)

# ----------------------------------------------------------------------
# create a translation table that can be used to filter out characters
#  less than a 32 (space) and greater than 126 (~)
#  see: http://www.mail-archive.com/rpc-user@xml.apache.org/msg00750.html
#  and http://www.asciitable.com/

def good_char(c):
    if c < '\x20' or c > '\x7e':
        return ' '
    else:
        return c

_all256chars = string.maketrans('', '')
_bad_char_translation_table = ''.join([good_char(c) for c in list(_all256chars)])

# ----------------------------------------------------------------------
# for storing dates in index as "seconds since Jan 1, 1970"
def get_unix_timestamp(dt):
    if not dt:
        return 0
    td = dt - datetime.utcfromtimestamp(0)
    return td.days*86400 + td.seconds

# ----------------------------------------------------------------------
def _get_group(d):
    t = d.get('type')
    assert(t)
    obj = qon.util.get_oid(d.get('oid'))
    if t=='Discussion':
        return obj.blog.ihb
    if t=='Wikipage':
        return obj.wiki.group
    if t=='Group':
        return obj
    if t=='Poll':
        return obj.container.ihb
    if t=='DiscussionComment':
        return obj.parent_blogitem.blog.ihb
    return None    
    

# A "do-nothing" search engine
# searchengine = SearchEngine()

# Lupy
# import qon.search_lupy
# searchengine = qon.search_lupy.SearchLupy("/www/var/qon_lupy")

# Lucene for xmlrpc -- get address from site.conf file
import qon.search_lucene
from dulcinea.site_util import get_config
import os
site_config = get_config()
site = os.environ.get('SITE', None)
lucene_address = site_config.get(site, 'lucene-address', fallback='')
searchengine = qon.search_lucene.SearchLucene(lucene_address)
# ----------------------------------------------------------------------
