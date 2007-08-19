"""
$Id: api.py,v 1.133 2007/06/28 14:43:59 jimc Exp $

Function-level APIs for Qon
"""
from quixote.errors import AccessError
from datetime import datetime
from util import sendmail, unique_items
from dulcinea.typeutils import typecheck
from dulcinea.database import unpack_oid, pack_oid
from quixote.html import url_quote

from qon.base import get_user_database, get_group_database, get_usergroup_database, \
     get_log, transaction_commit, get_observe_database, get_tags_database, get_tagged_item_database

import qon.ui.blocks
from ui.blocks.util import format_datetime    

import qon.blog
import qon.group
import qon.wiki
import qon.log
from qon.user import User

import qon.search

from qon.ui import messages
_ = messages.t

def group_can_manage(user, group):
    """Return True if user can manage group's settings."""
    return group.can_manage(user)

def group_set_settings(user, group, **kwargs):
    if not group_can_manage(user, group):
        raise AccessError
        
    _set_attributes(group, **kwargs)
    transaction_commit(None, 'GroupSetSettings')    # moved from group/form.ptl/SettingsForm.commit()
    qon.search.searchengine.notify_edited_group(group)
    
def group_set_member_edit(user, group, yes_or_no):
    if not group_can_manage(user, group):
        raise AccessError

    perms = group.get_perms()
    if yes_or_no:
        if 'write' not in perms[1]:
            perms[1].append('write')
            group.set_group_perms(perms[1])
    else:
        if 'write' in perms[1]:
            perms[1].remove('write')
            group.set_group_perms(perms[1])

def group_set_other_perms(user, group, access):
    if not group_can_manage(user, group):
        raise AccessError

    if access is None:
        access = 'none'
        
    if access == 'ro':
        group.set_other_perms(['read'])
    elif access == 'rw':
        group.set_other_perms(['read', 'write'])
    else:
        group.set_other_perms([])

def group_set_anon_read(user, group, yes_or_no):
    if not group_can_manage(user, group):
        raise AccessError

    group.anon_read = yes_or_no
    
def group_set_members_can_associate_groups(user, group, yes_or_no):
    if not group_can_manage(user, group):
        raise AccessError

    group.set_members_can_associate_groups(yes_or_no)
    
def _group_set_membership_policy(user, group, pol, priv):
    if not group_can_manage(user, group):
        raise AccessError

    if pol is None:
        pol = 'owner'
        
    members = group.get_members()
    perms = members.get_perms()
        
    if pol == 'open':
        perms[2].append(priv)
        perms[1].append(priv)
        perms[0].append(priv)
    elif pol == 'member':
        perms[1].append(priv)
        if priv in perms[2]:
            perms[2].remove(priv)
    elif pol == 'owner':
        perms[0].append(priv)
        if priv in perms[2]:
            perms[2].remove(priv)
        if priv in perms[1]:
            perms[1].remove(priv)
    
    members.set_other_perms(perms[2])
    members.set_group_perms(perms[1])
    members.set_owner_perms(perms[0])
    
def group_set_invite_policy(user, group, pol):
    _group_set_membership_policy(user, group, pol, 'manage')
    
def group_set_join_policy(user, group, pol):
    _group_set_membership_policy(user, group, pol, 'write')

def group_set_membership_visible(user, group, pol):
    _group_set_membership_policy(user, group, pol, 'read')
        
def group_set_owners_by_user_id(user, group, owner_ids):
    if not group_can_manage(user, group):
        raise AccessError

    user_db = get_user_database()
    users = []
    seen = {}
    for _id in owner_ids:
        if not seen.has_key(_id):
            u = user_db.get_user(_id)
            if u:
                users.append(u)
            seen[_id] = 1
            
    get_group_database().set_group_owners(group, users)
    
def group_get_owners_user_id(group):
    return [u.get_user_id() for u in group.owners]
        
def group_begin_sponsorship(group):
    group.set_pending()
    transaction_commit(None, 'BeginSponsor')    # moved from group/form.ptl/SponsorPhaseForm.commit()
    
def group_delete(group):
    get_group_database().remove_group(group)
    transaction_commit(None, 'DeleteGroup')    # moved from group/form.ptl/SponsorPhaseForm.commit() & DeleteGroupForm.commit() & AdminDeleteGroupForm.commit()
    qon.search.searchengine.notify_deleted_group(group)

def group_create(user, **kwargs):
    """Create a group. See qon.group_db.GroupDB.create_group for arguments."""
    
    group_db = get_group_database()
    
    if not user or not group_db.can_create_group(user):
        raise AccessError
    
    group = get_group_database().create_group(**kwargs)
    if group:
        group_begin_sponsorship(group)

        if 0:
            blog_new_item(group.blog,
                author=kwargs['owner'],
                title=_(_new_forum_title),
                summary=_(_new_forum_summary))

        transaction_commit(None, 'CreateGroup') # moved from group/form.ptl/NewGroupForm.commit()
        qon.search.searchengine.notify_new_group(group)

    return group

def group_invite_user(user, group, email, inviter):
    """Invite email to join group. May raise smtplib.SMTPRecipientsRefused if server
    rejects email.
    """
    if not group.is_accepted() or not group.get_members().can_manage(user):
        raise AccessError

    group.add_invitation(email, inviter)

    transaction_commit(inviter, 'InviteToGroup')    # moved from group/form.ptl/InviteForm.commit()
    
    try:
        user = get_user_database().get_user_by_email(email)
    except KeyError:
        # e-mail address is not registered, send an e-mail (rather than internal message)
        subject=_(_email_invite_subject) % dict(group_name=group.name)
        body=_(_email_invite_body) % dict(email=email,
            home_url=messages.home_url,
            inviter=qon.ui.blocks.user.display_name_plain(inviter),
            group_name=qon.ui.blocks.group.display_name_plain(group))
            
        sendmail(subject, body, [email])
    else:
        message_send(inviter, user,
            subject=_(_message_invite_subject) % dict(group_name=group.name),
            body=_(_message_invite_body) % dict(
                email=email,
                inviter=qon.ui.blocks.user.display_name_plain(inviter),
                group_name=qon.ui.blocks.group.display_name_plain(group)
                )
            )

