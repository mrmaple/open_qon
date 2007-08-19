"""
$Id: karma.py,v 1.44 2007/04/02 12:09:17 jimc Exp $
"""

import random
from persistent.list import PersistentList
from BTrees import OIBTree
from dulcinea.typeutils import typecheck

min_karma_to_post = -24     # min karma required for a User to post/edit
min_karma_to_show = -4      # min karma required for a BlogItem to be shown
min_author_karma = -9       # min karma required of author for an item to be shown
show_neg_threshold = -5     # level at which or below negative karma will no longer be anon

class NoKarmaToGive(Exception):
    """Raised when attempting to give karma out of an empty bank."""

class HasKarma:
    """Mixin class to record receipt of karma feedback.
    
    Subclasses must implement can_get_karma_from().
    """
    
    good_karma = 1
    bad_karma = -1
    
    def __init__(self):
        self.__score = 0
        self.__karma = OIBTree.OIBTree()
        
    def add_karma(self, source, karma, credit_bank=True):
        """Add karma from source. Will call self.notify_karma_changed()
        if it exists.
        """
        typecheck(source, HasKarmaBank)
        assert hasattr(source, 'get_user_id')
        source_uid = source.get_user_id()
        self.__karma[source_uid] = self.__karma.get(source_uid, 0) + karma
        self.__score += karma
        
        if credit_bank:
            if karma > 0:
                if hasattr(self, '_karma_subpoint'):
                    self._karma_subpoint(karma * HasKarmaBank.subpoints_for_receive_karma)
            
        self.notify_karma_changed()
            
    def notify_karma_changed(self):
        """If subclass defines, called by add_karma."""
        pass
        
    def return_karma_from(self, source):
        """Admin function to undo all karma received from source. Will credit source's bank and
        debit my bank for any subpoints I received. Returns karma (if any) from source.
        """
        karma_from = self.karma_points_from(source)
        if karma_from:
            karma_to_return = -karma_from
            
            # negate effect of karma, but don't credit my bank
            self.add_karma(source, karma_to_return, credit_bank=False)
            
            # return karma to source's bank
            if isinstance(source, HasKarmaBank):
                source.add_karma_bank(abs(karma_to_return))

            # debit my bank the credit I received
            if isinstance(self, HasKarmaBank):
                self.return_bank_credit_from_karma(karma_from)

        return karma_from

    def add_anon_karma(self, karma):
        self.__score += karma
        self.notify_karma_changed()
        
    def calc_karma_score(self):
        score = 0
        for user_id, karma in self.__karma.iteritems():
            score += karma
        self.__score = score
        
    def get_karma_score(self):
        """Return karma score. Note that some objects may implement
        this method to masquerade as HasKarma instances.
        """
        return self.__score

    def get_karma_breadth(self):
        """Breadth is the number of people who have given 
        karma to an item."""
        positive_karma_givers = 0
        for user_id, karma in self.__karma.iteritems():
            if karma > 0:
                positive_karma_givers += 1
        return positive_karma_givers
        
    def karma_points_from(self, user):
        assert hasattr(user, 'get_user_id')
        return self.__karma.get(user.get_user_id(), 0)
        
    def karma_plus_received(self):
        """Return positive karma points received."""
        total = 0
        for user_id, karma in self.__karma.iteritems():
            if karma > 0:
                total += karma
        return total

    def karma_minus_received(self):
        """Return negative karma points received (as a positive sum)."""
        total = 0
        for user_id, karma in self.__karma.iteritems():
            if karma < 0:
                total -= karma
        return total

    def positive_karma_givers(self):
        """Return list of positive karma givers (BY USERID) ordered by highest karma first.
        
        Returns list of tuples: (karma, user_id)...
        """
        bykarma = []
        for user_id, karma in self.__karma.iteritems():
            if karma > 0:
                bykarma.append((karma, user_id))
        bykarma.sort()
        bykarma.reverse()
        return bykarma
                
    def negative_karma_givers(self):
        """Return list of negative karma givers (BY USERID) ordered by lowest karma first.
        
        Returns list of tuples: (karma, user_id)...
        """
        bykarma = []
        for user_id, karma in self.__karma.iteritems():
            if karma < 0:
                bykarma.append((karma, user_id))
        bykarma.sort()
        return bykarma
        
    def karma_details(self):
        """Return results of karma_plus_received, karma_minus_received, positive_karma_givers,
        and negative_karma_givers in one iteration. Returns list.
        """
        plus_total = 0
        neg_total = 0
        plus_bykarma = []
        neg_bykarma = []
        for user_id, karma in self.__karma.iteritems():
            if karma > 0:
                plus_total += karma
                plus_bykarma.append((karma, user_id))
            elif karma < 0:
                neg_total -= karma
                neg_bykarma.append((karma, user_id))
        
        plus_bykarma.sort()
        plus_bykarma.reverse()
        neg_bykarma.sort()
        
        return (plus_total, neg_total, plus_bykarma, neg_bykarma)
        
    def can_get_karma_from(self, other):
        """Subclasses should implement to restrict karma from self, for example
        or other checks.
        """
        raise NotImplementedError
        
