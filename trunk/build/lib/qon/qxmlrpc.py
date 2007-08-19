"""
$Id: qxmlrpc.py,v 1.10 2006/01/26 07:03:36 alex Exp $

Implementation of ned.com XML-RPC Server.
"""
import sys, xmlrpclib
from datetime import datetime, timedelta
from DocXMLRPCServer import DocCGIXMLRPCRequestHandler
from quixote import get_request
from protocols import *

import qon.atom
import qon.api
import qon.karma
import qon.user
import qon.wiki
import qon.group
import qon.blog

from qon.base import get_user_database, get_group_database, get_list_database, \
        get_session_manager
from qon import local
from qon.util import xml_escape
from qon.ui.blocks.util import atom_id, lookup_atom_id, convert_url_to_atom_id, \
        path_to_obj, full_url, is_internal_user, secure_user_cookie_to_user

# Fault Codes
FAULT_INVALID_LOGIN = -1
FAULT_NOT_SECURE = -2
FAULT_INVALID_GROUP = -3
FAULT_INVALID_ITEM = -4
FAULT_ITEM_DELETED = -5
FAULT_NO_ACCESS = -6

def _format_dt(dt):
    if not dt:
        return 'never'
    dt = dt.replace(microsecond=0)
    return '%sZ' % dt.isoformat()

def _format_user(user):
    return dict(
            atom_tag = atom_id(user),
            display_name = xml_escape(user.display_name()),
            feedback_score = user.get_karma_score(),
            )

class IItemAPI(Interface):
    """Interface for API methods relating to BlogItems and WikiPages."""

def set_user(user):
    """Set the user acting upon the item."""

def get_item(fields):
    """Return struct of requested fields for an item.

    Valid fields to request are:

        text:           plain text (RST) of item
        html:           HTML of item text
        feedback:       Struct containing feedback-related data

    Returned struct will contain:

        atom_tag:       atom_tag of item
        title:          title of item
        author:         author information
                        (author of last revision for workspace pages)
        created:        creation date
        modified:       modification date (if applicable)

        comment_count:  number of comments (if applicable)
        revision_count: number of revisions (if applicable)
        text:           plain text of item (if requested)
        html:           HTML of item (if requested)
        feedback:       Feedback-related data (if requested)

    """

def get_item_feedback():
    """Return struct of feedback information for an item."""

def edit_item(data):
    """Edit an item

    Valid fields in data struct to edit are:

        title:          title of item
        text:           plain text (rst)
    """

class INewItemAPI(Interface):
    """Interface to create new BlogItems within a blog (topics) or
    new workspace pages within a wiki."""

    def new_item(data):
        """Create an item

        Valid fields in data struct are:

            title:          title of item (topic title or page name)
            text:           text of item
        """

class BaseItemAPI(object):
    """Common API methods for BlogItems and WikiPages."""

    advise(
            instancesProvide = [IItemAPI],
            )

    def __init__(self, item):
        self.item = item

    def set_user(self, user):
        self.user = user

        if self.item:
            # check user perms
            if not self.item.can_read(self.user):
                raise xmlrpclib.Fault(FAULT_NO_ACCESS, 'User cannot access this item.')

    def get_item_feedback(self):
        """Get feedback information for item.
        """
        _rollout_date = datetime(2005, 2, 10, 0)    # utc
        _rollout_date_display = "February 9, 2005, 4:00PM PST"

        assert self.item
        assert self.user

        user_db = get_user_database()

        def get_users(karma_givers):
            if self.item.date < _rollout_date:
                return []

            users = []
            for karma, user_id in karma_givers:
                if abs(karma) >= abs(qon.karma.show_neg_threshold):
                    users.append(_format_user(user_db.get_user(user_id)))
            return users


        plus_total, neg_total, pos_karma_givers, neg_karma_givers = self.item.karma_details()

        stats = dict(
                feedback_score=self.item.get_karma_score(),
                net_from_me=self.item.karma_points_from(self.user),
                positive_total=plus_total,
                negative_total=neg_total,
                decay_total=(plus_total - neg_total) - self.item.get_karma_score(),
                num_positive_users=len(pos_karma_givers),
                num_negative_users=len(neg_karma_givers),
                positive_users=get_users(pos_karma_givers),
                negative_users=get_users(neg_karma_givers),
                )

        return stats

    def get_item(self, fields):
        assert self.item
        assert self.user

        struct =  dict(
                atom_tag = self.atom_id(),
                title = xml_escape(self.item.get_title()),
                feedback_score = self.item.get_karma_score(),
                )

        if 'feedback' in fields:
            struct['feedback'] = self.get_item_feedback()

        return struct

    def atom_id(self):
        if self.item:
            return atom_id(self.item)
        return None