def group_force_accept(user, group):
    if not user or not user.is_admin():
        raise AccessError
    get_group_database().force_accept(group)

def group_force_accept_simple(user, group):
    if not user or not user.is_admin():
        raise AccessError
    group.force_accept()
    transaction_commit(None, 'ForceGroupAccept')   # moved from group/group.ptl/GroupStaffUI/accept()

def group_remove_owner(user, user_id, group):
    """Remove user_id from self.group's list of owners. user is user attempting removal."""
    owners_user_id = qon.api.group_get_owners_user_id(group)
    try:
        owners_user_id.remove(user_id)
    except ValueError:
        pass
    else:
        if owners_user_id:
            # don't allow an empty owner set -- who knows what would happen?
            qon.api.group_set_owners_by_user_id(user, group, owners_user_id)  

# XXX --------- continue adding permission checks here ---------- XXX

def group_join(group, user):
    """Join group. Raises NotEnoughPrivileges if user doesn't have permission to join."""
    get_group_database().join_group(user, group)
    transaction_commit(user, 'JoinGroup')       # moved from blocks/action.ptl/JoinGroupForm.commit()
    
def group_decline_invitation(group, user):
    get_group_database().decline_invitation(user, group)
    transaction_commit(user, 'DeclineJoinGroup')       # moved from blocks/action.ptl/JoinGroupForm.commit()
    
def group_leave(group, user):
    get_group_database().leave_group(user, group)
    transaction_commit(user, 'LeaveGroup')  # moved from admin.ptl/UnjoinUserForm.commit() & group/form.ptl/LeaveGroupForm.commit()
    
def group_sponsor(group, user):
    get_group_database().add_sponsor(group, user)
    transaction_commit(user, 'SponsorGroup')    # moved from blocks/action.ptl/SponsorGroupForm.commit()

def group_purge(group):
    """Purge an unsponsored group."""
    if not group.is_accepted():
        # send a message to group owner that his group is being purged
        
        email = group.owners[0].get_primary_email()
        
        d=dict(group_name=group.display_name(),
            primary=email,
            group_description=group.description,
            )
        
        message = _notify_group_purged % d
        
        import socket
        try:
            sendmail("ned.com Group Not Sponsored", message, [email])
        except socket.error:
            pass
        
        # delete the group
        group_delete(group)
    
def group_purge_unsponsored():
    """Remove groups which have not been sponsored by qon.group.Group._time_to_sponsor."""
    pending_groups = get_group_database().mod_queue.pending_items()
    now = datetime.utcnow()
    for group in pending_groups:
        if now - group.date > qon.group.Group._time_to_sponsor:
            group_purge(group)           

def group_decay_inactive_karma():
    """Decay karma of inactive blog items."""
    decayed_items = []
    for group_id, group in get_group_database().root.iteritems():
        decayed_items.extend(group.blog.decay_inactive_items())
        decayed_items.extend(group.wiki.decay_inactive_items())
        transaction_commit(None, 'DecayInactive')

    # notify the search engine that the items' karma changed.
    #  The reason we do the notification here, rather than in blog.decay_inactive_items() itself.
    #  is that it's nice keeping all the search engine notifications localized
    #  to this file, rather than sprinkled in the kernel.
    for item in decayed_items:
        qon.search.searchengine.notify_karma_given(item)
    
# ----------------------------------------------------------------------
import qon.user

def user_add_staff_note(user, author, note):
    """Add a staff note from author to user."""
    note = _unicode_fix(note)
    
    if not author.is_staff() and not author.is_admin():
        raise AccessError

    user.get_user_data().add_note(author, note)

def user_cancel_karma_given(user, staff_user):
    if not staff_user.is_staff() and not staff_user.is_admin():
        raise AccessError

    # since this is not reversible, log all data (which would otherwise be lost)
    karma_given_data = user.karma_given_report()
    karma_given = ['%s:%d' % (u.get_user_id(), karma) for u, karma in karma_given_data]
    qon.log.admin_info('CancelUserKarmaGiven\t%s\t%s' % (user.get_user_id(), ",".join(karma_given)))

    user.cancel_karma_given()

def user_set_settings(user, **kwargs):
    """Set user profile:
    
    name        Full name
    bio         about-me text
    anon_blog   'yes' if anon users can read personal news
    email_notify    'yes' if user should receive e-mail notices of incoming messages
    """
    
    user.set_contact_name(_unicode_fix(kwargs['name']))
    user.bio = _unicode_fix(kwargs['bio'])
    user.location = _unicode_fix(kwargs['location'])
    user.latitude = kwargs['latitude']
    user.longitude = kwargs['longitude']
    user.deliciousID = kwargs['deliciousID']
    user.flickrID = kwargs['flickrID']
    user.skypeID = kwargs['skypeID']
    user.blogURL = kwargs['blogURL']    
    user.get_user_data().set_anon_can_read_blog(kwargs['anon_blog'] == 'yes')
    user.set_email_notify(kwargs['email_notify'] == 'yes')
    user.set_copy_self(kwargs['copy_self'] == 'yes')

    transaction_commit(user, 'UserPrefs')  # moved from user.ptl/UserPrefsForm.commit()
    qon.search.searchengine.notify_edited_user(user)
    
    get_observe_database().notify_changed(user) # FIXME this should be in user.py somewhere
    