class HasKarmaBank:
    """Mixin class providing karma bank functionality.
    
    For example, users who give/receive karma points may do so out of their
    karma bank.
    """
    __persistenceVersion = 2
    
    initial_bank = 10
    bank_limiter = 3                # limit bank size to multiple (3) of score
    subpoints_in_points = 100       # needed for 1 karma point in bank
    subpoints_for_karma = 10        # credit for giving karma
    subpoints_for_activity = 5      # credit for activity
    subpoints_for_receive_karma = 50    # bank credit for receiving 1 karma point
    
    activity_credit_max = 100       # don't give activity credit to banks larger than this
    
    good_karma = HasKarma.good_karma
    bad_karma = HasKarma.bad_karma
    
    def __init__(self):
        self.__bank = self.initial_bank
        self.__subpoints = 0
        self.__plus_given = 0
        self.__minus_given = 0
        self.__plus_given_to = PersistentList()
        self.__minus_given_to = PersistentList()
    
    def upgradeToVersion2(self):
        self.__minus_given_to = PersistentList()

    def upgradeToVersion1(self):
        self.__plus_given_to = PersistentList()
        friends = self.__plus_given_to
        
        # expensive n^2 initial set up of friends list
        from qon.base import get_user_database
        for user in get_user_database().root.values():
            if user.karma_points_from(self) > 0:
                friends.append(user)

    def give_karma(self, to, karma):
        """Give karma to a user or item of content."""
        typecheck(to, HasKarma)
        if not self.can_give_karma(karma):
            raise NoKarmaToGive
            
        to.add_karma(self, karma)
        if karma < 0:
            self.add_karma_bank(karma)
            self.__minus_given -= karma         # sum is positive
            self._record_minus_given(to)
        else:
            self.add_karma_bank(-karma)
            self.__plus_given += karma
            self._record_plus_given(to)
            
        if self.get_karma_bank_balance() < self.activity_credit_max:
            self._karma_subpoint(self.subpoints_for_karma)
    
    def pay_karma(self, karma):
        """Pay a karma fee for a site action."""
        if not self.can_give_karma(karma):
            raise NoKarmaToGive
        
        # reduce bank
        self.add_karma_bank(-karma)
        
    def get_karma_bank_balance(self, read_only=False):
        """Return bank balance, after adding any subpoints.
        
        Normally will update bank if necessary. Pass read_only=True to avoid
        modifiying HasKarmaBank object.
        
        >>> import qon.user
        >>> user=qon.user.User()
        >>> user._HasKarmaBank__subpoints=100
        >>> user.get_karma_bank_balance()
        10
        >>> user._HasKarmaBank__subpoints    
        100
        >>> user._HasKarmaBank__subpoints=150
        >>> user.get_karma_bank_balance()
        10
        >>> user._HasKarmaBank__subpoints
        150
        >>> user._HasKarma__score=4
        >>> user.get_karma_bank_balance()
        11
        >>> user._HasKarmaBank__subpoints
        50
        >>> 
        >>> user._HasKarmaBank__subpoints=250
        >>> user.get_karma_bank_balance()
        12
        >>> user._HasKarmaBank__subpoints
        150
        """
        
        if read_only:
            return self.__bank
        
        if self.__subpoints > self.subpoints_in_points:
            (p, s) = divmod(self.__subpoints,
                self.subpoints_in_points)

            if p:
                remainder = self.add_karma_bank(p)
                if remainder and (remainder < p):
                    # could not fully increment bank due to limit, so subtract corresponding
                    # amount of subpoints
                    self.__subpoints -= remainder * self.subpoints_in_points
                elif remainder == p:
                    # could not increment bank at all, leave subpoints alone
                    pass
                else:
                    # fully incremented bank, record remaining subpoints
                    self.__subpoints = s
                
        return self.__bank
        
    def can_give_karma(self, karma):
        if karma < 0:
            return self.__bank >= -karma
        else:
            return self.__bank >= karma
    
    def _karma_subpoint(self, count=1, force=0):
        """Add (or subtract) subpoints."""

        # do not record subpoints if karma bank limit is already reached
        if force or not self.bank_is_capped():
            self.__subpoints += count
        
    def get_bank_limit(self):
        """Return the max size of the bank, or zero if size is unlimited.
        
        >>> import qon.user
        >>> user=qon.user.User()
        >>> user.get_bank_limit()
        10
        >>> user._HasKarma__score=3 
        >>> user.get_bank_limit()
        10
        >>> user._HasKarma__score=5 
        >>> user.get_bank_limit()
        15
        >>> user._HasKarma__score=-10
        >>> user.get_bank_limit()
        10
        >>> user._HasKarma__score=20 
        >>> user.get_bank_limit()
        60
        >>> user._HasKarma__score=30
        >>> user.get_bank_limit()
        90
        """
        if hasattr(self, 'get_karma_score'):
            limit = self.get_karma_score() * self.bank_limiter
            if limit < self.initial_bank:
                limit = self.initial_bank
        else:
            limit = 0
        return limit

    def bank_is_capped(self):
        """Return true if bank is currently capped at maximum."""
        limit = self.get_bank_limit()
        if limit:
            if self.__bank >= limit:
                return True
        return False
        
    def return_bank_credit_from_karma(self, karma):
        """Return (cancel, actually) credit I received when I received positive karma.

        >>> u = HasKarmaBank()
        >>> u._HasKarmaBank__bank = 100
        >>> u.return_bank_credit_from_karma(2)
        >>> u.get_karma_bank_balance()
        99
        >>> u.return_bank_credit_from_karma(1)
        >>> u.get_karma_bank_balance()
        99
        >>> u._HasKarmaBank__subpoints
        -50
        >>> u.return_bank_credit_from_karma(1)
        >>> u.get_karma_bank_balance()
        98
        >>> u._HasKarmaBank__subpoints
        0

        """

        def debit_subpoints(subpoints):
            """Debit from bank the appropriate number of whole points, returning
            the remainder of subpoints unused by debit.
            """
            assert subpoints >= 0
            points_to_debit, remainder = divmod(subpoints, self.subpoints_in_points)
            self.add_karma_bank(-points_to_debit)
            return remainder

        if karma <= 0:
            return

        subpoints_to_debit = karma * self.subpoints_for_receive_karma
        remainder = debit_subpoints(subpoints_to_debit)
        self._karma_subpoint(-remainder, force=1)

        if self.__subpoints <= -self.subpoints_in_points:
            # negative points accumulated
            subpoints_to_debit = -self.__subpoints
            remainder = debit_subpoints(subpoints_to_debit)
            self._karma_subpoint(subpoints_to_debit - remainder, force=1)

    def cancel_karma_given(self):
        """Admin function to cancel all karma given to users (HasKarma) by self."""

        for u in self.karma_plus_given_to() + self.karma_minus_given_to():
            u.return_karma_from(self)

        # zero lists
        self.__plus_given_to = PersistentList()
        self.__minus_given_to = PersistentList()

    def karma_given_report(self):
        """Return [(user, karma), ...]"""

        karma_given = []
        for u in self.karma_plus_given_to() + self.karma_minus_given_to():
            karma_given.append((u, u.karma_points_from(self)))

        return karma_given

    def add_karma_bank(self, karma):
        """Add karma to bank balance and return remainder if limit exceeded. Returns zero
        if all karma could be added to bank.
        
        >>> import qon.user
        >>> user=qon.user.User()
        >>> user.add_karma_bank(-1)
        0
        >>> user.get_karma_bank_balance()
        9
        >>> user.add_karma_bank(1)
        0
        >>> user.get_karma_bank_balance()
        10
        >>> user.add_karma_bank(1)
        1
        >>> user.get_karma_bank_balance()
        10
        >>> user.add_karma_bank(5)
        5
        >>> user.get_karma_bank_balance()
        10
        >>> user._HasKarma__score=10
        >>> user.add_karma_bank(5)
        0
        >>> user.get_karma_bank_balance()
        15
        >>> user._HasKarma__score=0
        >>> user.add_karma_bank(1)
        1
        >>> user.get_karma_bank_balance()
        15
        >>> user._HasKarma__score=-5
        >>> user.add_karma_bank(1)
        1
        >>> user.get_karma_bank_balance()
        15
        >>> user._HasKarmaBank__bank=0
        >>> user.add_karma_bank(1)
        0
        >>> user.get_karma_bank_balance()
        1
        >>> user._HasKarmaBank__bank=0
        >>> user.add_karma_bank(-1)     # do not allow neg balance
        0
        >>> user.get_karma_bank_balance()
        0
        
        """
        
        # negative karma - no limiter
        if karma < 0:
            self.__bank += karma

            # don't allow negative bank balance
            if self.__bank < 0:
                self.__bank = 0
            return 0
        
        # positive karma - don't exceed limit
        limit = self.get_bank_limit()
        if limit:
            if self.__bank >= limit:
                # could not add karma
                return karma
            
            self.__bank += karma
            
            if self.__bank > limit:
                remainder = self.__bank - limit
                self.__bank = limit
                # could not add entire karma, return remainder
                return remainder
            
            # added all karma, return zero
            return 0
        else:
            self.__bank += karma
            return 0

    def karma_activity_credit(self):
        """Give credit for activity."""
        if self.get_karma_bank_balance() < self.activity_credit_max:
            self._karma_subpoint(self.subpoints_for_activity)

    def karma_activity_credit_sampled(self):
        """Give credit for activity. Random sampling to minimize db hits."""
        
        # over time, give 1/2 of subpoints_for_activity per sampled hit
        if random.randint(1, 20) == 4:
            if self.get_karma_bank_balance() < self.activity_credit_max:
                self._karma_subpoint(self.subpoints_for_activity * 10)

    def karma_plus_given(self):
        return self.__plus_given
        
    def karma_plus_given_to(self):
        return self.__plus_given_to[:]
        
    def karma_minus_given(self):
        return self.__minus_given

    def karma_minus_given_to(self):
        return self.__minus_given_to[:]
        
    def _record_plus_given(self, to):
        """Record that I've given to a plus. Add to friends list."""
        if not isinstance(to, HasKarmaBank):
            return
        
        # add to friends if not there
        if to not in self.__plus_given_to:
            if to.karma_points_from(self) > 0:
                self.__plus_given_to.append(to)
        
        # remove from enemies if there
        if to in self.__minus_given_to:
            if to.karma_points_from(self) >= 0:
                self.__minus_given_to.remove(to)

    def _record_minus_given(self, to):
        """Record that I've given to a minus. Remove from friends list if <= 0."""
        if not isinstance(to, HasKarmaBank):
            return
            
        # add to enemies if not there
        if to not in self.__minus_given_to:
            if to.karma_points_from(self) < 0:
                self.__minus_given_to.append(to)

        # remove from friends if there
        if to in self.__plus_given_to:
            if to.karma_points_from(self) <= 0:
                self.__plus_given_to.remove(to)


