"""
$Id: poll.py,v 1.14 2005/08/03 08:06:17 alex Exp $

"""

# enable rollout test code
_ROLLOUT_TEST = False

from datetime import datetime, timedelta
from persistent.list import PersistentList
from BTrees import OOBTree
from qon.base import QonPersistent, PersistentCache
from qon.watch import Watchable
from qon.util import CompressedText, pack_user_id, unpack_user_id, iso_8859_to_utf_8
from qon.karma import NoKarmaToGive


class PollContainer(QonPersistent, Watchable):
    """Maintains list of Poll items for a Group."""
    
    _karma_new_item = 1     # cost to create a new poll
    
    def __init__(self, ihb):
        """Create a Polls belonging to an IHasBlog."""
        Watchable.__init__(self)
        self.ihb = ihb
        self.__polls = PersistentList()
    
    def can_pay_for_new_item(self, user):
        if not user:
            return False
        return user.can_give_karma(self._karma_new_item)
        
    def add_poll(self, poll):
        """Add new Poll. Returns None if poll was not added."""
        
        if not _ROLLOUT_TEST:
            # charge creator for item - don't create if can't pay
            try:
                poll.creator.pay_karma(self._karma_new_item)
            except NoKarmaToGive:
                return None
            
        # karma credit
        poll.creator.karma_activity_credit()

        self.__polls.append(poll)
        
        # set Poll's refs back to me
        poll.container = self
        poll._set_item_index(self.__polls.index(poll))
        
        self.watchable_changed(poll.date)
        poll.creator.karma_activity_credit()
        return poll
    
    def get_poll(self, index):
        try:
            return self.__polls[index]
        except IndexError:
            return None
    
    def active_polls(self):
        """Return list of active polls [(end_date, poll), ...], sorted by most-recent end date."""
        now = datetime.utcnow()
        bydate = [(p.end_date, p) for p in self.__polls if p.is_active(now)]
        bydate.sort()
        return bydate
    
    def completed_polls(self):
        """Return list of completed polls [(end_date, poll), ...] sorted by most recent end date."""
        now = datetime.utcnow()
        bydate = [(p.end_date, p) for p in self.__polls if not p.is_active(now)]
        bydate.sort()
        bydate.reverse()
        return bydate

    def get_polls(self):
        return self.__polls
    
    def watchable_name(self):
        return self.ihb.name + ' Polls'

    def watchable_changed(self, now=None):
        # tells group he has changed, too
        Watchable.watchable_changed(self, now)
        self.ihb.watchable_changed(now)

class PollData(QonPersistent):
    """Container for settings and results of a Poll."""

    persistenceVersion = 1
    
    def __init__(self, choices):
        """Creates default set of settings. choices is a list of strings.
        
        Raises KeyError if choices list contains duplicate strings.
        """
        
        seen = {}
        for c in choices:
            if seen.has_key(c):
                raise KeyError
            seen[c] = 1
        
        self.choices = PersistentList(choices)
        
        # Min/Max choices voter must choose
        self.min_choice = 1
        self.max_choice = 1
        
        # Record of votes
        self.votes = OOBTree.OOBTree()
        
        # Who can vote: owner, member, all
        self.vote_access = 'all'
        
        # Who can see final results: owner, member, all
        self.results_access = 'all'
        
        # Who can see intermediate results: owner, member, all, none
        self.intermediate_access = 'none'
        
        # Vote required to view intermediate results
        self.vote_required_to_view = True
        
        # Vote revisable
        self.voter_can_revise = False
        
        # Voters displayed in final results: anon, log_only, full
        #  2005-04-07 changed from what used to be simply a boolean
        self.display_voters = 'anon'
        
        # Min karma required to vote
        self.min_karma = 0
        
        # Cost to cast a vote
        self.karma_cost = 1
        
        # cached tally total
        self.__cached_tally = None


    def upgradeToVersion1(self):
        # convert boolean value to none or full
        if self.display_voters:
            self.display_voters = 'full'
        else:
            self.display_voters = 'anon'
        self.version_upgrade_done()
            
    def set_extended_data(self, custom_dict):
        """Set attributes based on custom_dict."""
        for k, v in custom_dict.iteritems():
            if hasattr(self, k):
                setattr(self, k, v)
            else:
                raise KeyError
            
    def has_voted(self, user):
        """Return True if user is in votes tree."""
        if not user:
            return False
        return self.votes.has_key(pack_user_id(user.get_user_id()))
        
    def choices_valid(self, choices):
        """Return True if choices are valid for this vote."""
        
        num_choices = len(choices)
        if (num_choices < self.min_choice) or (num_choices > self.max_choice):
            return False
        
        # check that choices fall within range
        max_index = len(self.choices) - 1
        for i in choices:
            if (i < 0) or (i > max_index):
                return False
        
        return True
        
    def record_vote(self, user, choices):
        """Record a users vote. Choices is a list of choice indicies mapping
        to self.choices list. Assumes user access permissions are valid, but
        checks choices for validity.
        
        Raises ValueError if choices are invalid.
        Raises KeyError if user is not allowed to re-vote.
        
        """
        
        if not self.choices_valid(choices):
            raise ValueError
            
        packed_user_id = pack_user_id(user.get_user_id())
        
        if not self.voter_can_revise and self.votes.has_key(packed_user_id):
            raise KeyError
        
        self.votes[packed_user_id] = PersistentList(choices)
        self.__cached_tally = None
        
    def user_vote(self, user):
        """Return copy of user's vote choices. Raises KeyError if none recorded."""
        packed_user_id = pack_user_id(user.get_user_id())
        
        if not self.votes.has_key(packed_user_id):
            raise KeyError
        
        return self.votes[packed_user_id][:]
    
    def num_votes_cast(self):
        return len(self.votes.keys())
    
    def tally_choices(self):
        if not self.__cached_tally:
            totals = [0 for c in self.choices]
            for p_user_id, votes in self.votes.iteritems():
                for v in votes:
                    totals[v] += 1
            self.__cached_tally = totals
        return self.__cached_tally
    
    def user_votes(self):
        vote_data = {}
        for p_user_id, votes in self.votes.iteritems():
            vote_data[unpack_user_id(p_user_id)] = votes
        return vote_data
    