def user_set_password(user, password):
    password= _unicode_fix(password)
    
    user.set_password(password)
    transaction_commit(user, 'ChangePassword') # moved from user.ptl/UserChangePasswordForm.commit()
    
def user_new(email):
    # create user and get the initial password in plaintext.
    email = _unicode_fix(email)

    user, password = get_user_database().new_user_from_email(email)

    transaction_commit(None, 'NewUser') # moved from user.ptl/NewUserForm.commit()

    # send email
    e = url_quote(email)
    p = url_quote(password)
    s = url_quote("Sign in")
    
    message = _(_new_user_message) % dict(email=email,
        password=password,                             
        auto_login_url=messages.login_url + "?email=" + e + "&password=" + p + "&submit-login=" + s + "&from_url=Y")

    extra_headers = ['Content-Type: text/html'] # because of the href
    sendmail("Welcome to ned.com", message, [email], extra_headers=extra_headers)

    # send pm using _live_tmpl_pm_new_user in sitedev as the template
    template_text = qon.util.get_page_template('pm_new_user', format='text')
    if template_text:
        message_anon_send(user, "Welcome to ned.com!", template_text, True)

    # add orientation page to all new users' watch lists
    try:
        orientation = get_group_database()['help'].get_wiki().pages['start_here']
        user.get_watch_list().watch_item(orientation)
    except:
        pass        

    qon.search.searchengine.notify_new_user(user)
    return (email, message)

def user_new_password(user, email):
    password = user.generate_password()

    transaction_commit(user, 'NewPassword')    # moved from user.ptl/NewPasswordForm.commit() 

    message = _(_new_password_message) % dict(
        email=email,
        password=password,
        )

    sendmail("ned.com New Password", message, [email])
    return (email, message)

def user_add_email(user, email):
    email = _unicode_fix(email)
    
    code = user.add_unconfirmed_email(email)

    transaction_commit(user, 'AddEmail')    # moved from user.ptl/AddEmailForm.commit() 

    message = _(_confirm_email_message) % dict(email=email,
        base_url=messages.base_url,
        url=qon.ui.blocks.user.path_to_user(user)[1:] + 'private/confirm', code=code)

    sendmail("ned.com Confirm New Email", message, [email])
    
    inform = _(_notify_new_email_message) % dict(
        primary=user.get_primary_email(),
        new=email)
    
    sendmail("ned.com Email Added", inform, [user.get_primary_email()])

    qon.search.searchengine.notify_edited_user(user)
    return (email, message)

def user_confirm_email(user, code):
    """Attempt to confirm an e-mail address with code. Returns True if successful."""
    success = get_user_database().confirm_user_email(user, code)
    transaction_commit(user, 'ConfirmEmail')   # moved from user.ptl/ConfirmEmailForm.commit()
    return success
    
def user_set_primary_email(user, email):
    email = _unicode_fix(email)
    
    user.set_primary_email(email)
    transaction_commit(user, 'ChangePrimaryEmail') # moved from user.ptl/UserEmailsForm.commit()
    

def user_delete_email(user, email):
    """Delete a confirmed or unconfirmed e-mail. Raise KeyError if attempt to delete last e-mail.
    Raise ValueError if email is not in user's email list.
    """
    get_user_database().remove_user_email(user, email)
    transaction_commit(user, 'UserDeleteEmail') # moved from user.ptl/UserDeleteEmailForm.commit()
    qon.search.searchengine.notify_edited_user(user)

def user_delete(user):
    """Deletes a user object from the ZODB and the Search DB.  Does not attempt to
    find items authored by the user and delete those too.
    """
    get_user_database().remove_user(user.get_user_id())
    transaction_commit(None, 'AdminDeleteUser')   # moved from admin.ptl/DeleteUserForm.commit()
    qon.search.searchengine.notify_deleted_user(user)

def user_set_user_agreement_accepted(user, accepted):
    user.set_user_agreement_accepted(accepted)
    transaction_commit(user, 'AcceptUserAgreement')    # moved from home.ptl/UserAgreementForm.commit()

def user_set_disabled(user, disabled):
    user.set_disabled(disabled)
    if disabled:
        note = 'AdminDisableUser'
    else:
        note = 'AdminEnableUser'
    transaction_commit(None, note) # moved from admin.ptl/UserUI.enable() & admin.ptl/DisableUserForm.commit()

def user_add_to_usergroup(user, ug):
    user.add_to_group(ug)
    transaction_commit(None, 'AdminAddUserFromUsergroup') # moved from admin.ptl/AddToUserGroupForm.commit()
    
def user_remove_from_usergroup(user, ug):
    user.remove_from_group(ug)
    transaction_commit(None, 'AdminRemoveUserFromUsergroup') # moved from admin.ptl/RemoveUserFromUsergroupForm.commit()

def user_signed_in(user):
    user.user_signed_in()
    transaction_commit(user, 'SignIn')  # moved from blocks/util.ptl/SignInForm.commit()
    
# ----------------------------------------------------------------------

def blog_new_item(blog, author, title, summary, main='', no_mod=1, no_pay=0):
    """Create a new blog item. If no_mod, don't assign negative karma."""
    title = _unicode_fix(title)
    summary = _unicode_fix(summary)
    main = _unicode_fix(main)
    
    new_item = blog.new_item(author, title, summary, main, no_mod=no_mod, no_pay=no_pay)
    if new_item:
        author.notify_authored_item(new_item)
        transaction_commit(author, 'NewBlogItem')   # moved from blog/form.ptl/NewBlogItemForm.commit() & wiki/form.ptl/CommentItemForm.commit()
        qon.search.searchengine.notify_new_blog_item(new_item)
    return new_item
    