class BlogItemAPI(BaseItemAPI):
    """API methods for BlogItems."""

    advise(
            instancesProvide = [IItemAPI],
            )

    def __init__(self, item, user=None):
        BaseItemAPI.__init__(self, item)

        if item:
            # check for valid type
            if not isinstance(self.item, qon.blog.BlogItem):
                raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Invalid item.')

        if user:
            self.set_user(user)


    def edit_item(self, data):
        assert self.item
        assert self.user
        if self.item.can_edit(self.user) and self.user is self.item.author:
            qon.api.blog_edit_item(self.item,
                    title = data.get('title', self.item.get_title()),
                    summary = data.get('text', self.item.get_summary()),
                    )
        else:
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, "No permission to edit item")

    def new_comment(self, text):
        assert self.item
        if not self.user.can_post():
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, "No permission to post item")
        return qon.api.blog_new_comment(self.item, self.user, title='comment', summary=text, main='')

    def delete_item(self):
        assert self.item
        if not self.item.can_delete(self.user):
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, "No permission to delete item")
        qon.api.blog_delete_item(self.item)

    def undelete_item(self):
        assert self.item
        if not self.item.can_manage(self.user):
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, "No permission to undelete item")
        qon.api.blog_undelete_item(self.item)

    def get_item(self, fields):
        struct = BaseItemAPI.get_item(self, fields)

        struct['author'] = _format_user(self.item.author)
        struct['created'] = _format_dt(self.item.date)

        if self.item.modified:
            struct['modified'] = _format_dt(self.item.modified)

        if not self.item.parent_blogitem:
            struct['comment_count'] = len(self.item.get_all_comments())

        if 'text' in fields:
            struct['text'] = xml_escape(self.item.get_summary())

        if 'html' in fields:
            struct['html'] = self.item.get_cached_html()

        return struct

declareAdapter(BlogItemAPI, [IItemAPI], forTypes=[qon.blog.BlogItem, qon.blog.Blog])

class BlogNewItemAPI(BaseItemAPI):
    """API for creating new BlogItems."""

    advise(
            instancesProvide = [INewItemAPI],
            )

    def __init__(self, item, user=None):
        BaseItemAPI.__init__(self, item)

        if user:
            self.set_user(user)

        if item:
            # check for valid type
            if not isinstance(self.item, qon.blog.BlogItem) and not isinstance(self.item, qon.blog.Blog):
                raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Invalid type for new item.')

    def new_item(self, data):
        assert self.user
        if not self.user.can_post():
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, "No permission to post item")
        if not self.item.can_read(self.user):
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, "No permission to read group")

        # When using this API to create a new item, self.item is the container which
        # will contain the item: either a Blog, BlogItem, or Wiki.

        container = self.item
        title = data.get('title', '')
        text = data.get('text', '')

        if isinstance(container, qon.blog.Blog):
            # create a new topic
            self.item = qon.api.blog_new_item(container, self.user, title, text)
        elif isinstance(container, qon.blog.BlogItem):
            # create a new comment
            self.item = qon.api.blog_new_comment(container, self.user, title='comment', summary=text, main='')
        else:
            # invalid container for this API
            self.item = None

        return self.item

declareAdapter(BlogNewItemAPI, [INewItemAPI], forTypes=[qon.blog.BlogItem, qon.blog.Blog])

class WikiPageAPI(BaseItemAPI):
    """API methods for WikiPages."""

    advise(
            instancesProvide = [IItemAPI],
            )

    def __init__(self, item, user=None):
        BaseItemAPI.__init__(self, item)

        if item:
            # check for valid type
            if not isinstance(self.item, qon.wiki.WikiPage):
                raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Invalid type for workspace api.')

        if user:
            self.set_user(user)

    def get_item(self, fields):
        struct = BaseItemAPI.get_item(self, fields)

        struct['author'] = _format_user(self.item.versions[-1].author)
        struct['created'] = _format_dt(self.item.versions[0].date)
        struct['modified'] = _format_dt(self.item.versions[-1].date)
        struct['revision_count'] = len(self.item.versions)

        if 'text' in fields:
            struct['text'] = xml_escape(self.item.versions[-1].get_raw())

        if 'html' in fields:
            struct['html'] = self.item.get_cached_html2()


        return struct

    def edit_item(self, data):
        assert self.item
        assert self.user
        if self.item.can_edit(self.user):
            qon.api.wiki_edit_page(self.item.wiki,
                    page=self.item,
                    name=self.item.name,
                    author=self.user,
                    title=self.item.versions[-1].title,
                    raw=data.get('text', self.item.versions[-1].get_raw()),
                    )
        else:
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, "No permission to edit item")