# -------------------------------------------------------------------------

def upgrade_minus_given_to():
    """Set up __minus_given_to list in all users."""
    from qon.base import get_user_database, transaction_commit
    
    for user_id, user in get_user_database().root.iteritems():
        
        changed = 0

        for id2, user2 in get_user_database().root.iteritems():
            if user2.karma_points_from(user) < 0:
                if user2 not in user._HasKarmaBank__minus_given_to:
                    user._HasKarmaBank__minus_given_to.append(user2)
                    changed = 1
        
        if changed:
            transaction_commit(None, 'UpgradeMinusGiven')
            changed = 0
    
def karma_given_by(user):
    """Return a list of all HasKarma items which have received karma from user.
    """
    from qon.base import get_group_database, get_user_database
    
    results = []
    
    def check_karma(item):
        p = item.karma_points_from(user)
        if p:
            results.append((item, p))
            
    def check_blog_karma(blog):
        for i in blog.get_items():
            check_karma(i)
            for c in i.get_all_comments():
                check_karma(c)
    
    for id, u in get_user_database().root.iteritems():
        check_karma(u)
        check_blog_karma(u.blog)
    
    for id, g in get_group_database().root.iteritems():
        check_blog_karma(g.blog)
        
        for id, page in g.wiki.pages.iteritems():
            check_karma(page)
            check_blog_karma(page.blog)

    return results
    
