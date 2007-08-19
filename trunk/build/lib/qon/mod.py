"""
$Id: mod.py,v 1.10 2004/05/18 22:39:54 jimc Exp $
:Author:    Jim Carroll

Provides Sponsored, Voteable and VoteableQueue.
"""
from datetime import datetime, timedelta
from persistent.list import PersistentList
from BTrees import OOBTree
from dulcinea.typeutils import typecheck
from qon.base import QonPersistent
from qon.user import User

class InvalidState(Exception):
    """Invalid state or state transition"""
    
class VotingClosed(Exception):
    """Voting is closed, no more votes."""
    
class HasState:
    """Mixin class for stated objects."""
    _valid_states = ['new', 'pending', 'accepted']
    
    def __init__(self):
        self.__state = 'new'

    def get_state(self):
        return self.__state
    
    def set_state(self, state):
        if state not in self._valid_states:
            raise InvalidState, "%s is not a valid state." % state
        self.__state = state

    def is_accepted(self):
        return self.__state == 'accepted'
    
class Sponsored(HasState):
    """Mixin class for sponsored objects.
    
    Refactored out of Voteable.
    """
    def __init__(self, min_sponsors=1):
        HasState.__init__(self)
        self.min_sponsors = min_sponsors
        self.__sponsors = PersistentList()

    def add_sponsor(self, sponsor):
        if sponsor not in self.__sponsors:
            self.__sponsors.append(sponsor)
        
    def get_sponsors(self):
        return self.__sponsors
    
    def enough_sponsors(self):
        return len(self.__sponsors) >= self.min_sponsors

    def set_pending(self):
        """Transition from new to pending state. Awaiting more sponsors."""
        if self.get_state() != 'new':
            raise InvalidState, "cannot transition to pending from '%s' state." % self.get_state()
        
        self.set_state('pending')

    def force_accept(self):
        """Force into accepted state, regardless of vote or status."""
        self.set_state('accepted')
    
    def is_sponsor(self, user):
        return user in self.__sponsors
        
class SponsoredQueue(QonPersistent):
    """A queue to keep Sponsored items that are in pending state.
    
    Code refactored out of Voteable.
    """
    def __init__(self):
        self.queue = PersistentList()

    def add_to_queue(self, item):
        self.queue.append(item)

    def remove_from_queue(self, item):
        if item in self.queue:
            self.queue.remove(item)

    def add_sponsor(self, item, sponsor):
        """Add sponsor to item."""
        item.add_sponsor(sponsor)
        if item.enough_sponsors():
            self.force_accept(item)

    def get_items_by_state(self, state):
        items = [item for item in self.queue if item.get_state() == state]
        return items

    def new_items(self):
        return self.get_items_by_state('new')
        
    def pending_items(self):
        return self.get_items_by_state('pending')
    
    def force_accept(self, item):
        item.force_accept()
        self.remove_from_queue(item)


# ----------------------------------------------------------------
# Everything below here is legacy code that is not in production.
# ----------------------------------------------------------------
        
