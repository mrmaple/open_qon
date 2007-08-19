"""
$Id: user.py,v 1.102 2007/06/20 16:20:50 jimc Exp $

Provides basic User and Group classes and permission management.
"""
import re, sha, time, random, binascii
from datetime import datetime, timedelta
from dulcinea.typeutils import typecheck, typecheck_seq
from dulcinea.database import unpack_oid
from persistent.list import PersistentList
from persistent.mapping import PersistentMapping

from qon.base import get_user_database, get_usergroup_database, QonPersistent, get_list_database, get_group_database
from qon.database import ConflictAvoidingOOBTree
from qon.message import HasMessages
from qon.util import coerce_to_list, unique_items, shroud_email, iso_8859_to_utf_8
from qon.watch import WatchList
from qon.tags import Tagger
import qon.blog
import qon.karma

# Block e-mail addresses from these domains.
_blocked_domains = []

class NotEnoughPrivileges(Exception):
    """Not enough privileges to complete requested operation."""

class PasswordGenerator:
    """
    Instance attributes:
      hash : any
    NOTE: from dulcinea.user
    """
    default_seed = "iGcnvxFfyniL2w" # some random secret data

    def __init__(self, seed=default_seed):
        self.hash = sha.new(seed)
        self.hash.update(str(time.time()))

    def generate(self, seed="", length=6):
        """Generate a password.  Some effort is made to make it random.

        seed: if supplied the str() of this argument is used to update the
              generator state before generating the password.

        length: the maximum length of the password to return.

        """
        try:
            # Try to use /dev/urandom.
            self.hash.update(open("/dev/urandom", "rb").read(length))
        except IOError:
            # No source of random data.  This method will now only
            # generate passwords that look random if seed is kept secret.
            self.hash.update(str(time.time()))
        self.hash.update(str(seed))
        return binascii.b2a_base64(self.hash.digest())[:length]

_password_generator = PasswordGenerator()
    
class HasPassword:
    """Mixin class providing a password attribute and related methods.
    
    Stores primary password and generated password, to allow for users requesting
    a new password, but still being able to log in with old password. Setting
    a password explicitly with set_password eliminates the generated pasword.
    
    Typical use:
    
      - generate_password() to set initial password
      - user signs in and changes password to newpass
      - set_password('newpass') records new password
      - user requests new password
      - generate_password() generates new password
      - user may sign in with 'newpass' or newly-generated password
      - both passwords are active until set_password is explicitly called
    """

    _default_seed = "87afsx76Hjhka642asDG"
    _expiring_password = False
    _num_old_passes = 15

    def __init__(self, seed=_default_seed):
        self.__password_hash = None
        self.__generated_password_hash = None
        
    def upgradeToVersion1(self):
        self.__password_hash = getattr(self, '_password_hash', None)
        self.__generated_password_hash = None

    def set_password(self, new_pass):
        """Record a new password and eliminate any generated password."""
        
        old_hash = self.__password_hash
        
        self.__password_hash = sha.new(new_pass).hexdigest()
        self.__generated_password_hash = None
        
        if self._expiring_password:
            self._reset_date = datetime.utcnow()
            
            # record old password hash
            old_passes = self._get_old_passes()
            old_passes.append(old_hash)
            self._old_passes = PersistentList(old_passes[-self._num_old_passes:])
    
    def _get_old_passes(self):
        if hasattr(self, '_old_passes'):
            return self._old_passes
        else:
            return []
    
    def check_strong_password(self, new_pass):
        """Return True is new_pass passes some basic tests.
        """
        
        # at least 6 characters in length
        if len(new_pass) < 6:
            return False
        
        hash = sha.new(new_pass).hexdigest()
        
        # same as current password?
        if hash == self.__password_hash:
            return False
        
        # was previously used?
        if hash in self._get_old_passes():
            return False
            
        # contains at least one symbol
        if not re.search('[]\-[`~!@#$%^&*()_=+{}\|,<.>/?]', new_pass):
            return False
        
        # contains at least one digit
        if not re.search('[0-9]', new_pass):
            return False
        
        return True

    def password_expired(self, max_age):
        """Return True if password was reset more than max_age (timedelta) ago."""

        if self._expiring_password:
            if not hasattr(self, '_reset_date'):
                return True
            if datetime.utcnow() - self._reset_date > max_age:
                return True
        
        return False
        
    def set_expiring_password(self, val):
        """Turn this instance into one which expires passwords."""
        self._expiring_password = bool(val)
        
    def expiring_password(self):
        """Returns True if this instance is set to have an expiring password."""
        return self._expiring_password
        
    def valid_password(self, testPass):
        """Return True if testPass is a valid password (plain or hash)."""
        
        # test hash
        if self.__password_hash == testPass:
            return True
        
        # test plaintext
        pass_hash = sha.new(testPass).hexdigest()
        return (self.__password_hash == pass_hash) or \
            (self.__generated_password_hash == pass_hash)

    def generate_password(self):
        """Set the generated password to a random value and return it in plaintext."""
        seed = str(id(self)) + str(self.__password_hash)
        password = _password_generator.generate(seed)
        self.__generated_password_hash = sha.new(password).hexdigest()
        return password
        
    def get_password_hash(self):
        return self.__password_hash or self.__generated_password_hash