declareAdapter(WikiPageAPI, [IItemAPI], forTypes=[qon.wiki.WikiPage, qon.wiki.Wiki])

class WikiNewItemAPI(BaseItemAPI):
    """API for creating new wiki pages."""

    advise(
            instancesProvide = [INewItemAPI],
            )

    def __init__(self, item, user=None):
        BaseItemAPI.__init__(self, item)

        if item:
            # check for valid type
            if not isinstance(self.item, qon.wiki.WikiPage) and not isinstance(self.item, qon.wiki.Wiki):
                raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Invalid type for new item.')

        if user:
            self.set_user(user)

    def new_item(self, data):
        assert self.user
        if not self.user.can_post():
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, "No permission to post item")
        if not self.item.can_read(self.user):
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, "No permission to read group")

        # When using this API to create a new item, self.item is the container which
        # will contain the item: either a Blog, BlogItem, or Wiki.

        container = self.item
        title = data.get('title', '')
        text = data.get('text', '')

        if isinstance(container, qon.wiki.Wiki):
            # create a new wiki page (unless it already exists, in which case
            #  we raise a fault)
            self.item = qon.api.wiki_new_page(container,  
                    name=title,
                    author=self.user,
                    title=title,
                    raw=text,
                    )
            if not self.item:
                raise xmlrpclib.Fault(FAULT_INVALID_ITEM, "Workspace page already exists")
        else:
            # invalid container for this API
            self.item = None

        return self.item

declareAdapter(WikiNewItemAPI, [INewItemAPI], forTypes=[qon.wiki.WikiPage, qon.wiki.Wiki])