def blog_new_comment(item, author, title, summary, main):
    title = _unicode_fix(title)
    summary = _unicode_fix(summary)
    main = _unicode_fix(main)    
    
    new_comment = item.new_comment(author, title, summary, main)
    author.notify_authored_comment(new_comment, item)
    transaction_commit(author, 'CommentBlogItem')  # moved from blog/form.ptl/CommentItemForm.commit() & wiki/form.ptl/CommentItemForm.commit()
    
    if new_comment:
        qon.search.searchengine.notify_new_blog_comment(item, new_comment)
        
    return new_comment

def blog_edit_item(item, **kwargs):
    typecheck(item, qon.blog.BlogItem)

    if kwargs.has_key('summary'):
        new_summary = _unicode_fix(kwargs['summary'])
    
        if item.title == 'comment':
            if not item.history:
                # start the history with the original message
                item.history = "---- Original Content from %s ----\n%s\n" % \
                    (format_datetime(item.date), item.get_summary())
    
            # append the diff from the current state to the new state to the history
            import difflib
            prev = item.get_summary().splitlines()
            current = new_summary.splitlines()
            diffs = list(difflib.unified_diff(prev, current, n=1, lineterm=''))
            date = format_datetime(datetime.utcnow())
            item.history = "%s\n---- Edit on %s ----\n%s\n" % (item.history, date, '\n'.join(diffs[2:]))

        # change the summary
        item.set_summary(new_summary)
        del kwargs['summary']

    _set_attributes(item, **kwargs)
    item.modified = datetime.utcnow()
    item._p_changed = 1
    
    transaction_commit(None, 'EditBlogItem')   # moved from blog/form.ptl/EditBlogItemForm.commit()

    if item.title == 'comment' or item.not_watchable:   # XXX hack to find comment
        assert(item.parent_blogitem)
        qon.search.searchengine.notify_edited_blog_comment(item)
    else:
        # handle edited blog entries
        qon.search.searchengine.notify_edited_blog_item(item)

def blog_delete_item(item, note=None):
    item.set_deleted(True)
    if note:
        item.set_deleted_note(note)

    transaction_commit(None, 'DeleteBlogItem')  # moved from blog/form.ptl/DeleteItemForm.commit()

    if item.title == 'comment' or item.not_watchable:   # XXX hack to find comment
        assert(item.parent_blogitem)
        qon.search.searchengine.notify_deleted_blog_comment(item)
    else:
        # handle deleted blog entries
        qon.search.searchengine.notify_deleted_blog_item(item)

def blog_undelete_item(item):
    item.set_deleted(False)
    transaction_commit(None, 'UnDeleteBlogItem')  # moved from blog/form.ptl/DeleteItemForm.commit()

    if item.title == 'comment':
        # NON-CRITICAL TO DO: handle deleted comments--will need access to the
        #  blog item to which this comment refers.
        #  One way to do this is to add a field to BlogItem called hc
        #  which points to the HasComments class that the comment belongs to
        pass
    else:
        # handle undeleted blog entries
        qon.search.searchengine.notify_edited_blog_item(item)

# ----------------------------------------------------------------------
import ticket

def ticket_new_tracker(group, name):
    t = ticket.TicketTracker(name=name, group=group)
    group.trackers.append(t)
    transaction_commit(None, 'NewTracker')  # moved from ticket.ptl/NewTrackerForm.commit()
    return t

def ticket_new_item(tracker, user, title, category, priority, text):
    title = _unicode_fix(title)
    text = _unicode_fix(text)
    
    t = tracker.new_ticket(user, title, category, priority, text)
    transaction_commit(user, 'NewTicket')  # moved from ticket.ptl/NewTicketForm.commit() 
    return t
    
def ticket_status_change(tracker, ticket, user, status, category, priority, text=''):
    """User sets ticket status with comment."""
    text = _unicode_fix(text)
    
    tracker.change_status(ticket, user=user, status=status, category=category, priority=priority, text=text)
    transaction_commit(None, 'ChangeIssueStatus')  # moved from ticket.ptl/EditTicketForm.commit() 

def ticket_add_comment(tracker, ticket, user, category, priority, text):
    """Add a comment"""
    text = _unicode_fix(text)
    
    tracker.add_comment(ticket, user=user, category=category, priority=priority, text=text)
    transaction_commit(None, 'AddIssueComment')  # moved from ticket.ptl/EditTicketForm.commit() 

# ------------------------- tagging ---------------------------------------------
# 
import qon.tags
# the central tagging function that coordinates different tag containers
def tag_item (tags, user, item_oid, group, comment = None, is_user=False):
    """ all tags are applied through this function, which keeps
    the various databases consistent with each other."""
    user_id = user.get_user_id()

    tags = qon.tags.standardize_tags(tags)

    # clear out any removed tags
    tags_db = get_tags_database()
    tidb = get_tagged_item_database()
    if is_user:
        user_db = get_user_database()

    # what gets removed? what gets added?
    old_tags = tidb.get_tags(item_oid, user_id)
    tags_to_remove = [tag for tag in old_tags if tag not in tags]
    tags_to_add = [tag for tag in tags if tag not in old_tags]

    if tags_to_remove:
        # remove user from removed tags
        tags_db.remove_tags(tags_to_remove, item_oid, user_id)
    
        if group:
            group.remove_tags(tags_to_remove, item_oid, user_id)
    
        # remove the tag from the user's list too.
        user.remove_tags(tags_to_remove, item_oid)

        if is_user:
            user_db.remove_tags(tags_to_remove, item_oid, user_id)
        #
    #

    if tags_to_add:
        # add to the global database
        tags_db.tag_item(user.get_user_id(), item_oid, tags, comment)
    
        # group gets its tag information
        if group:
            group.tag_item(user_id, item_oid, tags_to_add, comment)
    
        # update the user's tag cloud
        user.tag_item(tags, item_oid)

        if is_user:
            user_db.tag_item(user_id, item_oid, tags_to_add, comment)
        #
    #
    get_transaction().commit()