class HasUserID:
    """Mixin class providing user id and related functions.
    
    This mixin is also used for group ids.
    """
    
    _user_id_re = re.compile('^[-A-Za-z0-9_]*$')

    def __init__(self):
        self.user_id = None

    def display_name(self):
        raise NotImplementedError, "subclasses must implement"
        
    def valid_user_id(cls, user_id):
        """Returns True if user_id is in suitable format for a user_id."""
        if HasUserID._user_id_re.match(user_id):
            return True
        return False
    valid_user_id = classmethod(valid_user_id)

    def set_user_id(self, user_id):
        typecheck(user_id, str)
        if not self.valid_user_id(user_id):
            raise ValueError(
                    "Invalid user ID %s: can only contain letters, numbers, "
                    "dashes, and underscores." % user_id)

        self.user_id = user_id
        
    def get_user_id(self):
        return self.user_id
        
    def generate_user_id(self, basestr=None):
        """Set the user_id to a random value and return it."""
        user_id = self._gen_user_id(basestr)
        self.set_user_id(user_id)
        return user_id
        
    def _gen_user_id(self, basestr=None, length=9):
        """Generate a random user_id.

        basestr: str to prefix to user_id. e.g. if basestr='joe' user_id will
            be 'joe928323'
        """
        
        if length > 9:
            length = 9
        if basestr is None:
            basestr = 'u'
            
        return basestr + str(random.randint(int('1'*length), int('9'*length)))
        

class HasGroupMembership:
    """Mixin class providing group membership and related functions.
    
    An instance can be a member of any number of group (HasUserID) instances.
    """
    
    def __init__(self):
        self.__items = []
        
    def add_to_group(self, item):
        item = coerce_to_list(item)
        typecheck_seq(item, HasUserID)
        self.__items.extend(item)
        self.__items = unique_items(self.__items)
        self._p_changed = 1
        
    def remove_from_group(self, item):
        typecheck(item, HasUserID)
            
        while item in self.__items:
            self.__items.remove(item)
            
        self._p_changed = 1

    def remove_from_all_groups(self):
        self.__items = []

    def is_member_of_group(self, item):
        typecheck(item, HasUserID)
        return item in self.__items

    def group_list(self):
        return self.__items
    
class HasEmail:
    """Mixin class proving email address(es) and related functions"""
    
    def __init__(self):
        self.__items = []
        self.__unconfirmed = PersistentMapping()
        self.primary_email = None
        
    def is_valid_email(cls, email):
        """Class method returns True if email is valid, or False if it should
        be rejected.

        >>> HasEmail.is_valid_email('foo@bar.com')
        True
        >>> HasEmail.is_valid_email('foo@bar.def.com')
        True
        >>> HasEmail.is_valid_email('foo.bar@bar.def.com')
        True
        >>> HasEmail.is_valid_email('xyz')
        False
        >>> HasEmail.is_valid_email('abc@xyz@foo')
        False
        """
        global _blocked_domains
        
        if email.find('@') == -1:
            return False
        
        if email.count('@') != 1:
            return False
            
        (username, host) = email.split('@')
        if host in _blocked_domains:
            return False
        
        return True
        
    is_valid_email = classmethod(is_valid_email)
        
    def add_email(self, email):
        """Add email to the list. Adds primary if none set."""
        email = email.lower()
        if email not in self.__items:
            self.__items.append(email)
            self._p_changed = 1

        if self.primary_email is None:
            self.primary_email = email
            
    def add_unconfirmed_email(self, email):
        """Add new e-mail that has not yet been confirmed. Call confirm_email to move
        into active list of e-mails.
        Returns confirmation code that must be given to confirm_email to confirm.
        """
        email = email.lower()
        if not self.__unconfirmed.has_key(email):
            self.__unconfirmed[email] = _password_generator.generate(seed=email)
        return self.__unconfirmed[email]
        
    def remove_unconfirmed_email(self, email):
        email = email.lower()
        if self.__unconfirmed.has_key(email):
            del self.__unconfirmed[email]
            
    def confirm_email(self, code):
        """Confirm email with the given code, or return False if invalid code."""
        for email, conf_code in self.__unconfirmed.items():
            if conf_code == code:
                self.add_email(email)
                del self.__unconfirmed[email]
                self.notify_email_confirmed(email)
                return email
        return None
    
    def remove_email(self, email):
        """Remove an e-mail address from the list. Raises KeyError if only one e-mail address left"""
        email = email.lower()
        if self.__unconfirmed.has_key(email):
            return self.remove_unconfirmed_email(email)
            
        emails = self.email_list()
        if len(emails) > 1:
            self.__items.remove(email)
            self._p_changed = 1
            if email == self.get_primary_email():
                self.set_primary_email(self.email_list()[0])
        else:
            raise KeyError
            
    def remove_all_emails(self):
        self.__items = []
        self.primary_email = None
        
    def has_email(self, email):
        email = email.lower()
        return email in self.__items

    def email_list(self):
        return self.__items
        
    def unconfirmed_email_list(self):
        return self.__unconfirmed.keys()

    def set_primary_email(self, email):
        email = email.lower()
        if self.has_email(email):
            self.primary_email = email
        else:
            raise ValueError("I don't know email <%s>" % email)
            
    def get_primary_email(self):
        return self.primary_email
        
    def notify_email_confirmed(self, email):
        """Notice that email was just confirmed."""
        pass
        
    def _consistency_check(self):
        if self.primary_email is not None:
            if self.primary_email not in self.__items:
                raise KeyError, "primary_email not in email list"
            
        typecheck_seq(self.__items, str, allow_none=1)