class Poll(QonPersistent, Watchable):
    """A single Poll."""

    persistenceVersion = 1
    
    def __init__(self, creator, title, description, end_date, choices):
        """Create a poll. Choices is a list of strings."""
        
        Watchable.__init__(self)
        
        # PollContainer (set by container when added)
        self.container = None
        
        # User who created poll
        self.creator = creator
        
        # Date created/modified
        self.date = datetime.utcnow()
        
        # End date
        self.end_date = end_date
        
        # Title/Description
        self.title = title
        self.__description = CompressedText(description)
        self.__cached_html = PersistentCache(self._update_html_cache)
        
        # Other settings and vote data
        self.__data = PollData(choices)
        
        # cache of PollData items
        self.__num_votes_cast = None
        
        # poll index within container
        self.__item_index = None

    def upgradeToVersion1(self):
        self.title = iso_8859_to_utf_8(self.title)
        
    def get_data(self):
        return self.__data
    
    def get_description(self):
        return self.__description.get_raw()
    
    def set_description(self, raw):
        self.__description.set_raw(raw)
        self.invalidate_html_cache()
        
    def has_voted(self, user):
        """True if user has already voted."""
        return self.__data.has_voted(user)
        
    def user_vote(self, user):
        try:
            return self.__data.user_vote(user)
        except KeyError:
            return []

    def user_vote_choices(self, user):
        """Return list of strings representing user's choices."""
        choices = self.user_vote(user)
        
        pd = self.get_data()
        votes = []
        for v in choices:
            votes.append(pd.choices[v])
        
        return votes
    
    def user_votes_choices(self):
        """Returns dict of {user_id: [string1, string2, ...]} of user votes."""
        vote_choice_data = self.__data.user_votes()
        
        vote_data = {}
        for user_id, choices in vote_choice_data.iteritems():
            vote_data[user_id] = [self.__data.choices[i] for i in choices]
        return vote_data

    def is_active(self, as_of=None):
        """Return True if Poll is currently active."""
        if not as_of:
            as_of = datetime.utcnow()
            
        is_active = as_of < self.end_date
        
        # check if we need to update our watchable_changed status
        if not is_active:
            if self.watchable_last_change() < self.end_date:
                self.watchable_changed()
        
        return is_active
    
    def cancel_poll(self, note=None):
        """Immediately ends poll, inserting note if any at beginning of description."""
        self.end_date = datetime.utcnow()
        if note:
            self.set_description(note + '\n\n\n' + self.get_description())
            
        # set changed when poll is canceled
        self.watchable_changed(self.end_date)
        
    def num_votes_cast(self):
        if not self.__num_votes_cast:
            self.__num_votes_cast = self.__data.num_votes_cast()
        return self.__num_votes_cast
        
    def valid_vote(self, user, choices):
        """Check various permissions to vote. If choices is not None, also checks validity
        of choices. Use can_vote to pre-check user's access before validity of choices.
        
        Returns:
            1: if user is allowed to vote and choices includes required votes.
            0: if choices are not valid
            -1: if user does not have access to vote
            -2: user has already voted
            -3: user has insufficient feedback score to vote
            -4: user has insufficnent bank to vote
            -5: user joined ned.com after poll started
        """
        
        # general vote access
        if self.__data.vote_access == 'owner':
            if not self.container.ihb.is_owner(user):
                return -1
        elif self.__data.vote_access == 'member':
            if not self.container.ihb.is_member(user) and not self.container.ihb.is_owner(user):
                return -1
        
        # min karma
        if not self.enough_karma_to_vote(user):
            return -3
        
        # karma bank cost
        if user.get_karma_bank_balance() < self.__data.karma_cost:
            return -4
        
        # valid choices
        if choices and not self.__data.choices_valid(choices):
            return 0
        
        # check if trying to vote for no choices
        if choices is not None and not choices:
            return 0
        
        if not self.__data.voter_can_revise:
            if self.__data.has_voted(user):
                return -2
        
        if not self.old_enough_to_vote(user):
            return -5
        
        return 1
        
    def can_pay_for_vote(self, user):
        if not user:
            return False
        return user.can_give_karma(self.get_data().karma_cost)

    def enough_karma_to_vote(self, user):
        return user.get_karma_score() >= self.get_data().min_karma

    def old_enough_to_vote(self, user):
        return user.get_user_data().member_since() <= self.date

    def can_vote(self, user):
        return self.valid_vote(user, choices=None) == 1
    
    def can_see_intermediate_results(self, user):
        pd = self.get_data()
        
        vote_required = pd.vote_required_to_view
        has_voted = self.has_voted(user)
        
        if vote_required and not has_voted:
            return False
        
        if pd.intermediate_access == 'none':
            return False
        if pd.intermediate_access == 'all':
            return True
        if pd.intermediate_access == 'member':
            return self.container.ihb.is_member(user) or self.container.ihb.is_owner(user)
        if pd.intermediate_access == 'owner':
            return self.container.ihb.is_owner(user)
        return False
        
    def can_see_results(self, user):
        pd = self.get_data()
                
        if pd.results_access == 'all':
            return True
        if pd.results_access == 'member':
            return self.container.ihb.is_member(user) or self.container.ihb.is_owner(user)
        if pd.results_access == 'owner':
            return self.container.ihb.is_owner(user)
        return False
        
    def record_vote(self, user, choices):
        """Record a vote. Raises ValueError if valid_vote() check fails.
        
        Fails silently if poll is no longer open or if user can't pay.
        """
        
        if not self.is_active():
            return
        
        if self.valid_vote(user, choices) != 1:
            raise ValueError
            
        # see if new vote is identical to previous vote
        if self.has_voted(user):
            if choices == self.user_vote(user):
                return
            
        if not _ROLLOUT_TEST:
            # try to pay for item
            try:
                user.pay_karma(self.get_data().karma_cost)
            except NoKarmaToGive:
                return
        
        self.__data.record_vote(user, choices)
        self.__num_votes_cast = None
        
        # karma credit
        user.karma_activity_credit()
    
    def choice_list_to_choices(self, choice_list):
        """Convert a list of strings to their corresponding list of indices.
        
        Raises ValueError if there is an invalid item in choice_list.
        """
        pd = self.get_data()
        choices = []
        for item in choice_list:
            choices.append(pd.choices.index(item))
        return choices
        
    def _set_item_index(self, index):
        """Used by PollContainer to set this item's index when added to container."""
        self.__item_index = index
    
    def get_item_index(self):
        return self.__item_index

    def add_html_dependency(self, target):
        """Adds target as something self depends on for its HTML cache."""
        self.__cached_html.add_dependency(target)

    def invalidate_html_cache(self):
        self.__cached_html.flush()
        
    def get_cached_html(self):
        return self.__cached_html.get().get_raw()

    def _update_html_cache(self):
        from qon.ui.blocks.wiki import rst_to_html
        return CompressedText(str(rst_to_html(self.get_description(),
            wiki=self.container.ihb.get_wiki(),
            container=self)))

    def disable_cache(self):
        self.__cached_html.disable_cache()

    def cache_disabled(self):
        return self.__cached_html.cache_disabled()        
            
    def watchable_name(self):
        return self.title

    def watchable_changed(self, now=None):
        # tells container he has changed, too
        Watchable.watchable_changed(self, now)
        self.container.watchable_changed(now)

    def can_read(self, user):
        return self.container.ihb.can_read(user)        
        
# ---------------------------------------------------------------------

def _test():
    import doctest, poll
    return doctest.testmod(poll)
    
if __name__ == "__main__":
    _test()