class _Voteable(Sponsored):
    """Mixin class for objects subject to basic moderation (for/against)
    
    states: new:        item just created
            pending:    awaiting additional info (e.g. sponsors) before
                        voting
            voting:     item is being voted upon
            accepted:   item accepted
            rejected:   item rejected
            limbo:      item neither accepted nor rejected, in limbo
            
    Before a vote is cast, caller must verify that voting is still open.
    """
    
    _valid_states = ['new', 'pending', 'voting', 'accepted', 'rejected', 'limbo']
    
    def __init__(self, min_sponsors=1):
        Sponsored.__init__(self, min_sponsors=min_sponsors)
        self.__created = datetime.utcnow()
        self.__queued = None
        self.__unqueued = None
        self.__start_voting = None
        self.__end_voting = None
        self.__votes_for = []
        self.__votes_against = []
        self.__votes_abstain = []
        self.__votes_cast = OOBTree.OOBTree()
    
    def open_voting(self, end_datetime):
        """Begin voting."""
        
        if self.get_state() != 'new' and self.get_state() != 'pending' and self.get_state() != 'limbo':
            raise InvalidState, "cannot begin voting, invalid state."
            
        if not self.enough_sponsors():
            raise ValueError, "not enough sponsors"
        
        self.__start_voting = datetime.utcnow()
        self.__end_voting = end_datetime
        self.set_state('voting')
        
        self._register_sponsor_votes()
        
    def _register_sponsor_votes(self):
        for s in self.get_sponsors():
            self.vote(s, 'for')
        
    def voting_open(self):
        return self.get_state() == 'voting' and datetime.utcnow() < self.__end_voting
    
    def voting_ends(self):
        return self.__end_voting
        
    def voted(self, user):
        """Return user's vote or None if no vote yet"""
        if self.__votes_cast.has_key(user):
            return self.__votes_cast[user]
        else:
            return None
        
    def vote(self, user, vote):
        """Record a vote. vote: ['for', 'against', 'abstain']. Raises VotingClosed
        if voting is over. If VotingClosed is raised, caller must inform
        VoteableQueue.voting_closed()
        """
        typecheck(vote, str)
        self._check_vote_status(user, vote)
        vote_list = self._get_vote_list(vote)            
        vote_list.append(user)
        self._p_changed = 1
        
    def unvote(self, user):
        """Remove a user's vote"""
        if self.__votes_cast.has_key(user):
            vote = self.__votes_cast[user]
            del self.__votes_cast[user]
            self._get_vote_list(vote).remove(user)
            self._p_changed = 1
                
    def _get_vote_list(self, vote):
        if vote == 'for':
            vote_list = self.__votes_for
        elif vote == 'against':
            vote_list = self.__votes_against
        elif vote == 'abstain':
            vote_list = self.__votes_abstain
        else:
            raise ValueError, '%s is not a recognized vote.' % vote
        return vote_list
                
    def _check_vote_status(self, user, vote):
        typecheck(user, User)
        if self.get_state() != 'voting':
            raise InvalidState, "not in voting state."

        if self.__votes_cast.has_key(user):
            raise KeyError, "already voted."
        
        if datetime.utcnow() > self.__end_voting:
            self.close_voting()
            raise VotingClosed, "voting is over."
            
        self.__votes_cast[user] = vote
        self._p_changed = 1
        
    def get_votes_for(self):
        return self.__votes_for
        
    def get_votes_against(self):
        return self.__votes_against
        
    def get_votes_abstain(self):
        return self.__votes_abstain
        
    def for_count(self):
        return len(self.__votes_for)
    
    def against_count(self):
        return len(self.__votes_against)
        
    def abstain_count(self):
        return len(self.__votes_abstain)
        
    def close_voting(self):
        """Close voting, compute results, and move to appropriate state."""
        if self.get_state() != 'voting':
            raise InvalidState, "cannot close voting, invalid state."
            
        votes_for = len(self.__votes_for)
        votes_against = len(self.__votes_against)
            
        if votes_for > votes_against:
            self.set_state('accepted')
        elif votes_against > votes_for:
            self.set_state('rejected')
        else:
            self.set_state('limbo')
            
        # empty votes_cast mapping to free memory
        self.__votes_cast = OOBTree.OOBTree()
        
    def force_accept(self):
        """Force into accepted state, regardless of vote or status."""
        self.set_state('accepted')
        self.__votes_cast = OOBTree.OOBTree()
        
    def set_queued_datetime(self, datetime):
        self.__queued = datetime

    def set_unqueued_datetime(self, datetime):
        self.__unqueued = datetime

        
class _VoteableQueue(SponsoredQueue):
    """A moderation/voteable queue.
    
    Voteable items are added to this queue when they are created, to await
    moderation from members.
    
    This queue manages a voting process using the Voteable class.
    
    In order to begin voting, a minimum number of sponsors is required. The
    minimum is set on the Voteable instance.
    
    A separate ModQueue should be used for each different class of items.
    
    Once voting is complete, items are removed from the queue. Caller must ensure
    items is placed in correct database.
    """
    
    _voting_duration = timedelta(days=7)
    
    def __init__(self):
        SponsoredQueue.__init__(self)
        self.accepted = PersistentList()
        self.rejected = PersistentList()
        
    def add_to_queue(self, item):
        SponsoredQueue.add_to_queue(self, item)
        item.set_queued_datetime(datetime.utcnow())
        self._check_enough_sponsors(item)
        
    def remove_from_queue(self, item):
        SponsoredQueue.remove_from_queue(self, item)
        item.set_unqueued_datetime(datetime.utcnow())
        
    def voting_items(self):
        return self.get_items_by_state('voting')
        
    def add_sponsor(self, item, sponsor):
        """Add sponsor to item. If minimum number of sponsors is attained, begin
        voting."""
        SponsoredQueue.add_sponsor(self, item, sponsor)
        self._check_enough_sponsors(item)

    def _check_enough_sponsors(self, item):
        if item.enough_sponsors():
            item.open_voting(datetime.utcnow() + self._voting_duration)
        
    def voting_closed(self, item):
        """Call this when Votable.vote raises VotingClosed."""
        state = item.get_state()
        if state == 'accepted':
            self._item_accepted(item)
        elif state == 'rejected':
            self._item_rejected(item)
        elif state == 'limbo':
            self._item_tied(item)
            
        self.remove_from_queue(item)
        self._p_changed = 1
            
    def _item_accepted(self, item):
        self.accepted.append(item)
        self._p_changed = 1
        
    def _item_rejected(self, item):
        self.rejected.append(item)
        self._p_changed = 1
    
    def _item_tied(self, item):
        self._item_rejected(item)
        self._p_changed = 1