class HasOwnership:
    """Mixin class providing ownership and permission attributes for a resource"""

    _valid_perms    = ['read', 'write', 'manage']

    def __init__(self):
        self.owners = []
        self.groups = []
        self.__owner_perms = ['read', 'write', 'manage']
        self.__group_perms = []
        self.__other_perms = []
        
    def can_read(self, user_or_group):
        """Returns 1 if user_or_group can write resource.

        Checks if id exists in owner or group lists, and if owner or
        group permissions include writing.

        Raises ValueError if user_or_group is not an instance of
        HasUserID or HasGroupMembership
        """

        return self.test_perm('read', user_or_group)

    def can_write(self, user_or_group):
        """Returns 1 if user_or_group can write resource.

        Checks if id exists in owner or group lists, and if owner or
        group permissions include writing.

        Raises ValueError if user_or_group is not an instance of
        HasUserID or HasGroupMembership
        """

        return self.test_perm('write', user_or_group)

    def can_manage(self, user_or_group):
        """Returns 1 if user_or_group can manage resource.

        Checks if id exists in owner or group lists, and if owner or
        group permissions include writing.

        Raises ValueError if user_or_group is not an instance of
        HasUserID or HasGroupMembership
        """

        return self.test_perm('manage', user_or_group)

    def add_owner(self, owner):
        """Add owner as an owner of this resource"""
        owner = coerce_to_list(owner)[:]
        typecheck_seq(owner, HasUserID)

        to_remove = []
        for user in owner:
            if user in self.owners:
                to_remove.append(user)

        for user in to_remove:
            owner.remove(user)
            
        self.owners.extend(owner)
        self._p_changed = 1

    def remove_owner(self, owner):
        """Remove owner as an owner of this resource"""
        self.owners.remove(owner)
        self._p_changed = 1

    def set_owner(self, owner):
        """Set owner as sole owner of this resource.
        
        Can use add_owner to add additional owners.
        """
        owner = coerce_to_list(owner)
        typecheck_seq(owner, HasUserID)
        self.owners = []
        self.add_owner(owner)
        
    def get_owners(self):
        return self.owners

    def add_owning_group(self, group):
        """Add group as an group owner of this resource"""
        
        group = coerce_to_list(group)
        typecheck_seq(group, HasUserID)
        self.groups.extend(group)
        self._p_changed = 1

    def remove_owning_group(self, group):
        """Remove group as a group owner of this resource"""
        self.groups.remove(group)
        self._p_changed = 1

    def set_owning_group(self, group):
        """Set group as sole group owner of this resource.

        Can use add_owning_group to add additional groups.
        """
        typecheck(group, HasUserID)
        self.groups = []
        self.groups.append(group)
        self._p_changed = 1

    def set_owner_perms(self, perms):
        perms = coerce_to_list(perms)
        perms = unique_items(perms)
        self.check_perm(perms)
        self.__owner_perms = []
        self.__owner_perms.extend(perms)
        self._p_changed = 1

    def set_group_perms(self, perms):
        perms = coerce_to_list(perms)
        perms = unique_items(perms)
        self.check_perm(perms)
        self.__group_perms = []
        self.__group_perms.extend(perms)
        self._p_changed = 1
        
    def set_other_perms(self, perms):
        perms = coerce_to_list(perms)
        perms = unique_items(perms)
        self.check_perm(perms)
        self.__other_perms = []
        self.__other_perms.extend(perms)
        self._p_changed = 1
        
    def check_perm(self, perm):
        """Raise KeyError if perm is not a valid perm"""

        perm = coerce_to_list(perm)
        for p in perm:
            if p not in HasOwnership._valid_perms:
                raise KeyError, "%s is not a valid permission" % p
                
    def get_perms(self):
        return (self.__owner_perms, self.__group_perms, self.__other_perms)

    def test_perm(self, perm, user_or_group):
        """Returns 1 if user_or_group can access resource with perm.

        Checks if id exists in owner or group lists, and if owner
        or group permissions include perm.
        
        Raises TypeError if user_or_group is not an instance of
        HasUserID or HasGroupMembership. Raises KeyError if perm
        is not in _valid_perms.
        """

        self.check_perm(perm)
        
        if user_or_group is None:
            return False

        if not isinstance(user_or_group, HasUserID) \
                and not isinstance(user_or_group, HasGroupMembership):
            raise TypeError, "%s is not an instance of HasUserID" \
                    " or HasGroupMembership" % user_or_group

        # does owner permission pass?
        
        if isinstance(user_or_group, HasUserID):
            if user_or_group in self.owners:
                if perm in self.__owner_perms:
                    return True

        # does group permission pass?

        if isinstance(user_or_group, HasGroupMembership):
            for g in user_or_group.group_list():
                if g in self.groups:
                    if perm in self.__group_perms:
                        return True

        # does other permission pass?
        return perm in self.__other_perms

    def is_owner(self, user):
        """True if user is an owner."""
        return user in self.owners

