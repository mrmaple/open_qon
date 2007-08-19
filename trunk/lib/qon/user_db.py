"""
$Id: user_db.py,v 1.42 2007/05/29 15:42:04 jimc Exp $
"""
from datetime import datetime, timedelta
from qon.base import QonPersistent

from BTrees import OOBTree

from qon.database import ConflictAvoidingOOBTree
from qon.user import HasOwnership, HasUserID
from qon.util import get_oid, distance_lat_long_fast
from qon.base import transaction_commit, transaction_abort
from qon.tags import HasTags

class GenericDB(QonPersistent):
    root_class = OOBTree.OOBTree

    def __init__(self):
        self.root = self.root_class()
    
    def __getitem__(self, key):
        return self.root[key]
        
    def __setitem__(self, key, val):
        if self.root.has_key(key):
            raise KeyError, "key '%s' already exists" % key
        self.root[key] = val
        self._p_changed = 1
        
    def __delitem__(self, key):
        del self.root[key]
        self._p_changed = 1
        
    def __len__(self):
        return len(self.root)
    
    def __iter__(self):
        return iter(self.root)
        
    def __getslice__(self, i, j):
        # this is an ExtensionClass, doesn't support slices in __getitem__
        # XXX is this true since ZODB3.3a3?
        return self.root[max(0, i):max(0, j)]
        
    def __setslice__(self, i, j, seq):
        # this is an ExtensionClass, doesn't support slices in __setitem__
        # XXX is this true since ZODB3.3a3?
        self.root[max(0, i):max(0, j):] = seq
        self._p_changed = 1
        
    def __delslice__(self, i, j):
        del self.root[max(0, i):max(0, j):]
        self._p_changed = 1
        
    def has_key(self, key):
        return self.root.has_key(key)

class HitDB(GenericDB):
    """Keep track of hits by persistent objects."""
    
    persistenceVersion = 1
    
    root_class = ConflictAvoidingOOBTree
    
    _time_resolution = timedelta(minutes=5)
    
    def __init__(self):
        GenericDB.__init__(self)
        
    def upgradeToVersion1(self):
        newbt = ConflictAvoidingOOBTree()
        for k, v in self.root.iteritems():
            newbt[k] = v

        del self.root
        self.root = newbt
        
        self.version_upgrade_done()
        
    def hit(self, obj):
        """Update hit if it's older than our _time_resolution."""

        now = datetime.utcnow()
        if self.root.has_key(obj._p_oid):
            if self.root[obj._p_oid] < now - self._time_resolution:
                self.root[obj._p_oid] = now
        else:
            self.root[obj._p_oid] = now
    
    def clear_hits(self, obj):
        """Remove record of obj hits."""
        if self.root.has_key(obj._p_oid):
            del self.root[obj._p_oid]
            
    def get_hits(self, time_delta, prune=1):
        """Returns unsorted list of tuples of hits not older than time_delta.
        
        Tuples returned: (datetime, obj)...
        If prune is set, deletes items older than time_delta.
        """
        cutoff = datetime.utcnow() - time_delta
        l = []
        for k, v in self.root.items():
            if v > cutoff:
                l.append((v, get_oid(k)))
            else:
                if prune:
                    del self.root[k]
        return l