class QonAPI(object):
    """Main dispatcher for XML-RPC API.

    Note that all method documentation will be public.
    """
    require_atom    = True  # require atom authentication
    max_login_age   = timedelta(seconds=5*60)

    def version(self):
        """Return version number of this server (int). Any changes to the API which
        are not backwards compatible will force an increment of the version number.
        """
        return 1

    def login(self, username, password):
        """Return a login_bundle struct if username and password are valid. Raises
        a Fault if invalid.

        You must generally call this method to obtain a login_bundle for use
        with any other API method. valid_login() may be used to verify the
        validity of login_bundle. Login bundles generally expire after
        five minutes.

        NOTE: the username provided must be that of a member of the
        "api" group at http://www.ned.com/group/api/

        The login bundle uses the WSSE cryptographic protocol to protect
        your password during its use with any other API method.

        Calls to this method MUST be via HTTPS or a Fault will be raised. Calls
        to the rest of the API should be via HTTP.

        Parameters:
            username: e-mail or user-id (string)
            password: string

        Returns:
            login_bundle: struct:
                username:   user-id (string)
                passdigest: password digest (string)
                created:    creation timestamp (string)
                nonce:      string
        atom_tag:   atom_tag of user (string)

        """
        if local.HTTPS_LOGIN and get_request().scheme != 'https':
            raise xmlrpclib.Fault(FAULT_NOT_SECURE, 'Must use https')

        user = get_user_database().authenticate_user(username, password)

        # check api group membership or internal user
        if user:
            if not is_internal_user(user):
                group = get_group_database().get_group('api')
                if group and not group.is_member(user):
                    raise xmlrpclib.Fault(FAULT_INVALID_LOGIN, 'User must be member of http://www.ned.com/group/api/')

        if user:
            return self._create_login_bundle(user)

        raise xmlrpclib.Fault(FAULT_INVALID_LOGIN, 'Invalid login')

    def _create_login_bundle(self, user):
        """Given a user, return a login_bundle for the user."""

        (digest, creation, nonce) = qon.atom.create_password_digest(user.get_password_hash())
        atom_tag = atom_id(user)

        return dict(
                username=user.get_user_id(),
                passdigest=digest,
                created=creation,
                nonce=nonce,
                atom_tag=atom_tag,
                )



    def valid_login(self, login_bundle):
        """Return True if login_bundle is currently allowed to access
        this server, raises Fault otherwise.

        login_bundle is a struct as returned by login().

        See http://www.xml.com/pub/a/2003/12/17/dive.html.

        Parameters:
            login_bundle: struct

        login_bundles must be less than 5 minutes old to be valid.
        """

        user = self._authenticate_user(login_bundle, self.max_login_age)
        if user:
            return True

        raise xmlrpclib.Fault(FAULT_INVALID_LOGIN, 'Invalid or expired login bundle')

    def user_atom_id(self, login_bundle, user_id):
        """Given a short user id (e.g. 'u123456789') return the corresponding user's atom_tag,
        which is required by other API calls.
        """
        cur_user = self._check_login(login_bundle)
        user = get_user_database().get_user(user_id)
        if user:
            return atom_id(user)
        return None

    def group_atom_id(self, login_bundle, group_id):
        """Given a short group id (e.g. 'community-general') return the corresponding group's atom_tag,
        which is required by other API calls.
        """
        cur_user = self._check_login(login_bundle)
        group = get_group_database().get_group(group_id)
        if group:
            return atom_id(group)
        return None

    def user_info(self, login_bundle, atom_tag_list):
        """Given a list of users' atom_tags, return a struct for each user containing
        the user's display name and feedback score."""
        cur_user = self._check_login(login_bundle)

        result = {}
        for atom_id in atom_tag_list:
            user = lookup_atom_id(atom_id)
            if user and not result.has_key(atom_id) \
                    and isinstance(user, qon.user.User):
                        result[atom_id] = _format_user(user)
        return result

    def user_data(self, login_bundle, atom_tag, fields):
        """Return struct containing requested fields for user atom_tag.

        Parameters:
            atom_tag: the atom tag of the user for which requesting data
            fields: array of zero or more of the following:
                'name':         currently-specified name to be displayed
                'fscore':       feedback score
                'fbank':        feedback bank
                'fpos':         positive feedback received
                'fneg':         negative feedback received
                'fposgiv':      positive feedback given
                'fneggiv':      negative feedback given
                'fcom':         net comment feedback received
                'fcompos':      positive comment feedback received
                'fcomneg':      negative comment feedback received
                'membsince':    member since date
                'lastlogin':    last login (may return 'never' or 'inactive')
                'idletime':     idle time or 'none' if not logged in
                'posffrom':     positive feedback from (array of user_ids)
                'posffromnum':  number of positive feedback givers
                'negffrom':     negative feedback from (if visible)
                'neggfromnum':  number of negative feedback givers
                'emaildomain:   domain portion of email
                'groupown':     groups owned by user
                'groupmemb':    groups user is a member of
                'all':          all of the above

        Returns struct containing one entry per requested field.
        """
        user_db = get_user_database()
        group_db = get_group_database()

        cur_user = self._check_login(login_bundle)
        user = lookup_atom_id(atom_tag)
        if not user or not isinstance(user, qon.user.User):
            raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Invalid user id')

        all = 'all' in fields
        result = {}

        if all or 'name' in fields:
            result['name'] = user.display_name()
        if all or 'fscore' in fields:
            result['fscore'] = user.get_karma_score()
        if all or 'fbank' in fields:
            result['fbank'] = user.get_karma_bank_balance()
        if all or 'fpos' in fields:
            result['fpos'] = user.karma_plus_received()
        if all or 'fneg' in fields:
            result['fneg'] = user.karma_minus_received()
        if all or 'fposgiv' in fields:
            result['fposgiv'] = user.karma_plus_given()
        if all or 'fneggiv' in fields:
            result['fneggiv'] = user.karma_minus_given()

        if all or ('fcom' in fields) or ('fcompos' in fields) or ('fcomneg' in fields):
            fcompos, fcomneg = get_list_database().karma_user_content_totals(user)
        if all or 'fcom' in fields:
            result['fcom'] = fcompos + fcomneg
        if all or 'fcompos' in fields:
            result['fcompos'] = fcompos
        if all or 'fcomneg' in fields:
            result['fcomneg'] = fcomneg

        if all or 'membsince' in fields:
            dt = user.get_user_data().member_since()
            result['membsince'] = _format_dt(dt)
        if all or 'lastlogin' in fields:
            result['lastlogin'] = _format_dt(getattr(user, 'last_login', None))
        if all or 'idletime' in fields:
            if user.is_disabled():
                sec = 'inactive'
            else:
                idle = user.idle_time()
                if idle:
                    sec = idle.seconds
                else:
                    sec = 'none'
            result['idletime'] = sec

        if all or 'posffrom' in fields:
            result['posffrom'] = [atom_id(user_db.get_user(uid)) \
                    for karma, uid in user.positive_karma_givers()]

        if all or 'posffromnum' in fields:
            result['posffromnum'] = len(user.positive_karma_givers())

        if all or 'negffrom' in fields:
            result['negffrom'] = [atom_id(user_db.get_user(uid)) \
                    for karma, uid in user.negative_karma_givers()]

        if all or 'negffromnum' in fields:
            result['negffromnum'] = len(user.negative_karma_givers())

        if all or 'emaildomain' in fields:
            e = user.get_primary_email()
            result['emaildomain'] = e[e.find('@')+1:]
        if all or 'groupown' in fields:
            result['groupown'] = [atom_id(g) \
                    for g in group_db.owned_groups(user)]
        if all or 'groupmemb' in fields:
            result['groupmemb'] = [atom_id(g) \
                    for g in group_db.member_groups(user)]

        return result

    def user_content(self, login_bundle, atom_tag, fields, count):
        """Return struct containing requested content-related fields for user atom_tag.

        Parameters:
            user_id: the user_id of the user for which requesting data
            count:   number items to return, max is 50
            fields:  array of zero or more of the following:
                'pnews':    personal news items 
                'topics':   topics authored
                'comments': comments authored
                'pages':    workspace pages edited
                'ctopics':  topics commented upon or started
                'all':      all of the above

        Returns struct containing one entry per requested field. Items are
        returned in reverse chronological order. Items are "Atom Tags,"
        globally-unique content identifiers.
        """
        cur_user = self._check_login(login_bundle)
        user = lookup_atom_id(atom_tag)
        if not user:
            raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Invalid user id')

        def item_info(item):
            """Return struct with standard item information."""
            return dict(atom_tag=atom_id(item),
                    title=item.watchable_name(),
                    score=item.get_karma_score(),
                    )

        activity = user.get_activity()
        result = {}

        count = min(count or 50, 50)
        all = 'all' in fields

        if all or 'pnews' in fields:
            result['pnews'] = [item_info(i) for date, i \
                    in activity.recent_personal_news_for_reader(cur_user)][:count]

        if all or 'topics' in fields:
            result['topics'] = [item_info(i) for date, i \
                    in activity.recent_blog_items_for_reader(cur_user)][:count]

        if all or 'comments' in fields:
            result['comments'] = [item_info(i) for date, i, parent \
                    in activity.recent_blog_comments_for_reader(cur_user)][:count]

        if all or 'pages' in fields:
            result['pages'] = [item_info(p) for date, p \
                    in activity.recent_wiki_pages_for_reader(cur_user)][:count]

        if all or 'ctopics' in fields:
            result['ctopics'] = [item_info(i) for date, i \
                    in activity.recent_participation_for_reader(cur_user)][:count]

        return result

    def item_data(self, login_bundle, atom_tag, fields):
        """Return struct containing requested fields for specified item.

        Parameters:
            atom_tag:        atom_tag of item.
            fields: array of requested information:
                feedback:   extended feedback information
                text:       full raw (reStructuredText) text
                html:       html of item text

        Returns:
            struct of requested information (fields) as well as:
                atom_tag:       atom_tag of item
                title:          title of item
                author:         author of item
                created:        date item created
                modified:       date item modifed (only if modified)
                feedback_score: feedback score of item
                comment_count:  number of comments (only if item is a discussion topic)
                revision_count: number of revisions (only if item is a workspace page)

        For example, if fields is an empty array, the returned struct will
        include all of the above fields, but not the detailed feedback, nor
        the actual text of the item itself.
        """
        user = self._check_login(login_bundle)
        obj = lookup_atom_id(atom_tag)
        if not obj:
            raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Invalid atom_tag.')

        api = adapt(obj, IItemAPI, None)
        if api:
            api.set_user(user)
            return api.get_item(fields)

        raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Could not dispatch to API.')

    def item_edit(self, login_bundle, atom_tag, data):
        """Edit an item's data. Item may be a topic, comment, or workspace page.

        Valid fields in data are:

            title:      new title of item
            text:       new text of item

        Fields not provided are left unchanged. Editing a workspace page creates
        a new revision and ignores 'title' field.
        """
        user = self._check_login(login_bundle)
        obj = lookup_atom_id(atom_tag)
        api = adapt(obj, IItemAPI, None)
        if api:
            api.set_user(user)
            api.edit_item(data)
            return True

        raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Cannot edit this type of item.')

    def item_new(self, login_bundle, atom_tag, data):
        """Create a new topic, comment, or workspace page. Return atom_tag of new item.

        Parameters:

            atom_tag:       atom_tag of container of new item. Should be
                            either a Discussions tag, a topic tag, or a
                            Workspace tag, like this:

                            tag:ned.com:/group/group_name/news/
                            tag:ned.com:/group/group_name/news/23/
                            tag:ned.com:/group/group_name/ws/

                            Depending on the atom_tag, this function will
                            either create a new discussion topic, a new
                            comment within a discussion, or a new workspace
                            page.

            data:           struct containing:

                                title:  title of new item (ignored for comments)
                                text:   text of new item
        """
        user = self._check_login(login_bundle)
        obj = self._get_blog_or_wiki(user, atom_tag)

        api = adapt(obj, INewItemAPI, None)
        if not api:
            raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Cannot create a new item here.')

        api.set_user(user)
        item = api.new_item(data)
        return api.atom_id()

    def get_all_groups(self, login_bundle):
        """Return array of all groups (atom_tags). List may include groups that are not
        active or not accessible by user.
        """
        user = self._check_login(login_bundle)
        groups = []
        for group_id, group in get_group_database().root.iteritems():
            groups.append(atom_id(group))
        return groups

    def can_read_group(self, login_bundle, atom_tag):
        """Return True if user can read content of atom_tag, False otherwise."""
        user = self._check_login(login_bundle)
        group = self._get_group(atom_tag)
        return group.can_read(user)

    def can_edit_group(self, login_bundle, atom_tag):
        """Return True if user can create or edit content of group atom_tag, False otherwise."""
        user = self._check_login(login_bundle)
        group = self._get_group(atom_tag)
        return group.can_edit(user)

    def get_recent_topics(self, login_bundle, atom_tag, count):
        """Get count topics in most-recent order from atom_tag.

        Parameters:
            login_bundle: login_bundle from login()
            atom_tag: group's atom_tag
            count: int

        Returns:
            array of:
                (see return description of item_data())
        """
        user = self._check_login(login_bundle)
        blog = self._get_blog(user, atom_tag)
        items = blog.recent_items(count=count)

        result = []
        for item in items:
            api = BlogItemAPI(item, user)
            result.append(api.get_item([]))
        return result

    def convert_url_to_atom_id(self, login_bundle, url):
        """Given a URL for an object, return its atom_id."""

        cur_user = self._check_login(login_bundle)

        atom_id = convert_url_to_atom_id(url)
        if atom_id:
            return atom_id

        raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Invalid URL.')


    def convert_atom_id_to_url(self, login_bundle, atom_id):
        """Given an atom_id, return the URL for that object."""

        cur_user = self._check_login(login_bundle)

        obj = lookup_atom_id(atom_id)

        if obj:
            path = path_to_obj(obj)
            if path:
                return full_url(path)

        raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Invalid atom_id.')

    def internal_method(self, login_bundle, data):
        """For internal use only."""

        """
            data: struct
                method: string
                params: struct
        """
        cur_user = self._check_login(login_bundle)

        # sanity check args before proceeding in order to provide
        # sanitzed error message
        if type(data) is not dict or not data.has_key('method') or not data.has_key('params'):
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, 'Invalid data.')

        if type(data['params']) is not dict:
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, 'Invalid data.')

        # check api-admin membership
        group = get_group_database().get_group('api-admin')
        if group and not group.is_member(cur_user):
            raise xmlrpclib.Fault(FAULT_INVALID_LOGIN, 'User must be member of http://www.ned.com/group/api-admin/')

        if data['method'] in ['_cookie_login']:
            return self._internal_cookie_to_login(data['params'])

        raise xmlrpclib.Fault(FAULT_NO_ACCESS, 'Invalid access.')


    # -------------------------------------------------------------------------------

    def _internal_cookie_to_login(self, params):
        """Return login bundle for given cookies.

        parmas: struct
            session_id: string
            auth_bundle: string

        session_id is the contents of the QX_session cookie
        auth_bundle is the contents of the aux1 cookie, which includes
        a digest, creation date, and nonce, separated by '|'
        """

        # sanity check args before proceeding
        if type(params) is not dict or not params.has_key('session_id') or not params.has_key('auth_bundle'):
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, 'Invalid data.')

        # get the user_id from the session_id
        user_id = self._get_session_user_id(params['session_id'])

        # try to authorize this user_id with the auth_bundle
        user = secure_user_cookie_to_user(user_id, params['auth_bundle'])

        if user:
            # valid user, return a login_bundle for this user
            return self._create_login_bundle(user)

        raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Invalid item.')


    def _get_session(self, session_id):
        """Return the Quixote Session with given id, or None."""
        session_mgr = get_session_manager()
        try:
            session = session_mgr[session_id]
        except KeyError:
            session = None
        return session

    def _get_session_user_id(self, session_id):
        """Return user_id of user referred to by session_id, or None."""
        session = self._get_session(session_id)
        if not session:
            return None

        user = session.user
        if user:
            return user.get_user_id()
        else:
            return None

    
    # -------------------------------------------------------------------------------

    def _get_group(self, atom_tag):
        group = lookup_atom_id(atom_tag)
        if not group or not isinstance(group, qon.group.Group):
            raise xmlrpclib.Fault(FAULT_INVALID_GROUP, 'Invalid group id')
        return group

    def _get_blog(self, user, atom_tag):
        obj = lookup_atom_id(atom_tag)
        if not obj:
            raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Invalid tag')
        if isinstance(obj, qon.blog.Blog):
            blog = obj
        elif isinstance(obj, qon.blog.BlogItem):
            blog = obj.blog
        elif isinstance(obj, qon.group.Group):
            blog = obj.get_blog()
        elif isinstance(obj, qon.user.User):
            blog = obj.get_blog()
        else:
            blog = None

        if not blog:
            raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Cannot find news from tag.')

        if not blog.can_read(user):
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, "User cannot access this content")

        return blog

    def _get_wiki(self, user, atom_tag):
        obj = lookup_atom_id(atom_tag)
        if not obj:
            raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Invalid tag')
        if isinstance(obj, qon.wiki.Wiki):
            wiki = obj
        elif isinstance(obj, qon.wiki.WikiPage):
            wiki = obj.wiki
        elif isinstance(obj, qon.wiki.WikiVersion):
            wiki = obj.page.wiki
        elif isinstance(obj, qon.group.Group):
            wiki = obj.get_wiki()
        else:
            wiki = None

        if not wiki:
            raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Cannot find workspace from tag.')

        if not wiki.can_read(user):
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, "User cannot access this content")

        return wiki

    def _get_blog_or_wiki(self, user, atom_tag):
        """Using atom_tag, find a Blog, or find a Wiki if no Blog.

        Note that failure to find a blog may indicate a bad tag, or
        insufficient permissions. In either case, an attempt will be
        made to find a wiki.
        """

        try:
            obj = self._get_blog(user, atom_tag)
        except xmlrpclib.Fault:
            obj = self._get_wiki(user, atom_tag)

        return obj

    def _get_page(self, user, atom_tag):
        page = lookup_atom_id(atom_tag)
        if not page or not isinstance(page, qon.wiki.WikiPage):
            raise xmlrpclib.Fault(FAULT_INVALID_ITEM, "Invalid page name")

        if not page.can_read(user):
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, "User cannot access this content")

        return page

    def _get_revision(self, user, atom_tag):
        version = lookup_atom_id(atom_tag)
        if not version or not isinstance(version, qon.wiki.WikiVersion):
            raise xmlrpclib.Fault(FAULT_INVALID_ITEM, "Invalid revision")

        page = version.page

        if not page.can_read(user):
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, "User cannot access this content")

        return version


    def _get_item(self, user, atom_tag, allow_deleted=False):
        item = lookup_atom_id(atom_tag)
        if not item or not isinstance(item, qon.blog.BlogItem):
            raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Invalid topic id')

        if not item.can_read(user):
            raise xmlrpclib.Fault(FAULT_NO_ACCESS, 'User cannot access this content')
        if not allow_deleted and item.is_deleted():
            raise xmlrpclib.Fault(FAULT_ITEM_DELETED, 'Topic has been deleted')

        return item

    def _get_comment(self, user, group_id, topic_id, comment_id, allow_deleted=False):
        item = self._get_item(user, group_id, topic_id)

        # get comment
        comment = item.get_comment(comment_id)
        if comment:
            # valid comment, check deleted
            if not allow_deleted and comment.is_deleted():
                raise xmlrpclib.Fault(FAULT_ITEM_DELETED, 'Comment has been deleted')
            return comment
        else:
            raise xmlrpclib.Fault(FAULT_INVALID_ITEM, 'Invalid comment id')


    def _check_login(self, login_bundle):
        """Return user if valid or raise Fault if not."""

        user = self._authenticate_user(login_bundle, self.max_login_age)

        if not user:
            raise xmlrpclib.Fault(FAULT_INVALID_LOGIN, 'Invalid or expired login bundle')

        return user

    def _authenticate_user(self, login_bundle, max_age):
        """Return user if valid, otherwise raise Fault."""

        user = get_user_database().authenticate_user(
                login_bundle.get('username'),
                login_bundle.get('passdigest'),
                login_bundle.get('created'),
                login_bundle.get('nonce'),
                max_age,
                )

        if user:
            # require atom authentication. authenticate_user will return
            # user if correct plaintext password is used, which we don't want
            # to allow
            if not self.require_atom or qon.atom.valid_password_digest(
                    user.get_password_hash(),
                    login_bundle.get('passdigest'),
                    login_bundle.get('created'),
                    login_bundle.get('nonce'),
                    max_age):

                # valid user, other access checks
                self._attempt_record_ip(user)
                if not user.user_agreement_accepted():
                    raise xmlrpclib.Fault(FAULT_INVALID_LOGIN, 'Must accept User Agreement')
                if user.is_disabled():
                    raise xmlrpclib.Fault(FAULT_INVALID_LOGIN, 'Login disabled')

                return user

        raise xmlrpclib.Fault(FAULT_INVALID_LOGIN, 'Invalid login')

    def _attempt_record_ip(self, user):
        try:
            request = get_request()
        except:
            pass
        else:
            user.record_ip_access(request.get_environ('REMOTE_ADDR'))


    def _format_page(self, page, format=None):
        struct = dict(
                atom_tag = atom_id(page),
                name = page.name,
                )

        if format == 'html':
            struct['html'] = str(page.get_cached_html2())
        elif format == 'text':
            struct['text'] = page.versions[-1].get_raw()

        return struct

    def _format_revision(self, revision, format=None):
        struct = dict(
                atom_tag = atom_id(revision),
                )

        if format == 'html':
            struct['html'] = str(revision.html2())
        elif format == 'text':
            struct['text'] = revision.get_raw()

        return struct