class UserActivity(QonPersistent):
    """A record of user activity.
    
    recent_blog_items = [(date, BlogItem), ...]
    recent_blog_comments = [(date, BlogItem), ...]
    recent_wiki_pages = [(date, WikiPage), ...]
    recent_wiki_comments = [(date, WikiPage), ...]
    recent_personal_comments = [(date, BlogItem), ...]
    recent_personal_news = [(date, BlogItem), ...]
    recent_participation = [(date, BlogItem), ....]
    """
    
    persistenceVersion = 2
    
    _recent_count = 50
    
    def __init__(self):
        self.__recent_blog_items = PersistentList()
        self.__recent_blog_comments = PersistentList()
        self.__recent_wiki_pages = PersistentList()
        self.__recent_wiki_comments = PersistentList()
        self.__recent_personal_comments = PersistentList()
        self.__recent_personal_news = PersistentList()
        self.__recent_participation = PersistentList()
        self.__total_pms_sent = 0

    def upgradeToVersion2(self):
        self.__total_pms_sent = 0
        self.version_upgrade_done()
    
    def upgradeToVersion1(self):
        # don't build new lists - separate upgrade function in User
        self.__recent_personal_news = PersistentList()
        self.__recent_participation = PersistentList()
        self.version_upgrade_done()
        
    def add_recent_blog_item(self, item):
        recent = self.__recent_blog_items
        recent.append((item.date, item))
        self._record_recent_participation(item)
        self.__recent_blog_items = PersistentList(recent[-self._recent_count:])

    def add_recent_blog_comment(self, comment, parent):
        recent = self.__recent_blog_comments
        recent.append((comment.date, comment, parent))
        self._record_recent_participation(parent)
        self.__recent_blog_comments = PersistentList(recent[-self._recent_count:])

    def add_recent_wiki_page(self, page):
        recent = self.__recent_wiki_pages
        recent.append((page.watchable_last_change(), page))
        self.__recent_wiki_pages = PersistentList(recent[-self._recent_count:])

    def add_recent_wiki_comment(self, comment, page):
        recent = self.__recent_wiki_comments
        recent.append((comment.date, comment, page))
        self.__recent_wiki_comments = PersistentList(recent[-self._recent_count:])
        
    def add_recent_personal_comments(self, comment, parent):
        recent = self.__recent_personal_comments
        recent.append((comment.date, comment, parent))
        self._record_recent_participation(parent)
        self.__recent_personal_comments = PersistentList(recent[-self._recent_count:])
        
    def add_recent_personal_news(self, item):
        recent = self.__recent_personal_news
        recent.append((item.date, item))
        self._record_recent_participation(item)
        self.__recent_personal_news = PersistentList(recent[-self._recent_count:])

    def new_pm_sent (self):
        self.__total_pms_sent += 1

    def get_total_pms_sent (self):
        return self.__total_pms_sent

    def _record_recent_participation(self, item):
        recent = self.__recent_participation
        if item not in recent:
            recent.append(item)
            if len(recent) > self._recent_count:
                self.__recent_participation = PersistentList(recent[-self._recent_count:])
    
    def recent_participation(self):
        """Return sorted [(date, BlogItem, ...] of most recent items user has participated in.
        
        Note: caller must filter list with can_read() and check for deleted items.
        """
        recent = [(i.watchable_last_change(), i) for i in self.__recent_participation]
        recent.sort()
        recent.reverse()
        return recent
    
    def recent_participation_for_reader(self, reader):
        """Return recent participation readable by reader."""
        return [(date, i) for date, i \
            in self.recent_participation() \
            if i.can_read(reader) and not i.is_deleted()]

    def recent_personal_news(self):
        recent = self.__recent_personal_news[:]
        recent.reverse()
        return recent

    def recent_personal_news_for_reader(self, reader):
        """Return recent personal news readable by reader: [(date, item), ...]."""
        return [(date, i) for date, i \
            in self.recent_personal_news() \
            if i.can_read(reader) and not i.is_deleted()]
    
    def recent_blog_items(self):
        recent = self.__recent_blog_items[:]
        recent.reverse()
        return recent

    def recent_blog_items_for_reader(self, reader):
        """Return recent blog items readable by reader: [(date, item), ...]."""
        return [(date, i) for date, i \
            in self.recent_blog_items() \
            if i.can_read(reader) and not i.is_deleted()]

    def recent_blog_comments(self):
        recent = self.__recent_blog_comments[:]
        recent.reverse()
        return recent

    def recent_blog_comments_for_reader(self, reader):
        """Return recent blog comments readable by reader: [(date, item, parent), ...]."""
        return [(date, i, parent) for date, i, parent \
            in self.recent_blog_comments() \
            if i.can_read(reader) and not i.is_deleted()]

    def recent_wiki_pages(self):
        recent = self.__recent_wiki_pages[:]
        recent.reverse()
        return recent
    
    def recent_wiki_pages_for_reader(self, reader):
        """Return recent wiki pages readable by reader: [(date, page), ...]."""
        return [(date, p) for date, p \
            in self.recent_wiki_pages() \
            if p.can_read(reader)]

    def recent_wiki_comments(self):
        recent = self.__recent_wiki_comments[:]
        recent.reverse()
        return recent
        
    def recent_wiki_comments_for_reader(self, reader):
        """Return recent wiki comments readable by reader: [(date, comment, page), ...]."""
        return [(date, c, p) for date, c, p \
            in self.recent_wiki_comments() \
            if p.can_read(reader) and not c.is_deleted()]

    def recent_personal_comments(self):
        recent = self.__recent_personal_comments[:]
        recent.reverse()
        return recent
    
    def recent_personal_comments_for_reader(self, reader):
        """Return recent personal comments readable by reader."""
        return [(date, i, parent) for date, i, parent \
            in self.recent_personal_comments() \
            if i.can_read(reader) and not i.is_deleted()]

    def activity_count(self, days_cutoff=3):
        """ Returns the number of 'things' the user has done in the last X days """
        cutoff_date = datetime.utcnow() - timedelta(days=days_cutoff)
        tally = 0

        lists_to_tally = (self.recent_blog_items(), self.recent_blog_comments(), self.recent_wiki_pages(), \
                          self.recent_wiki_comments(), self.recent_personal_comments())
        
        for l in lists_to_tally:
              for x in l:
                    if x[0] > cutoff_date:
                          tally += 1
                    else:
                          break     # we can do this since each list is sorted
                        
        return tally      

    def recalculate_personal_news(self, user):
        """Rebuild user's personal news cache."""
        recent = user.blog.recent_items_with_date(count=self._recent_count, consider_comments=False)
        self.__recent_personal_news = PersistentList(recent)
        
    def recalculate_participation(self):
        """Rebuild participation list."""
        
        # build best list of recent participation I have
        recent = []
        
        for date, item in self.__recent_blog_items:
            recent.append(item)
        
        for date, comment, item in self.__recent_blog_comments:
            recent.append(item)
        
        for date, comment, item in self.__recent_personal_comments:
            recent.append(item)
        
        for date, item in self.__recent_personal_news:
            recent.append(item)
        
        # get rid of duplicates
        recent = unique_items(recent)
        
        # limit to most recent items
        recent_by_date = [(i.watchable_last_change(), i) for i in recent]
        recent_by_date.sort()
        recent = recent_by_date[-self._recent_count:]
        
        self.__recent_participation = PersistentList([i for date, i in recent])
                
    def recalculate_recent_activity(self, user):
        """EXPENSIVE recalculation of all recent user activity."""
        import blog

        active_groups = get_group_database().active_groups()
        users = get_user_database().root.values()
        
        group_blogs = [g.blog for g in active_groups]
        group_wikis = [g.wiki for g in active_groups]
        user_blogs = [u.blog for u in users]
        
        # recent blog items
        recent = PersistentList([(i.date, i) for i in
            blog.recent_items_by_author(group_blogs, user, count=self._recent_count)])
        
        recent.reverse()
        self.__recent_blog_items = recent
        
        # recent blog comments
        recent = PersistentList([(i.date, i, parent) for i, parent in
            blog.recent_comments_by_author(group_blogs, user, count=self._recent_count)])
        
        recent.reverse()
        self.__recent_blog_comments = recent
        
        # recent wiki pages
        pages = []
        for wiki in group_wikis:
            pages.extend([(p.watchable_last_change(), p) for p in
                wiki.recent_edits_by_author(user, count=self._recent_count)])
        
        pages.reverse()
        self.__recent_wiki_pages = PersistentList(pages)
        del pages
        
        # recent wiki comments
        comments = []
        for wiki in group_wikis:
            comments.extend([(c.date, c, p) for p, c in
                wiki.recent_comments_by_author(user, count=self._recent_count)])
        
        comments.reverse()
        self.__recent_wiki_comments = PersistentList(comments)
        del comments
        
        # recent personal comments
        recent = PersistentList([(i.date, i, parent) for i, parent in
            blog.recent_comments_by_author(user_blogs, user, count=self._recent_count)])
        
        recent.reverse()
        self.__recent_personal_comments = recent
        
        del users
        del active_groups
        del group_blogs
        del user_blogs
            