# UserDB is the list of all users in the system
#
#   The email_db is an index by e-mail for user lookup.
#
#   The tags that are applied to users are tracked as a set
# so that we can show a tag cloud of tags that have been 
# applied to users.  
class UserDB(GenericDB, HasOwnership, HasTags):

    persistenceVersion = 2
    
    def __init__(self):
        GenericDB.__init__(self)
        HasOwnership.__init__(self)
        HasTags.__init__(self)
        self.email_db = GenericDB()
        self.hit_db = HitDB()
        self.retired_users = OOBTree.OOBTree()

    def upgradeToVersion2(self):
        HasTags.__init__(self)
        self.version_upgrade_done()

    def upgradeToVersion1(self):
        self.retired_users = OOBTree.OOBTree()
        self.version_upgrade_done()
    
    def add_user(self, user):
        self[user.user_id] = user
        self._add_emails(user)
        
    def new_user_from_email(self, email):
        """Create a new user with the given e-mail. Returns (User, password)"""
        from user import User
        from base import get_usergroup_database, get_group_database
        
        email = email.lower()
        
        user = User()
        password = user.new_user_from_email(email)
        user.add_to_group(get_usergroup_database()['users'])
        
        # check user id for uniqness FIXME should be in qon.user
        while self.has_key(user.get_user_id()) or self.retired_users.has_key(user.get_user_id()):
            user.generate_user_id()
        self.add_user(user)
        
        # join user to default group
        get_group_database().notify_new_user(user)
        
        return user, password
        
    def remove_user(self, user_id):
        """Removes a user from the database. Retires user id to prevent new users from accidentally
        inheriting it.
        """
        user = self.get_user(user_id)
        if user:
            self._remove_emails(user)
            self.retired_users[user_id] = user
            del self[user_id]
        
    def user_hit(self, user):
        """Called by User when a hit is registered."""
        self.hit_db.hit(user)
        
    def get_user(self, user_id):
        """Return the user with given user_id, or None if not found."""
        return self.root.get(user_id)
        
    def get_users(self, user_id_list):
        """Given a list of user_ids, return a list of users"""
        users = [self.get_user(uid) for uid in user_id_list]
        
        # filter out None entries for invalid UIDs
        return [u for u in users if u]
        
    def get_user_by_email(self, email):
        """Look up user by e-mail. Raises KeyError if email can't be found."""
        email = email or ''

        # hack for bug where some emails could've been stored with capital letters
        uid = None
        try:
            uid = self.email_db[email.lower()]
        except KeyError:
            uid = self.email_db[email]
        return self.get_user(uid)
    
    def resolve_user(self, user_or_email):
        if isinstance(user_or_email, HasUserID):
            return user_or_email
        else:
            try:
                user = self.get_user_by_email(user_or_email)
                return user
            except KeyError:
                return None
        
    def confirm_user_email(self, user, code):
        """Attempt to confirm a user e-mail identified by code."""
        email = user.confirm_email(code)
        if email:
            self.email_db[email] = user.get_user_id()
            self._p_changed = 1
            return True
        return False
        
    def remove_user_email(self, user, email):
        """Remove given email from user and Email DB. Raises KeyError
        if attempting to remove last e-mail address.
        """
        email = email.lower()
        user.remove_email(email)
        try:
            del self.email_db[email]
        except KeyError:
            # deleting an unconfirmed e-mail, which is not in email_db
            pass
            
        self._p_changed = 1
        
    def authenticate_user(self, username, password, creation=None, nonce=None, max_age=None):
        """Attempt to authenticate user with login information (user id or email).
        Password can be plaintext, hash, or atom PasswordDigest.
        
        creation and nonce are only required if password is an Atom PasswordDigest.
        max_age (timedelta) may be passed to override default Atom expiration.
        
        Returns user if successful, None if not.
        """
        
        # try user id
        user = self.get_user(username)
        
        if not user:
            # try email
            try:
                user = self.get_user_by_email(username)
            except KeyError:
                # couldn't find user
                return None
        
        if user.valid_password(password):
            return user
        
        # try atom PasswordDigest
        if creation and nonce:
            try:
                import qon.atom
            except ImportError:
                return None
            else:
                if qon.atom.valid_password_digest(user.get_password_hash(), password, creation, nonce, max_age):
                    return user
        
        return None

    def user_age_report(self):
        """Return mapping of lists of users segmented by last sign in.
        
        # never signed in:
        d['never'] = [(user.member_since, user), ...]
        # more than xxx days old
        d['180'] = [(user.last_login, user), ...]
        d['120'] = [(user.last_login, user), ...]
        d['90'] = [(user.last_login, user), ...]
        d['30'] = [(user.last_login, user), ...]

        # less than 30 days old
        d['current'] = [(user.last_login, user), ...]

        """
        now = datetime.utcnow()

        t180 = now - timedelta(days=180)
        t120 = now - timedelta(days=120)
        t90 = now - timedelta(days=90)
        t30 = now - timedelta(days=30)
        
        d = {}
        d['never'] = []
        d['180'] = []
        d['120'] = []
        d['90'] = []
        d['30'] = []
        d['current'] = []
        for user_id, user in self.root.iteritems():
            if not user.last_login:
                # never signed in
                d['never'].append((user.member_since(), user))
            elif user.last_login < t180:
                d['180'].append((user.last_login, user))
            elif user.last_login < t120:
                d['120'].append((user.last_login, user))
            elif user.last_login < t90:
                d['90'].append((user.last_login, user))
            elif user.last_login < t30:
                d['30'].append((user.last_login, user))
            else:
                d['current'].append((user.last_login, user))

        return d

    def _add_emails(self, user):
        userid = user.get_user_id()
        for email in user.email_list():
            self.email_db[email] = userid
        self._p_changed = 1
    
    def _remove_emails(self, user):
        for email in user.email_list():
            del self.email_db[email]
        self._p_changed = 1

    def get_user_distances(self, latitude, longitude):
        return_list = []
        for user_id, user in self.root.iteritems():
            if user.latitude is not None and user.longitude is not None:
                return_list.append((user, distance_lat_long_fast(latitude, longitude, user.latitude, user.longitude)))
        return return_list
        
        
