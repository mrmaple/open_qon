"""
$Id: message.py,v 1.10 2004/11/24 16:15:11 jimc Exp $

Messages
"""
from datetime import datetime, timedelta
from persistent.list import PersistentList

from qon.base import QonPersistent

class HasMessages:
    """Mixin class providing message/inbox management."""
    
    __persistenceVersion = 1
    
    _purge_age = timedelta(days=7)      # days messages stay in trash
    _trash_age = timedelta(days=30)     # days messages stay in inbox
    
    def __init__(self):
        self.__message_list = PersistentList()
        
    def upgradeToVersion1(self):
        pl = PersistentList(self.__message_list)
        self.__message_list = pl
        
    def has_messages(self):
        return len(self.__message_list) > 0
        
    def new_messages(self):
        return [msg for msg in self.__message_list \
            if msg.status == 'new']
            
    def old_messages(self):
        return [msg for msg in self.__message_list \
            if msg.status == 'read']

    def deleted_messages(self):
        return [msg for msg in self.__message_list \
            if msg.status == 'deleted']
            
    def add_message(self, msg):
        self.__message_list.append(msg)
        
    def trash_old_messages(self):
        """Call periodically to move old messages, read and undread, to trash."""
        cutoff = datetime.utcnow() - self._trash_age
        for msg in self.__message_list:
            if msg.status != 'deleted':
                if msg.date < cutoff:
                    msg.delete()
    
    def purge_old_messages(self):
        """Call periodically to permanently delete old messages out of trash."""
        cutoff = datetime.utcnow() - self._trash_age - self._purge_age
        for msg in self.deleted_messages():
            if (msg.date_opened or msg.date) < cutoff:
                self.__message_list.remove(msg)
            
    def message_index(self, msg):
        return self.__message_list.index(msg)
        
    def get_message(self, index):
        return self.__message_list[index]
            
class Message(QonPersistent):

    _valid_states = ['new', 'read', 'deleted']

    def __init__(self, sender, subject, body):
        self.status = 'new'
        self.sender = sender
        self.subject = subject
        self.body = body
        self.date = datetime.utcnow()
        self.date_opened = None
        
    def read(self):
        """Marks a message as read."""
        if self.status == 'new':
            self.date_opened = datetime.utcnow()
            self.status = 'read'
        
    def delete(self):
        self.status = 'deleted'

    def undelete(self):
        self.status = 'read'

    def is_deleted(self):
        return self.status == 'deleted'
        
    def get_body(self):
        return self.body
        
    def get_subject(self):
        return self.subject
        
    def get_sender(self):
        return self.sender
        
    def get_date(self):
        return self.date
        
class LinkedMessage(Message):
    """A message that is simply a link to another Message, but maintains
    its own read/unread status."""
    
    def __init__(self, original):
        Message.__init__(self, None, None, None)
        self.original = original

    def get_body(self):
        return self.original.get_body()
        
    def get_subject(self):
        return self.original.get_subject()

    def get_sender(self):
        return self.original.get_sender()
        
    def get_date(self):
        return self.original.get_date()