class UserData(QonPersistent):
    """Holds extended User data, requiring less frequent access."""
    
    persistenceVersion = 6
    
    def __init__(self):
        self.__activity = UserActivity()
        self.__anon_can_read_blog = False
        self.__member_since = datetime.utcnow()
        self.__top_activity_thresh  = 2
        self.__contact_names = PersistentList()
        self.__notes = PersistentList()
        self.__total_pms_sent = 0

    def upgradeToVersion6(self):
        notes = self.get_notes()
        new_notes = []
        for date, user, msg in notes:
            new_notes.append((date, user, iso_8859_to_utf_8(msg)))
        self.__notes = PersistentList(new_notes)
        self.version_upgrade_done()
    
    def upgradeToVersion5(self):
        self.__notes = PersistentList()
        self.version_upgrade_done()

    def upgradeToVersion4(self):
        self.__contact_names = PersistentList()
        self.version_upgrade_done()

    def upgradeToVersion3(self):
        self.__top_activity_thresh  = 2
        self.version_upgrade_done()

    def upgradeToVersion2(self):
        self.__member_since = datetime.utcnow()
        self.version_upgrade_done()

    def upgradeToVersion1(self):
        self.__anon_can_read_blog = False
        
    def get_activity(self):
        return self.__activity
    
    def anon_can_read_blog(self):
        return self.__anon_can_read_blog
    
    def set_anon_can_read_blog(self, val):
        self.__anon_can_read_blog = bool(val)
        
    def member_since(self):
        return self.__member_since
    
    def set_member_since(self, dt):
        typecheck(dt, datetime)
        self.__member_since = dt
        
    def top_activity_thresh(self):
        return self.__top_activity_thresh
    
    def set_top_activity_thresh(self, val):
        val = max(1, val)
        self.__top_activity_thresh = val
        
    def save_contact_name(self, contact_name):
        """Record old contact name before overwriting it."""
        self.__contact_names.append((datetime.utcnow(), contact_name))

    def get_contact_names(self):
        return self.__contact_names[:]

    def get_notes(self):
        return self.__notes[:]

    def add_note(self, user, msg):
        self.__notes.append((datetime.utcnow(), user, msg))

