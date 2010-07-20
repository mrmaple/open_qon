from BTrees import OOBTree
from qon.persistent_session import DulcineaSession, DulcineaSessionManager

class QonSession(DulcineaSession):

    def __init__(self, request, id):
        DulcineaSession.__init__(self, request, id)
        
    def start_request(self, request):
        DulcineaSession.start_request(self, request)
        
    def has_info(self):
        return DulcineaSession.has_info(self)
    
    def _p_resolveConflict(self, oldState, savedState, newState):
        """User Sessions should just always take the new state in case of conflict."""
        return newState

    #is_dirty = has_info

class QonSessionManager(DulcineaSessionManager):
    
    def __init__(self, session_class=QonSession, session_mapping=None):
        DulcineaSessionManager.__init__(self, session_class, OOBTree.OOBTree())

    def commit_changes(self, session):
        DulcineaSessionManager.commit_changes(self, session)
    
    def set_session_cookie(self, request, session_id):
        """Make the session cookie persistent."""
        self._set_cookie(request, session_id, expires='Fri, 01-Jan-2014 00:00:00 GMT')
    
    def delete_session(self, session_id):
        if self.has_key(session_id):
            del self[session_id]
            
    def get_user_sessions(self, user_or_id):
        
        # get userid
        from qon.user import HasUserID
        if isinstance(user_or_id, HasUserID):
            user_id = user_or_id.get_user_id()
        else:
            user_id = user_or_id
            
        sessions = []
        for k, v in self.items():
            if v.user and v.user.get_user_id() == user_id:
                sessions.append(self[k])
                
        return sessions