def find_over_negs():
    """Return users who have given more negative feedback over the threshold."""
    from qon.base import get_user_database
    
    users = []
    for user_id, user in get_user_database().root.iteritems():
        neg_givers = user.negative_karma_givers()
        for karma, giver in neg_givers:
            if karma <= show_neg_threshold:
                users.append((giver, user.get_user_id(), karma))
    return users

def find_over_pos():
    """Return users who have given more positive feedback over +5."""
    from qon.base import get_user_database
    
    users = []
    for user_id, user in get_user_database().root.iteritems():
        pos_givers = user.positive_karma_givers()
        for karma, giver in pos_givers:
            if karma >= 5:
                users.append((giver, user.get_user_id(), karma))
    return users

def report_over_pos():
    from qon.base import get_user_database
    user_db = get_user_database()
    users = find_over_pos()
    
    for giver, recip, amount in users:
        print '%s,%s,%d,%f,%d' % (
            user_db.get_user(giver).display_name().replace(',','.'),
            user_db.get_user(recip).display_name().replace(',','.'),
            amount,
            float(amount) / float(user_db.get_user(recip).get_karma_score()),
            user_db.get_user(giver).get_karma_bank_balance(),
            )
    
def upgrade_cap_subpoints():
    """Remove pending subpoints from users whose banks are capped."""
    from qon.base import get_user_database, transaction_commit
    
    for user_id, user in get_user_database().root.iteritems():
        if user.bank_is_capped():
            if user._HasKarmaBank__subpoints > 0:
                user._HasKarmaBank__subpoints = 0
                transaction_commit(None, 'UpgradeCapSubpoints')

def _test():
    import doctest, karma
    return doctest.testmod(karma)
    
if __name__ == "__main__":
    _test()