class IPAddresses(QonPersistent):
    """Container to track IP addresses."""

    _resolution = timedelta(minutes=15)
    
    def __init__(self):
        self.__items = ConflictAvoidingOOBTree()
    
    def ip_hit(self, ip, dt=None):
        """Record a hit from ip at dt (or now). Only records if more than
        _resolution time has elapsed.
        """
        from qon.util import pack_ip

        try:
            packed_ip = pack_ip(ip)
        except:
            # a problem in format of ip
            return

        dt = dt or datetime.utcnow()

        last_hit = self.__items.get(packed_ip, None)
        if last_hit:
            if dt - last_hit < self._resolution:
                return

        self.__items[packed_ip] = dt
    
    def get_ips(self):
        """Return dict of [IP.Address] -> datetime, ..."""
        from qon.util import unpack_ip
        ips = {}
        for k, v in self.__items.iteritems():
            ips[unpack_ip(k)] = v
        return ips
    

class User(QonPersistent, HasUserID, HasPassword, HasGroupMembership,
    HasEmail, HasMessages, qon.karma.HasKarma, qon.karma.HasKarmaBank, qon.blog.IHasBlog, Tagger):
    """Encapsulates concept of a user"""
    
    persistenceVersion = 17
    
    idle_timeout = timedelta(minutes=30)
    idle_resolution = timedelta(minutes=5)
    signin_resolution = timedelta(minutes=60)
        
    def __init__(self, user_id=None):
        HasUserID.__init__(self)
        HasPassword.__init__(self)
        HasGroupMembership.__init__(self)
        HasEmail.__init__(self)
        HasMessages.__init__(self)
        Tagger.__init__(self)
        qon.karma.HasKarma.__init__(self)
        qon.karma.HasKarmaBank.__init__(self)
        
        if user_id is not None:
            self.set_user_id(user_id)
        self.bio = ''
        self.location = ''
        self.latitude = None
        self.longitude = None
        self.deliciousID = None
        self.flickrID = None
        self.skypeID = None
        self.blogURL = None
        self.prev_login = None
        self.last_login = None
        self.last_hit = None
        self.contact_name = None
        self.watch_list = WatchList()
        self.blog = qon.blog.Blog(self)
        self.__data = UserData()
        self.__user_agreement_accepted = False
        self.__email_notify = True
        self.__copy_self = True
        
        self.__ip_addresses = IPAddresses()

        # user_id in the keys
        self.users_to_ignore = {}

    def upgradeToVersion17(self):
        self.users_to_ignore = {}
        self.version_upgrade_done()

    def upgradeToVersion16(self):
        # The tagger mix-in now has karma
        self.tagger_upgradeToVersion1()
        self.version_upgrade_done()

    def upgradeToVersion15(self):
        if not hasattr(self, "tags"):
            Tagger.__init__(self)

    def upgradeToVersion14(self):
        Tagger.__init__(self)

    def upgradeToVersion13(self):
        self.deliciousID = None
        self.flickrID = None
        self.skypeID = None
        self.blogURL = None
        self.version_upgrade_done()
        
    def upgradeToVersion12(self):
        self.location = ''
        self.latitude = None
        self.longitude = None
        self.version_upgrade_done()        

    def upgradeToVersion11(self):
        self.__copy_self = True
        # this is a cheap upgrade of a non-persistent value,
        # so i don't mind not committing it by calling version_upgrade_done

    def upgradeToVersion10(self):
        self.bio = iso_8859_to_utf_8(self.bio)
        self.contact_name = iso_8859_to_utf_8(self.contact_name)
        
    def upgradeToVersion9(self):
        self.__ip_addresses = IPAddresses()
        self.version_upgrade_done()
    
    def upgradeToVersion8(self):
        self.get_activity().recalculate_personal_news(self)
        self.get_activity().recalculate_participation()
        self.version_upgrade_done()

    def upgradeToVersion7(self):
        qon.karma.HasKarmaBank.upgradeToVersion2(self)
        self.version_upgrade_done()

    def upgradeToVersion6(self):
        qon.message.HasMessages.upgradeToVersion1(self)
        self.version_upgrade_done()

    def upgradeToVersion5(self):
        self.__email_notify = True
        # this is a cheap upgrade of a non-persistent value,
        # so i don't mind not committing it by calling version_upgrade_done

    def upgradeToVersion4(self):
        self.__user_agreement_accepted = False
        # this is a cheap upgrade of a non-persistent value,
        # so i don't mind not committing it by calling version_upgrade_done

    def upgradeToVersion3(self):
        self.__data = UserData()
        self.__data.get_activity().recalculate_recent_activity(self)
        self.version_upgrade_done()
        
    def upgradeToVersion2(self):
        qon.karma.HasKarmaBank.upgradeToVersion1(self)
        self.version_upgrade_done()
        
    def upgradeToVersion1(self):
        self.blog = qon.blog.Blog(self)
        self.version_upgrade_done()
        
    def __str__(self):
        return '<%s object at 0x%x: %s>' % (self.__module__ + '.' + self.__class__.__name__,
            id(self), self.user_id or "*no id*")

    def get_tagger_id(self):
        return self.user_id

    def ignore_user (self, user_id):
        """ add this user to the ignore list. AKA Bozo Filter """
        self.users_to_ignore[user_id] = 1
        self._p_changed = 1

    def dont_ignore_user(self, user_id):
        if user_id in self.users_to_ignore:
            del self.users_to_ignore[user_id]
            self._p_changed = 1

    def new_user_from_email(self, email):
        """Used to create a new user given a valid e-mail address.
        
        Generates random password, user_id and returns the password.
        """
        
        email = email.lower()
        self.add_email(email)
        
        self.generate_user_id()
        return self.generate_password()
        
    def display_name_private(self):
        """Return name to display for this user, for use when displaying to the same user."""
        if self.contact_name is not None:
            return self.contact_name
        else:
            return self.get_primary_email()

    def display_name(self):
        """Returns name to display for this user"""
        if self.contact_name is not None:
            return self.contact_name
        else:
            return shroud_email(self.get_primary_email())

    def user_signed_in(self):
        """Called when user signs in"""
        self.prev_login = self.last_login
        self.last_login = datetime.utcnow()
        get_user_database().user_hit(self)
        
    def user_hit(self):
        """Notice the fact that the user has hit a page.
        """
        now = datetime.utcnow()
        if not self.last_hit or (self.last_hit < now - self.idle_resolution):
            self.last_hit = now
        
        # update login for users who never sign out
        if not self.last_login or (self.last_login < now - self.signin_resolution):
            self.user_signed_in()
        
        get_user_database().user_hit(self)
        
    def record_ip_access(self, ip):
        """Record access from ip address ip."""
        self.__ip_addresses.ip_hit(ip)
        
    def get_ip_addresses(self):
        """Return BTree of IP addresses."""
        return self.__ip_addresses.get_ips()
        
    def idle_time(self):
        if self.last_hit:
            idle = datetime.utcnow() - self.last_hit
            if idle < self.idle_timeout:
                return idle

        return None

    def is_admin(self):
        admin = get_usergroup_database().get_usergroup('admin')
        return admin in self.group_list()
        
    def is_staff(self):
        staff = get_usergroup_database().get_usergroup('staff')
        return staff in self.group_list()
        
    def get_watch_list(self):
        return self.watch_list
    
    def can_get_karma_from(self, other):
        return self is not other
        
    def notify_karma_changed(self):
        get_list_database().notify_user_changed()
        
    def notify_email_confirmed(self, email):
        get_group_database().notify_email_confirmed(self, email)
    
    def notify_authored_item(self, item):
        """Notice that I authored an item: BlogItem or WikiPage."""
        from blog import BlogItem
        from group import Group
        from wiki import WikiPage
        typecheck(item, (BlogItem, WikiPage))
        
        if isinstance(item, BlogItem):
            # only notice new BlogItems contained in Groups; otherwise
            # would catch a WikiPage's comment BlogItem. IHasBlog.notify_new_item
            # is called when an item is added to self.blog
            if isinstance(item.blog.ihb, Group):
                self.get_activity().add_recent_blog_item(item)
                
        elif isinstance(item, WikiPage):
            self.get_activity().add_recent_wiki_page(item)
            
        
    def notify_authored_comment(self, item, parent):
        """Notice that I authored a comment belonging to parent."""
        from blog import BlogItem
        from group import Group
        from wiki import WikiPage

        if not item:
            return
        
        typecheck(item, BlogItem)
        typecheck(parent, BlogItem)
        
        activity = self.get_activity()
        container = parent.blog.ihb
        typecheck(container, (Group, WikiPage, User))
        
        if isinstance(container, Group):
            activity.add_recent_blog_comment(item, parent)
        elif isinstance(container, WikiPage):
            activity.add_recent_wiki_comment(item, container)   # note not parent
        elif isinstance(container, User):
            activity.add_recent_personal_comments(item, parent)
    
    def set_contact_name(self, contact_name):
        if contact_name != self.contact_name:
            self.get_user_data().save_contact_name(self.contact_name)
            self.contact_name = contact_name
            self.notify_contact_name_changed()
    
    def notify_contact_name_changed(self):
        get_list_database().notify_user_changed()          
        
    def user_agreement_accepted(self):
        return self.__user_agreement_accepted
    
    def set_user_agreement_accepted(self, val):
        self.__user_agreement_accepted = bool(val)
        
    def can_post(self):
        """Return True unless user's karma is too low to have 'voice'."""
        return self.get_karma_score() >= qon.karma.min_karma_to_post
        
    def email_notify(self):
        return self.__email_notify
    
    def set_email_notify(self, val):
        self.__email_notify = val

    def copy_self(self):
        return self.__copy_self
    
    def set_copy_self(self, val):
        self.__copy_self = val

    def is_disabled(self):
        """Return True if user should not be allowed to sign in."""
        if hasattr(self, '_User__disabled'):
            return self.__disabled
        return False
    
    def set_disabled(self, val):
        if not val and self.is_disabled():
            del self.__disabled
        elif val and not self.is_disabled():
            self.__disabled = True
    
    # UserData methods
    
    def get_user_data(self):
        return self.__data
    
    def get_activity(self):
        """Convenience method for direct access to UserActivity."""
        return self.__data.get_activity()

    def member_since(self):
        """Convenience method for direct access to member_since."""
        return self.__data.member_since()
        
    # IHasBlog methods
    
    def blog_name(self):
        return self.display_name() + ' News'

    def can_manage(self, user):
        return (user is self)
    
    def can_edit(self, user):
        return (user is self)
    
    def can_read(self, user):
        return self.get_user_data().anon_can_read_blog() or (user is not None)
    
    def is_accepted(self):
        return True
    
    def get_owners(self):
        return [self]
    
    def is_owner(self, user):
        return (user is self)
    
    def get_blog(self):
        return self.blog
    
    def get_wiki(self):
        # users don't have wikis, return Community-General's wiki
        db = get_group_database()
        g = db.root.get('community-general', None)
        if g:
            return g.wiki
        else:
            return None
    
    def get_name(self):
        return self.display_name()
    
    def get_all_owners(self):
        return self.get_owners()
    
    def get_all_blogs(self):
        return [self.blog]
    
    def get_member_list(self):
        return []
        
    def notify_new_item(self, item):
        """Notice that I created a new personal news item."""
        get_list_database().notify_personal_news_added(item)
        self.get_activity().add_recent_personal_news(item)
        
class UserGroup(QonPersistent, HasUserID):
    """Encapsulates concept of a unix-like permissions group. Uses HasUserID for group name"""

    def __init__(self, group_id=None):
        HasUserID.__init__(self)
        if group_id is not None:
            self.set_group_id(group_id)

    get_group_id = HasUserID.get_user_id
    set_group_id = HasUserID.set_user_id

    def display_name(self):
        return str(self.get_user_id())

# --------------------------------------------------------------------

def _test():
    import doctest, user
    return doctest.testmod(user)
    
if __name__ == "__main__":
    _test()