#
 
def tag_karma_give_good(fr, to, message=None, message_anon=True, karma=qon.karma.HasKarma.good_karma):
    message = _unicode_fix(message)
    
    if to.can_get_karma_from(fr):
        try:
            tags_db = get_tags_database()
            fr.give_karma(to.tag_karma, karma)
            to.tag_karma.calc_karma_score()
            if to.tag_karma.get_karma_score() > qon.tags.tagger_naughty_threshold:
                tags_db.set_tagger_nice(to.get_user_id())
            #
            _karma_send_message(fr, to, 'positive', '+%d' % karma, message, message_anon)
            transaction_commit(fr, 'KarmaGiveGood')
            qon.search.searchengine.notify_karma_given(to)
        except qon.karma.NoKarmaToGive:
            pass
    #
#

def tag_karma_give_bad(fr, to, message=None, message_anon=True, karma=qon.karma.HasKarma.bad_karma):
    message = _unicode_fix(message)
    
    if to.can_get_karma_from(fr):
        try:
            tags_db = get_tags_database()
            fr.give_karma(to.tag_karma, karma)
            to.tag_karma.calc_karma_score()
            if to.tag_karma.get_karma_score() <= qon.tags.tagger_naughty_threshold:
                tags_db.set_tagger_naughty(to.get_user_id())
            #
            _karma_send_message(fr, to, 'negative', '%d' % karma, message, message_anon)
            transaction_commit(fr, 'KarmaGiveBad')            
            qon.search.searchengine.notify_karma_given(to)
        except qon.karma.NoKarmaToGive:
            pass
    #
# 

#   def tag_delete_item (user, item):
#       """ whenever a user is deleted, or made inactive with bad karma, this removes
#       any tags that were applied to their items. """
#       user_id = user.get_user_id()
#       item_oid = item._p_oid
#   
#       tidb = get_tagged_item_db()
#       tagdb = get_tags_db()
#       groupdb = None # get group for item
#   
#       if tidb[item_oid].has_key(user_id):
#           attributes = tidb[item_oid][user_id]
#           del tidb[item_oid][user_id]
#   
#           #for tag in attributes.tags:
#               #user.removed_tagged_items(
#   
#           for db in [tagdb, groupdb] :
#               for tag in attributes.tags:
#                   del db[tag][item_oid][user_id]
#               #
#           # 
#       #
#

# ----------------------------------------------------------------------
import qon.karma

def _karma_send_message(fr, to, kind, amount, message, message_anon):
    if message:
        d = {}
        d['display_name'] = qon.ui.blocks.user.display_name_plain(to)
        d['message'] = message
        d['giver'] = qon.ui.blocks.user.display_name_plain(fr)
        d['kind'] = kind
        d['amount'] = amount
        
        subject = 'Feedback received'
        
        if message_anon:
            message_anon_send(to, subject, _anon_karma_message % d)
        else:
            message_send(fr, to, subject, _karma_message % d)

def karma_give_good(fr, to, message=None, message_anon=True, karma=qon.karma.HasKarma.good_karma):
    message = _unicode_fix(message)
    
    if to.can_get_karma_from(fr):
        try:
            fr.give_karma(to, karma)
            _karma_send_message(fr, to, 'positive', '+%d' % karma, message, message_anon)
            transaction_commit(fr, 'KarmaGiveGood')
            qon.search.searchengine.notify_karma_given(to)
        except qon.karma.NoKarmaToGive:
            pass

def karma_give_bad(fr, to, message=None, message_anon=True, karma=qon.karma.HasKarma.bad_karma):
    message = _unicode_fix(message)
    
    if to.can_get_karma_from(fr):
        try:
            fr.give_karma(to, karma)

            # fold tags if the user can't post (?)
            #if to.get_karma_score() < qon.karma.min_karma_to_post

            _karma_send_message(fr, to, 'negative', '%d' % karma, message, message_anon)
            transaction_commit(fr, 'KarmaGiveBad')            
            qon.search.searchengine.notify_karma_given(to)
        except qon.karma.NoKarmaToGive:
            pass

def karma_has_good_to_give(user):
    return user.can_give_karma(qon.karma.HasKarma.good_karma)

def karma_has_bad_to_give(user):
    return user.can_give_karma(qon.karma.HasKarma.bad_karma)

# ----------------------------------------------------------------------
import message

def message_send(fr, to, subject, body, suppress_email=False, copy_self=False):
    """Send a message to one or more recipients."""
    subject = _unicode_fix(subject)
    body = _unicode_fix(body)

    if type(to) is not list:
        to = [to]

    # only send messages to users
    to = [recipient for recipient in to if type(recipient) is User]

    for recipient in to:
        msg = message.Message(sender=fr, subject=subject, body=body)
        recipient.add_message(msg)
        #qon.log.admin_info('added message for %s' % qon.ui.blocks.util.display_name_plain(recipient))

    # log the activity
    fr.get_user_data().get_activity().new_pm_sent()

    # let's commit here so that if the commit fails, we won't accidentally
    #  send out an email notice with the wrong msg # in the URL
    transaction_commit(None, 'NewMessage')  
    
    # email notification
    if (not suppress_email):
        for recipient in to:
            if recipient.email_notify():
                message_email(recipient, msg)

    # email notification to self
    if (not suppress_email) and copy_self:
        message_email_copy_self(fr, to, msg)    