class UserGroupDB(GenericDB, HasOwnership):

    def __init__(self):
        GenericDB.__init__(self)
        HasOwnership.__init__(self)
        
    def add_usergroup(self, group):
        self[group.get_group_id()] = group
        
    def remove_usergroup(self, groupID):
        del self[groupID]
        
    def get_usergroup(self, groupID):
        return self.root.get(groupID)
        

class MiscDB(GenericDB):
    """Holder for miscellaneous databases. Used to cleanly add new databases."""
    
    def __init__(self):
        GenericDB.__init__(self)
        
        from qon.observe import ObserveDB
        self['observe_db'] = ObserveDB()
    
    def get_observe_database(self):
        return self['observe_db']

def clean_email_db():
    """Remove lingering entries in email db that don't map to current users."""
    from base import get_user_database
    
    user_db = get_user_database()
    
    for email, user_id in user_db.email_db.root.iteritems():
        user = user_db.get_user(user_id)
        if email not in user.email_list():
            print "%s is no longer associated with %s, removing." % (email, user.display_name())
            del user_db.email_db[email]

def upgrade_misc_db():
    from qon.base import get_root, get_database
    
    root = get_root()
    if not root.has_key('misc_db'):
        get_database().init_root('misc_db', 'qon.user_db', 'MiscDB')

def upgrade_internal_users_expiring_passwords():
    """Set internal users to have expiring passwords."""
    from qon.base import get_user_database
    from qon.ui import blocks
    
    user_db = get_user_database()
    for user_id, user in user_db.root.iteritems():
        if blocks.util.is_internal_user(user):
            user.set_expiring_password(True)

def fix_broken_user_data_caches():
    """Scans all users to check if any of their user data caches are
    inaccurate, or worse, reference deleted groups."""
    from qon.base import get_user_database, get_group_database
    
    user_db = get_user_database()
    group_db = get_group_database()
    i = 0
    for user_id, user in user_db.root.iteritems():
        i += 1
        # print "%d) %s" % (i, user_id)

        # check/fix owned groups        
        if hasattr(user, '_group_owned_groups'):
            real_owned_groups = [group_db[group] for group in group_db.root.keys() \
                if group_db[group].is_owner(user)]
            if real_owned_groups != user._group_owned_groups:
                print "%s's _group_owned_groups isn't accurate" % user_id
                for g in user._group_owned_groups:
                    if not group_db.has_key(g.get_user_id()):
                        print "-%s's _group_owned_groups references deleted group %s" % (user_id, g.get_user_id())

                # fix it!                        
                user._group_owned_groups = real_owned_groups

        # check/fix member groups                
        if hasattr(user, '_group_member_groups'):
            real_member_groups = [group_db[group] for group in group_db.root.keys() \
                if group_db[group].is_member(user, slow=True)]            
            if real_member_groups != user._group_member_groups:
                print "%s's _group_member_groups isn't accurate" % user_id
                for g in user._group_member_groups:
                    if not group_db.has_key(g.get_user_id()):
                        print "-%s's _group_member_groups references deleted group %s" % (user_id, g.get_user_id())

                # fix it                        
                user._group_member_groups = real_member_groups