# -----------------------------------------------------------------------------

_docs = '''
=======
General
=======

NOTE: This interface is experimental, unsupported and fluid.

The URL to access for the XML-RPC interface is:

    http://www.ned.com/home/xmlrpc

All API methods require a "login bundle," which you can obtain by
invoking the method login(). Login bundles are valid for 5 minutes,
after which time you should obtain a new bundle.  All API actions
use this login bundle to identify the user performing the given action. 

NOTE: In order to login to the API, you must first join the API group
at:

    http://www.ned.com/group/api/

Generally, API methods identify users and content using a parameter
called `atom_tag`. Atom Tags are universally-unique identifiers, and
for the purposes of this API, they are used as both input and output
parameters. For developers' purposes, they are just strings.

See http://www.xmlrpc.com/ for general assistance.

Here's how you would access the server from python:

>>> import xmlrpclib
>>> secure_server = xmlrpclib.ServerProxy('https://www.ned.com/home/xmlrpc')
>>> server = xmlrpclib.ServerProxy('http://www.ned.com/home/xmlrpc')

>>> # login to the server
>>> lb = secure_server.login('john@doe.net', 'password')

>>> # get a list of all groups in the system
>>> group_list = server.get_all_groups(lb)

>>> # get a list of most recent topics posted to the first group
>>> recent_topics = server.get_recent_topics(lb, group_list[0], 10)

>>> # get detailed information on the most recent topic
>>> topic_data = server.item_data(lb, recent_topics[0]['atom_tag'], ['text'])

>>> # get detailed information on the author of the topic
>>> user_data = server.user_data(lb, topic_data['author']['atom_tag'], ['posffrom', 'negffrom'])

>>> etc...

Generally, you will access and edit content information using item_data()
and item_edit(), as well as item_new().

You will access user-related information using user_data() and user_content(),
as well as user_info().
'''

# create singleton
_handler = DocCGIXMLRPCRequestHandler()

_handler.set_server_title("ned.com XML-RPC Server")
_handler.set_server_name("ned.com XML-RPC Server")
_handler.set_server_documentation(_docs)

_handler.register_instance(QonAPI())
# _handler.register_introspection_functions()

def handle_xml_rpc_post(data):
    return _handler._marshaled_dispatch(
            data, getattr(_handler, '_dispatch', None)
            )

def handle_xml_rpc_get():
    """Display documentation."""
    return _handler.generate_html_documentation()


_documentation = '''
<html>
<head>
<title>ned.com XML-RPC interface</title>
</head>

<h1>ned.com XML-RPC interface</h1>
<p>For XML-RPC access, POST your request to this URL.</p>
<p>There is currently no documentation available.</p>

</html>
'''