def message_anon_send(to, subject, body, suppress_email=False):
    """Send an anonymous message (from admin user)."""
    subject = _unicode_fix(subject)
    body = _unicode_fix(body)
    
    admin = get_user_database().get_user('admin')
    message_send(admin, to, subject, body, suppress_email)
    

def message_email(to, message):
    """Email a notice to the recipient's primary e-mail address."""
    
    body = _notify_new_message % dict(
        primary=to.display_name(),
#       url=messages.base_url[:-1] + qon.ui.blocks.message.path_to_message(to, message),
        url=messages.base_url[:-1] + qon.ui.blocks.user.path_to_user(to) + 'msg/',
        settings_url=messages.base_url[:-1] + qon.ui.blocks.user.path_to_user_settings(to),
        sender=qon.ui.blocks.util.display_name_plain(message.sender),
        subject=message.subject,
        date=qon.ui.blocks.util.format_datetime(message.date),
        text=message.body,
        )

    #subject = _('Message from %s') % qon.ui.blocks.util.display_name_plain(message.sender)
    #subject = _('%s') % message.subject
    subject = _('PM: from %s: %s') % (qon.ui.blocks.util.display_name_plain(message.sender), message.subject)

    # mark content as utf-8
    extra_headers = ['Content-Type: text/plain; charset=utf-8']
    
    sendmail(subject, body, [to.get_primary_email()], extra_headers=extra_headers)

def message_email_copy_self(fr, to, message):
    """Email a notice to the recipient's primary e-mail address."""
    if type(to) is not list:
        to_name = to.display_name()
    else:
        if len(to) == 1:
            to_name = to[0].display_name()
        else:
            to_name = "all %i users in the group" % len(to)

    body = _notify_new_message_copy_self % dict(
        uid=fr.get_user_id(),
        recipient=to_name,
        sender=qon.ui.blocks.util.display_name_plain(message.sender),
        subject=message.subject,
        date=qon.ui.blocks.util.format_datetime(message.date),
        text=message.body,
        )
    
    #subject = _('Copy of message to %s') % to_name
    #subject = _('%s') % message.subject
    subject = _('PM: to %s: %s') % (to_name, message.subject)

    # mark content as utf-8
    extra_headers = ['Content-Type: text/plain; charset=utf-8']
    
    sendmail(subject, body, [fr.get_primary_email()], extra_headers=extra_headers)
        

# ----------------------------------------------------------------------

def wiki_new_page(wiki, name, author, title, raw):
    '''Called only by qmxlrpc.  Used to create a new wiki page, but
    if the page already exists, it will *not* edit the existing page, but
    instead, return None.'''
    # check to make sure the page doesn't already exist
    if wiki.get_page(name) is not None:
        return None
    
    # ok, we're good to go    
    return wiki_edit_page(wiki, None, name, author, title, raw)

def wiki_edit_page(wiki, page, name, author, title, raw):
    name = _unicode_fix(name)
    title = _unicode_fix(title)
    raw = _unicode_fix(raw)
    
    if page is not None:
        # editing an existing page
        page.new_revision(author=author, title=title, raw=raw)
        author.notify_authored_item(page)        
        transaction_commit(None, 'EditWikiPage')    # moved from wiki/form.ptl/EditWikiPage.commit()
        qon.search.searchengine.notify_edited_wiki_page(page)
    else:
        # when trying to create a new page, ensure raw is not empty
        raw = raw or ' '
        page = wiki.new_page(name)
        page.versions[-1].set_raw(raw)
        page.versions[-1].set_title(title)
        page.versions[-1].set_author(author)
        author.notify_authored_item(page)               
        transaction_commit(None, 'EditWikiPage')    # moved from wiki/form.ptl/EditWikiPage.commit()       
        qon.search.searchengine.notify_new_wiki_page(page)
        
    return page

def wiki_restore_revision(wiki, page, version, author):
    """Restore version as current version of page."""
    
    # don't bother restoring most recent version
    if version is page.versions[-1]:
        return page
        
    edited_page = wiki_edit_page(wiki,
        page=page,
        name=page.name,
        author=author,
        title=version.title,
        raw=version.get_raw(),
        )

    transaction_commit(None, 'RestoreWikiRevision')    # moved from wiki/form.ptl/RestoreRevisionForm.commit()
    return edited_page

def wiki_new_page_like(wiki, page, author):
    np = wiki.new_page(wiki.get_unique_name(page))
    np.versions[-1].set_raw('<include %s latest>\n' % page.name)
    np.versions[-1].set_author(author)
    transaction_commit(None, 'NewLikeWikiPage')     # moved from wiki/wiki.ptl/WikiPageUI.newlike()   
    qon.search.searchengine.notify_new_wiki_page(np)
    return np

# called from qon.ui.wiki.form.EditWikiPage.commit()
def wiki_lock_page(page, user):
    page.lock(user)
    transaction_commit(user, 'LockPage');           # moved from wiki/wiki.ptl/WikiPageUI.lock()

# called from qon.ui.wiki.form.EditWikiPage.commit()
def wiki_unlock_page(page, user):
    page.unlock(user)
    transaction_commit(user, 'UnlockPage');           # moved from wiki/wiki.ptl/WikiPageUI.unlock()

