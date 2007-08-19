"""
$Id: ticket.py,v 1.15 2007/01/21 17:02:12 jimc Exp $
"""
import sys
from datetime import datetime
from persistent.list import PersistentList
from qon.base import QonPersistent
from qon.watch import Watchable, never
from qon.util import iso_8859_to_utf_8

class TicketTracker(QonPersistent, Watchable):
    """A ticket/issue tracking system."""

    persistenceVersion = 2
    
    def __init__(self, name='', group=None):
        Watchable.__init__(self)
        self.group = group
        self.name = name
        self.modified = never
        self.__items = PersistentList()
        self.__categories = PersistentList()

    def upgradeToVersion1(self):
        self.name = iso_8859_to_utf_8(self.name)
        
    def add_category(self, category):
        if category not in self.__categories:
            self.__categories.append(category)
        
    def remove_category(self, category):
        if category in self.__categories:
            self.__categories.remove(category)
        
    def get_categories(self, sorted=0):
        cats = self.__categories[:]
        if sorted:
            cats.sort()
        return cats
        
    def add_ticket(self, ticket):
        self.__items.append(ticket)
        self.modified = datetime.utcnow()
        self.watchable_changed(self.modified)
        
    def new_ticket(self, user, title='', category="feature", priority = 3, text=''):
        """Create a new ticket and return it."""
        ticket = Ticket(user, title, category, priority, text)
        self.add_ticket(ticket)
        user.karma_activity_credit()
        return ticket
        
    def get_ticket(self, id):
        """Return a ticket with the given id (index)."""
        return self.__items[id]
                
    def get_index(self, ticket):
        """Return index of ticket. Uses cached value if available."""
        if hasattr(ticket, '_v_index'):
            return ticket._v_index
        else:
            return self.__items.index(ticket)
            
    def new_tickets(self):
        """Return new tickets."""
        return self._tickets_by_state(['new'])

    def open_tickets(self):
        """Return open tickets."""
        return self._tickets_by_state(['open'])
        
    def closed_tickets(self):
        """Return closed tickets."""
        return self._tickets_by_state(['closed'])
        
    def active_tickets(self):
        """Return tickets not new or closed."""
        return self._tickets_by_state(['open', 'assigned', 'feedback'])
        
    def owned_tickets(self, user, only_open=0):
        """Return tickets owned (submitted) by user."""
        items = []
        for i, t in enumerate(self.__items):
            if t.user is user and (not only_open or not t.is_closed()):
                t._v_index = i
                items.append(t)
        return items        
        
    def assigned_tickets(self, user, only_open=0):
        """Return tickets assigned to user, regardless of state."""
        items = []
        for i, t in enumerate(self.__items):
            if t.assignee is user and (not only_open or not t.is_closed()):
                t._v_index = i
                items.append(t)
        return items        
        
    def feedback_tickets(self, user, only_open=0):
        """Return tickets awaiting feedback from user."""
        items = []
        for i, t in enumerate(self.__items):
            if t.is_feedback() and (t.user is user) and (not only_open or not t.is_closed()):
                t._v_index = i
                items.append(t)
        return items        
        
    def only_open(self, tickets):
        """Given a list of tickets, eliminate closed tickets."""
        return [t for t in tickets if not t.is_closed()]
        
    def sort_by_modified(self, tickets):
        """Given a list of tickets, return sorted newest to oldest by modified."""
        bydate = [(t.modified or t.date, t) for t in tickets]
        bydate.sort()
        bydate.reverse()
        return [t for date, t in bydate]
        
    def last_modified(self):
        """Compute and cache last_modified from tickets.
        """
        if self.modified:
            return self.modified
            
        latest = never
        for t in self.__items:
            if t.modified > latest:
                latest = t.modified
                
        self.modified = latest
        return self.modified
        
    def watchable_name(self):
        return self.name
        
    def watchable_modified_date(self):
        return self.last_modified()
        
    # ticket methods
    
    def add_comment(self, ticket, user, category, priority, text):
        ticket.add_comment(user, category, priority, text)
        self.modified = datetime.utcnow()
        self.watchable_changed(self.modified)
 
    def change_status(self, ticket, user, status, category, priority, text):
        ticket.change_status(user, status, category, priority, text)
        self.modified = datetime.utcnow()
        self.watchable_changed(self.modified)        
        
    def _tickets_by_state(self, state):
        items = []
        for i, t in enumerate(self.__items):
            if t.status in state:
                t._v_index = i
                items.append(t)
        return items

class Ticket(QonPersistent):
    """A single ticket/issue.
    """

    persistenceVersion = 2
    
    _valid_states = [
        'new',          # newly created
        'open',         # opened for review
        'assigned',     # assigned to staff for work
        'feedback',     # awaiting feedback from originator
        'closed',       # closed        
        ]
    _categories = ["bug", "feature"]
    _priorities = range(1, 6)

    def __init__(self, user, title='', category="feature", priority=3, text=''):
        """Create a new ticket submitted by user with title and text."""
        self.user = user
        self.title = title
        self.text = text
        self.date = datetime.utcnow()
        self.modified = None
        self.status = 'new'
        self.assignee = None
        self._v_index = None

        self.priority = priority
        if category in self._categories:
            self.category = category
        else:
            raise ValueError

    def upgradeToVersion2(self):
        self.priority = 3
        if self.title.lower().find("feature") != -1:
            self.category = "feature"
        else:
            self.category = "bug"

    def upgradeToVersion1(self):
        self.title = iso_8859_to_utf_8(self.title)
        self.text = iso_8859_to_utf_8(self.text)
        
    def add_comment(self, user, category, priority, text, extra_header=''):
        """Add a comment to an existing ticket. Simply appends a separator
        line and text."""
        if text is None:
            text = ''
        self.modified = datetime.utcnow()

        from ui.blocks.util import format_datetime    
        date = format_datetime(self.modified)

        self.category = category
        self.priority = priority
        
        if self.text is None:
            self.text = ''
            
        self.text += '\n\n' + ('-' * 40) + '\n' + \
            'Comment by: %s\n' % user.display_name() + \
            'Date: %s\n' % date + \
            extra_header + \
            '\n' + \
            text.strip()
            
        user.karma_activity_credit()
            
    def change_status(self, user, status, category, priority, text=''):
        """Change ticket status, with comment."""
        if status not in self._valid_states:
            raise ValueError
            
        self.status = status
        self.category = category
        self.priority = priority

        # this is only called when the status has changed.
        if status == 'assigned':
            self.assign_to(user)
        self.add_comment(user, category, priority, text, 'Status changed to: %s\n' % status)

    def open_ticket(self):
        self.status = 'open'
        
    def assign_to(self, user):
        self.assignee = user
        self.status = 'assigned'
        
    def await_feedback(self):
        self.status = 'feedback'
        
    def close_ticket(self):
        self.status = 'closed'
        
    def get_index(self):
        """Return my index within my tracker, or sys.maxint if I don't know it.
        
        Should only be called after one of TicketTracker's following methods:
        new_tickets, open_tickets, closed_tickets, active_tickets, owned_tickets
        which set _v_index.
        """
        if hasattr(self, '_v_index'):
            return self._v_index
        else:
            return sys.maxint

    def is_new(self):
        return self.status == 'new'
        
    def is_open(self):
        return self.status == 'open'
        
    def is_closed(self):
        return self.status == 'closed'
        
    def is_assigned(self):
        return self.status == 'assigned'
        
    def is_feedback(self):
        return self.status == 'feedback'

    def is_feature(self):
        return self.category == "feature"

    def is_bug(self):
        return self.category == "bug"
    
