"""$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/dulcinea/lib/persistent_session.py $
$Id: persistent_session.py,v 1.4 2004/05/09 06:27:02 jimc Exp $

Provides versions of Quixote's session management classes that
work with ZODB.
"""

from time import time

from quixote.session import SessionManager as QuixoteSessionManager
from quixote.session import Session as QuixoteSession

from persistent.list import PersistentList
from persistent.mapping import PersistentMapping

from base import QonPersistent, transaction_commit

class DulcineaSession (QonPersistent, QuixoteSession):
    """
    Instance attributes:
      _form_tokens : PersistentList [string]
        (overrides Session's attribute for persistence)
      user : User
        (overrides Session's attribute for stronger typing)
        the user object used for access control checks.  Usually
        user == actual_user, but when an admin user is acting as some other
        user, user is the person being impersonated, and actual_user is
        the person actually doing the work (ie.  the admin user)
      actual_user : User
        (see user attribute)
    """

    __Session_init = QuixoteSession.__init__

    def __init__ (self, request, id):
        self.__Session_init(request, id)
        self.user = None
        self.actual_user = None
        self._form_tokens = PersistentList()

    def __str__ (self):
        # override Session.__str__ to take actual_user into account
        if self.actual_user is None:
            return "session %s (no user)" % self.id
        elif self.user == self.actual_user:
            return "session %s (user %s)" % (self.id, self.user)
        else:
            return "session %s (user %s acting as %s)" % (self.id,
                                                          self.actual_user,
                                                          self.user)
    def clear_app_state(self):
        """Override to clear any session data when acting as another user
        """
        pass

    def has_info (self):
        if self.actual_user or self.user or self._form_tokens:
            return 1
        else:
            return 0

    def set_actual_user (self, user):
        self.user = self.actual_user = user


class DulcineaSessionManager (QonPersistent, QuixoteSessionManager):
    """
    Instance attributes:
      sessions : PersistentMapping { session_id:string : DulcineaSession }
        (same as in SessionManager, just made persistent)
    """

    __SessionManager_init = QuixoteSessionManager.__init__
    __SessionManager_get_session = QuixoteSessionManager.get_session

    ACCESS_TIME_RESOLUTION = 900 # in seconds (don't dirty the session on
                                 # every hit)

    def __init__ (self, session_class=DulcineaSession, session_mapping=None):
        if session_mapping is None:
            session_mapping = PersistentMapping()
        self.__SessionManager_init(session_class=session_class,
                                   session_mapping=session_mapping)

    def get_sessions(self):
        return self.sessions.values()

    def sorted_keys (self):
        keys = list(self.sessions.keys())
        keys.sort()
        return keys

    def forget_changes (self, session):
        get_transaction().abort()

    def commit_changes (self, session):
        transaction_commit(None, 'DulcineaSessionManager.commit_changes')

    def del_sessions (self, ip=None, age=None):
        """Delete a subset of open sessions selected according to the
        keyword arguments.  Default values delete all sessions.  Sessions
        are selected by combining non-None keyword args with "and": eg. if
        'ip' and 'age' are non-None then any session matching *both* the
        supplied IP address and age (hours since session was accessed) is
        deleted.

        'ip' specifies an IP address (dotted-quad string); it must match
        the IP address of a session exactly.  'age' is the session's age
        (since last access) in hours; any session older than 'age' will
        pass the age test.

        The number of sessions deleted is returned.
        """
        deleted = 0
        now = time()
        for s in list(self.sessions.values()):
            if ip is not None and ip != s.get_remote_address():
                continue
            if age is not None and s.get_access_age(_now=now) < age*3600:
                continue

            # passed all the tests: we'll delete this sucker
            deleted += 1
            del self.sessions[s.id]

        return deleted