def wiki_delete_page(page):
    wiki = page.wiki
    wiki.remove_page(page)
    transaction_commit(None, 'DeleteWikiPage')     # not moved from anywhere (this is not called by anybody)    
    qon.search.searchengine.notify_deleted_wikipage(page)

def wiki_create_snapshot(group, wiki, user):
    wf = qon.wiki.WikiFile(wiki)
    sf = wf.write_zip(group.file_db)
    sf.owner = user
    transaction_commit(None, 'WikiSnapshot')    # moved from wiki/form.ptl/SnapshotForm.commit()
    

# ----------------------------------------------------------------------
import qon.poll

def poll_create(polls, creator, title, description, end_date, choices):
    title = _unicode_fix(title)
    description = _unicode_fix(description)
    choices = [_unicode_fix(x) for x in choices]
    
    poll = qon.poll.Poll(creator=creator,
        title=title,
        description=description,
        end_date=end_date,
        choices=choices)
    
    poll = polls.add_poll(poll)
    transaction_commit(None, 'PollCreate')
    qon.search.searchengine.notify_new_poll(poll)  
    return poll

def poll_create_custom(polls, creator, title, description, end_date, choices, custom):
    title = _unicode_fix(title)
    description = _unicode_fix(description)
    choices = [_unicode_fix(x) for x in choices]    
    
    """Create a custom poll. custom is a dict with the following keys:
    
    min_choice
    max_choice
    vote_access
    results_access
    intermediate_access
    vote_required_to_view
    voter_can_revise
    display_voters
    min_karma
    karma_cost
    
    Raises KeyError if custom contains keys not recognized by PollData.
    
    """
    poll = qon.poll.Poll(creator=creator,
        title=title,
        description=description,
        end_date=end_date,
        choices=choices)

    # set custom settings
    poll.get_data().set_extended_data(custom)   
    poll = polls.add_poll(poll)
    transaction_commit(None, 'PollCreateCustom')
    qon.search.searchengine.notify_new_poll(poll)  
    
    return poll

def poll_vote(poll, user, choice_list):
    if type(choice_list) is not list:
        choice_list = [choice_list]
        
    try:
        choices = poll.choice_list_to_choices(choice_list)
        poll.record_vote(user, choices)
    except ValueError:
        return None
    transaction_commit(None, 'PollVote')
    qon.search.searchengine.notify_poll_vote(poll)      
    return poll

def poll_cancel(poll, note=None):
    poll.cancel_poll(note)
    transaction_commit(None, 'PollCancel')
    qon.search.searchengine.notify_poll_cancel(poll)      
    
# ----------------------------------------------------------------------
import qon.file

def file_new_directory(group, dir):
    group.file_db.new_dir(parent_dir=dir)
    transaction_commit(None, 'mkdir')  # moved from file.ptl/FileUI.mkdir()  

def file_rename_directory(dir, name):
    name = _unicode_fix(name)
    
    typecheck(dir, qon.file.QonDir)
    dir.filename = name
    transaction_commit(None, 'RenameDir')  # moved from file.ptl/RenameDirForm.commit()

def file_delete_directory(group, dir, parent_dir):
    group.file_db.del_dir(dir, parent_dir=parent_dir)
    transaction_commit(None, 'DeleteDir')  # moved from file.ptl/DeleteDirForm.commit()

def file_delete_file(group, dir, file, unlink=False):
    group.file_db.remove_file(file, unlink=unlink,
        dir=dir)
    transaction_commit(None, 'DeleteFile')  # moved from file.ptl/DeleteFileForm.commit()
        
def file_set_description(file, desc):
    desc = _unicode_fix(desc)
    
    file.description = desc
    transaction_commit(None, 'FileInfo')  # moved from file.ptl/FileInfoForm.commit()

def file_upload(group, dir, owner, source_path, filename, desc):
    filename = _unicode_fix(filename)
    desc = _unicode_fix(desc)
    
    sf = group.file_db.new_file(
        source_path=source_path,
        dir=dir)
    sf.filename = filename
    sf.description = desc
    sf.owner = owner
    transaction_commit(None, 'Upload')  # moved from file.ptl/UploadForm.commit()
    
def file_replace(group, dir, owner, path, source_path, filename, desc):
    """Replace file with path=path in dir=dir, with data at source_path."""
    filename = _unicode_fix(filename)
    desc = _unicode_fix(desc)
    
    sf = group.file_db.replace_file(
        path=path,
        source_path=source_path,
        dir=dir)
    sf.filename = filename
    sf.description = desc
    sf.owner = owner
    transaction_commit(None, 'UploadReplace')   # moved from file.ptl/UploadReplaceForm.commit()

def file_move(group, files, destination):
    """Move the given files to the new destination"""
    group.file_db.move_files(files, destination)
    transaction_commit(None, 'MoveFiles')


# ----------------------------------------------------------------------

def misc_email_page(from_email, to_email, user, subject, personal_message, obj):
    """Email page to a person. May raise smtplib.SMTPRecipientsRefused if server
    rejects email.
    """
    subject = _unicode_fix(subject)
    personal_message = _unicode_fix(personal_message)
    
    if not personal_message:
        personal_message = ''
    else:
        personal_message = "\nPersonal message:\n" + personal_message + '\n'

    # show title in message body only for non-internal groups
    title = ''
    if not qon.ui.blocks.util.is_internal_item(obj):
        title = qon.ui.blocks.util.formatted_display_name_plain(obj)

    url = "http://www.ned.com" + qon.ui.blocks.util.path_to_obj(obj)

    body=_(_email_page_body) % dict(email=to_email,
        sender=qon.ui.blocks.user.display_name_plain(user),
        title = title,
        url = url,
        personal_message = personal_message,
        home_url = messages.home_url)

    sendmail(subject, body, [to_email], from_addr=from_email)        

 

# ----------------------------------------------------------------------

def _set_attributes(object, **kwargs):
    for (key, val) in kwargs.items():
        if hasattr(object, key):   
            setattr(object, key, _unicode_fix(val))
        else:
            raise KeyError
        
# make sure all our text is utf-8 encoded
def _unicode_fix(text):
    if type(text) is unicode:
        return text.encode('utf-8', 'replace')
    return text

# ----------------------------------------------------------------------

_new_forum_title = _('''Welcome to your Discussions!''')
_new_forum_summary = _('''This topic is automatically created when you create a group.
Feel free to delete it, or replace it with your own text!
Before your group becomes active, you have to find another co-sponsor.
Contact your associates and ask them to sponsor this group.
''')

# ----------------------------------------------------------------------

_email_invite_subject = _('''ned.com invitation to join %(group_name)s''')
_email_invite_body=_('''Dear %(email)s,

%(inviter)s has invited you to join the ned.com group %(group_name)s!

In order to accept this invitation to join the group, you'll need to
create an account at www.ned.com/home by clicking the "join us now" link
in the yellow box on the left side of this page:

    %(home_url)s

The sign-up process is quick and easy. All you need to do is give us your
email address, and we'll email you your password.

Once you sign in, click on the green "my ned.com" tab at the top
of the page, and you'll see a list of groups you're invited to join.
Simply click on the group name and decide whether or not to accept
the invitation by clicking the "join this group" button.

Thank you for using ned.com!

The ned.com Team
''')
# ----------------------------------------------------------------------

_email_page_body=_('''Dear %(email)s,

You have been sent this message from %(sender)s as a courtesy of ned.com.
%(personal_message)s
    %(title)s
    %(url)s

ned.com is an online community where you can pursue your passion to make
the world a better place and connect with others who share your interests.
To learn more, click here:

    %(home_url)s

''')
# ----------------------------------------------------------------------

_message_invite_subject = _('''Invitation to join %(group_name)s''')
_message_invite_body=_('''Dear %(email)s,

%(inviter)s has invited you to join the group %(group_name)s.

To accept this invitation or to view all your group invitations, 
click on the my ned.com tab at the top of your screen. 
Your invitations will appear above the list of groups you are 
already a member of.
''')

# ----------------------------------------------------------------------

_new_user_message = _('''<p>Dear %(email)s,<br /><br />

Thank you for signing up with ned.com. Your password is:<br /><br />

    %(password)s<br /><br />

<a href="%(auto_login_url)s">Click here to sign-in for the first time and start learning about how to use ned.com</a><br /><br />

The ned.com Team</p>
''')

_new_password_message = _('''Dear %(email)s,

Someone requested a new password for your account. Your new password is:

    %(password)s

Your old password will continue to work until you explicitly set a new
password on your User Settings page.

To change your password to something easier to remember, sign in, then
select "settings" on the right hand side of the top navigation bar, next
to your name.

Thank you for using ned.com!

The ned.com Team
''')

_confirm_email_message = _("""Dear %(email)s,

To confirm your email address, please visit the following address:

    %(base_url)s%(url)s

and enter this code: %(code)s

This email address will remain unconfirmed until you follow these
instructions.
    
Thank you for using ned.com!

The ned.com Team
""")

_notify_new_email_message = _("""Dear %(primary)s,

This email is to inform you that someone has added the following email
address to your account:

    %(new)s
    
To confirm this addition: you will receive a "confirm your new email"
message from us shortly. To confirm that %(new)s
belongs to your account, simply follow the instructions emailed to you
at that account.
    
If you did not initiate this request, please visit the site, change your
password, and delete any email addresses you don't recognize.

The ned.com Team
""")

_notify_new_message = _("""Dear %(primary)s,

You have received a message from %(sender)s on ned.com. To view or
reply, please visit your inbox on ned.com at:

  %(url)s

The text of the message also follows in this email.

You CANNOT REPLY by email. Please visit the address above to reply.

To change your options to avoid being notified by email when you
receive a message on ned.com, please visit your settings page here:

  %(settings_url)s

The ned.com Team

--------------------------------------------------
From: %(sender)s
Date: %(date)s
Subject: %(subject)s

%(text)s
--------------------------------------------------
""")

_notify_new_message_copy_self = _("""Dear %(sender)s,

Per your request, you have been sent a copy of the following message
you sent to %(recipient)s on ned.com.

To change the email address to which these copies are sent, please
change the primary email address found on your settings page here:

  http://www.ned.com/user/%(uid)s/private/

The ned.com Team

--------------------------------------------------
From: %(sender)s
Date: %(date)s
Subject: %(subject)s

%(text)s
--------------------------------------------------
""")

_notify_group_purged = _("""Dear %(primary)s,

Unfortunately, your group:

  %(group_name)s

was not fully sponsored in the last two weeks, so we are removing it
from the list of pending groups. If you have identified co-sponsors for
your group, you will have to create the group again, and ask the
co-sponsors to sponsor it.

For your convenience, the group description you entered when you created
the group follows this message.

The ned.com Team

--------------------------------------------------
Group name: %(group_name)s
Group description:

%(group_description)s
--------------------------------------------------
""")

_anon_karma_message = _("""Dear %(display_name)s,

A member has given you %(amount)s %(kind)s feedback, and has provided the
following anonymous comment:

--------------------------------------------------

%(message)s

--------------------------------------------------
""")

_karma_message = _("""Dear %(display_name)s,

%(giver)s has given you %(amount)s %(kind)s feedback, and has
provided the following comment:

--------------------------------------------------

%(message)s

--------------------------------------------------
""")

