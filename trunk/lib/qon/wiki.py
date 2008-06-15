"""
$Id: wiki.py,v 1.81 2007/05/31 11:15:34 jimc Exp $
"""
import sys, os, re
import urllib
from datetime import datetime, timedelta
from quixote.html import href, htmlescape, htmltext
from BTrees import OOBTree, IOBTree
from persistent.list import PersistentList

from qon.util import CompressedText, unique_items, coerce_to_list, sort_list, \
    xor_lists, iso_8859_to_utf_8
from qon.base import QonPersistent, PersistentCache, get_user_database, get_group_database
from qon.watch import Watchable
from qon.blog import Blog, IHasBlog
from qon.base import transaction_commit
from qon.watch import never
from qon.observe import Dependencies
import qon.karma

def clean_page_name(name):
    name = name.strip()
    name = name.lower()
    name = re.compile("%\d\d").sub('_', name)        # get rid of things like %20 and %28 (for api)
    name = re.compile("[\W\/]").sub('_', name)
    return name

def resolve_page_name(refname):
    """Return (Group, clean_name, skip). Group is None if missing or invalid. Skip is non-zero
    if refname was /group-name/Page Name, and points to the second slash."""
    
    # is it a full name: /group_name/page name
    if refname.startswith('/'):
        end = refname.find('/', 1)
        if end != -1:
            group_name = refname[1:end].lower()
            skip_index = end + 1
            page_name = clean_page_name(refname[skip_index:])
    else:
        page_name = clean_page_name(refname)
        group_name = None
        skip_index = 0

    # look up group by name
    if group_name:
        try:
            group = get_group_database()[group_name]
        except KeyError:
            group = None
    else:
        group = None
    
    return (group, page_name, skip_index)

def url_to_page_reference(url):
    """Attempt to convert a URL to /group-name/page_name or return None."""
    
    from qon.group import reserved_names
    
    # XXX There must be a better re to make this work instead of using four.
    
    re_name = re.compile(r"/group/([^/]*)/ws/([^/]+)/$", re.IGNORECASE)
    re_name2 = re.compile(r"/group/([^/]*)/ws/([^/]+)$", re.IGNORECASE)    # no trailing slash
    re_name3 = re.compile(r"/group/([^/]*)/([^/]+)/$", re.IGNORECASE)         # group shortcut
    re_name4 = re.compile(r"/group/([^/]*)/([^/]+)$", re.IGNORECASE)
    
    match = re_name.search(url)
    if not match:
        match = re_name2.search(url)
    if not match:
        match = re_name3.search(url)
    if not match:
        match = re_name4.search(url)        
        
    if match:
        group = match.group(1)
        page = urllib.unquote(match.group(2))
        
        if page in reserved_names or group in reserved_names:
            return None
        
        return '/%s/%s' % (group, page)

    return None

def highest_score_items(wikis, count=10):
    """Return list of highest scoring items across multiple wikis.
    
    The order in which tied items are returned is not defined.
    """
    wikis = coerce_to_list(wikis)
    items = []
    for wiki in wikis:
        items.extend(wiki.highest_score_items(count))
        
    bykarma = sort_list(items, lambda x: x.get_karma_score(), count=count)
    return bykarma

def recent_items(wikis, count=10):
    """Return list of recent items across multiple wikis, most recent first,
    with wikis intermingled.
    """
    wikis = coerce_to_list(wikis)
    items = []
    for wiki in wikis:
        items.extend(wiki.recent_changes_with_date())
        
    items.sort()
    items = [i for date, i in items[-count:]]
    items.reverse()
    return items

# --------------------------------------------------------------
# Docutils stuff
# --------------------------------------------------------------
from docutils import nodes
from docutils.readers import standalone
from docutils.transforms import Transform


class WikiLinkResolver(nodes.SparseNodeVisitor):

    def _look_up_wiki_page(self, node):
        refname = node['refname']

        if node.hasattr('refuri') and node['refuri'].startswith("http:"):
            return True
        
        try:
            orig_page_name = node['name']    # as user typed it
        except KeyError:
            # node will have no 'name' attribute if it is an empty reference,
            # like this: |Up: Market Development|_
            return False

        # slashes aren't caught by urllib.quote
        orig_page_name = orig_page_name.replace('/', ' ')

        page_name = None
        group_name = None
        group = None
        
        # is it a full name: /group_name/page name
        (group, page_name, skip_index) = resolve_page_name(refname)
        if skip_index:
            orig_page_name = node['name'][skip_index:]
                
        # if valid group, get the wiki; otherwise, use the one passed in from the Reader
        if group:
            wiki = group.get_wiki()
        else:
            wiki = self.document.settings.wiki
        
        # if we have a wiki, refer into it for the page name
        if wiki:
            import qon.ui.blocks.wiki   # yes, this shouldn't be here

            # get the final group name for our link
            group_name = wiki.group.get_user_id()
            
            # tooltip (hover) text
            if not self.document.settings.suppress_tooltip:
                if not wiki.pages.has_key(page_name):
                    node['class'] = 'newwikipage'
                    node['title'] = 'This page does not exist. Click to create it.'
                else:
                    page = wiki.pages[page_name]
                    node['title'] = qon.ui.blocks.wiki.format_version_title_tooltip(page)
        
            # orig_page_name is unicode now, encode to utf-8 - handles extended chars
            # in `backquoted` references.
            orig_page_name = orig_page_name.encode('utf-8')
            node['refuri'] = urllib.quote(qon.ui.blocks.wiki.path_to_wiki(wiki) + orig_page_name + '/')
            return True
        else:
            return False


    def visit_reference(self, node):
        """For unresolved references, assume they're wiki page names."""
        
        if node.resolved or not node.hasattr('refname'):
            # check if this resolved link uses a URL to refer to a page in this wiki
            
            force_continue = False
            refuri = node.attributes.get('refuri')
            if refuri:
                refname = url_to_page_reference(refuri)
                if refname:
                    # seems like it might be a valid page reference
                    node['refname'] = refname
                    node['name'] = refname
                    force_continue = True

                    if 0:
                        group, page_name, skip_index = resolve_page_name(refname)
                        if group:
                            # seems like a valid URL
                            if group.get_wiki() is self.document.settings.wiki:
                                # this is a link to a page in this wiki
                                node['refname'] = page_name
                                node['name'] = page_name
                                force_continue = True
            
            if not force_continue:
                return
        
        node['class'] = 'wikipage'
                
        # If we were given a wiki, check if this page exists or not
        # and change class appropriately
        if (self._look_up_wiki_page(node)):
        
            # refname might contain a simple page name, or a /group/page_name
            group, page_name, skip_index = resolve_page_name(node['refname'])
            
            # Record list of documents being referred to.
            # Note: group could be None
            self.document._qon_references.append((group, page_name))
            
            del node['refname']
            node.resolved = 1
        else:
            node.resolved = 0
            
    def unknown_visit(self, node):
        """
        Called when entering unknown `Node` types.

        Override to avoid throwing an exception. See docutils.nodes.NodeVisitor.unknown_visit.
        """
        pass
        
class WikiLink(Transform):
    
    default_priority = 800
    
    def apply(self):
        self.document._qon_references = []
        
        self.document.walk(WikiLinkResolver(self.document))
        
class Reader(standalone.Reader):

    supported = standalone.Reader.supported + ('wiki', )
    default_transforms = standalone.Reader.default_transforms \
        + (WikiLink, )

from docutils.writers import html4css1

class HTMLTranslator(html4css1.HTMLTranslator):
    """
    My override of the Docutils HTML translator is to enable hrefs
    to have a title.
    """
    def __init__(self, document):
        html4css1.HTMLTranslator.__init__(self, document)
        
    def visit_reference(self, node):
        """Override to respect setting of `title` key. Unfortunately, I have to copy-paste
        original code and add mine below.
        """
        from docutils import nodes
        
        # begin HTMLTranslator.visit_reference():
        if isinstance(node.parent, nodes.TextElement):
            self.context.append('')
        else:
            self.body.append('<p>')
            self.context.append('</p>\n')
        if node.has_key('refuri'):
            href = node['refuri']
        elif node.has_key('refid'):
            href = '#' + node['refid']
        elif node.has_key('refname'):
            href = '#' + self.document.nameids[node['refname']]
        # end HTMLTranslator.visit_reference(), all but the end of
        # this method, self.body.append(...)
        
        if node.has_key('title'):
            title = node['title']
        else:
            title = ''
        
        self.body.append(self.starttag(node, 'a', '', href=href,
                                       CLASS='reference',
                                       title=title))
    

class Writer(html4css1.Writer):
    """
    Override to install my HTMLTranslator
    """
    def __init__(self):
        html4css1.Writer.__init__(self)
        self.translator_class = HTMLTranslator

# --------------------------------------------------------------
# Qon wiki
# --------------------------------------------------------------

def _ref_to_page(ref, default_group):
    """Convert a (group, page_name) reference to a WikiPage."""

    group, page_name = ref
    if not group:
        group = default_group
    return group.get_wiki().get_page(page_name)

def _sort_refs(refs, current_group):
    """Sort a list of (group, page_name), within the current_group."""
    byname = []
    for refgroup, refname in refs:
        if refgroup and refgroup is not current_group:
            group_id = refgroup.get_user_id()
        else:
            group_id = ' '  # sort first
        byname.append((group_id+refname, refgroup, refname))

    byname.sort()
    return [(refgroup, refname) for sort_id, refgroup, refname in byname]

 
class Wiki(QonPersistent, Watchable):

    persistenceVersion = 1
    _inactive_period            = timedelta(days=7)
    _inactive_karma_discount    = 1

    def __init__(self, group):
        Watchable.__init__(self)
        self.group = group
        self.pages = OOBTree.OOBTree()
        self.__cached_recent_changes = PersistentCache(self._update_recent_changes_cache)
        self.index_page = WikiPage(self, name='index')
        self.pages['index'] = self.index_page
        self.index_page.versions[-1].set_raw(_default_index_page % \
            dict(top_header='='*len(self.group.name),
                bottom_header='='*len(self.group.name),
                title=self.group.name,
                group_name=self.group.get_user_id()
                )
            )
        self.index_page.versions[-1].set_date(datetime.utcnow())
        self.index_page.versions[-1].set_author(self.group.owners[0])
        self.index_page.versions[-1].set_title(self.group.name)
        self.__uniques = OOBTree.OOBTree()

        self._create_default_pages()
        
    def upgradeToVersion1(self):
        self.__cached_recent_changes = PersistentCache(self._update_recent_changes_cache)
        self.version_upgrade_done()
        
    def new_page(self, name):
        page = WikiPage(self, name)
        name = clean_page_name(name)
        self.pages[name] = page
        self.watchable_changed(page.versions[-1].date)
        self._p_changed = 1
        return page

    def remove_page(self, page):
        del self.pages[page.name]
        if self.__uniques.get(page.name):
            del self.__uniques[page.name]
        
    def get_page(self, page_name):
        """Return page or None."""
        # jimc: not cleaning the page name
        # led to case differences wiping out
        # an old workspace page.
        name = clean_page_name(page_name)

        if self.pages.has_key(name):
            return self.pages[name]
        return None

    def decay_inactive_items(self):
        """Call this daily to decay karma of inactive items.
        Returns a list of items that were decayed.
        """
        # XXX This could be refactored into an interface shared by
        # XXX Wiki.decay_inactive_items and Blog.decay_inactive_items

        decayed_items = []
        decay_time = datetime.utcnow() - self._inactive_period
        for page_name, item in self.pages.iteritems():
            if item.get_karma_score() > 0:
                if item.watchable_last_change() < decay_time:
                    item.add_anon_karma(-self._inactive_karma_discount)
                    decayed_items.append(item)
        return decayed_items

    def recent_changes(self):
        """Returns list of pages sorted newest first."""
        return [page for date, page in self.recent_changes_with_date()]
        
    def _update_recent_changes_cache(self):
        bydate = []
        for name, page in self.pages.items():
            bydate.append((page.watchable_last_change(), page))
        bydate.sort()
        bydate.reverse()
        return bydate
        
    def recent_changes_with_date(self):
        return self.__cached_recent_changes.get()
        
    def recent_edits_by_author(self, author, count=10):
        """Return count pages most-recently edited by author."""
        edits = []
        for name, page in self.pages.items():
            version = page.latest_edit_by(author)
            if version:
                edits.append(page)
        
        edits = sort_list(edits, lambda x: x.watchable_last_change(), count=count)
        return edits        
    
    def recent_comments_by_author(self, author, count=10):
        """Return count most-recent comments by author in this wiki. Returns list of (page, comment)
        tuples.
        """
        bydate = []
        for page in self.pages.values():
            bydate.extend([(c.date, page, c) for c in page.get_comments() if c.author is author])
        
        bydate.sort()
        
        comments = [(page, comment) for date, page, comment in bydate[-count:]]
        comments.reverse()
        return comments

    def num_pages(self):
        return len(self.pages)

    def num_active_pages(self, days=3):
        """Returns the number of pages that have been modified in the last X days
        Also returns the date of the latest page, in case it's useful"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        # active_pages = [p for p in self.pages if p.watchable_last_change() > cutoff_date]      // slower because it creates a new list
        # return len(active_pages)         
        num = 0
        latest_date = never        
        for n, p in self.pages.items():
            mod = p.watchable_last_change()
            if mod > cutoff_date:
                num += 1
            if mod > latest_date:
                latest_date = mod                
        return (num, latest_date)
        
    def search_pages(self, text_to_find):
        """Search pages for text. Slow and lame. Fix me, please."""
        if text_to_find is None:
            return []
            
        matching = []
        text_to_find = text_to_find.strip().lower()
        
        for page_name in self.pages.keys():
            page = self.pages[page_name]
            if page.name.find(text_to_find) != -1:
                matching.append(page)
            elif page.versions[-1].title.find(text_to_find) != -1:
                matching.append(page)
            elif page.versions[-1].get_raw().lower().find(text_to_find) != -1:
                matching.append(page)
        return matching
        
    def references_to(self, page, all=1, all_groups=1):
        """Return pages which refer to page. If all is false, returns first match."""
        
        # if page has up-to-date inbound_references
        if hasattr(page, 'inbound_references') and page.inbound_references is not None:
            matching = []
            sorted_refs = _sort_refs(page.inbound_references, self.group)
            for ref in sorted_refs:
                if all:
                    matching.append(_ref_to_page(ref, self.group))
                else:
                    return _ref_to_page(ref, self.group)
            return matching
        
        # otherwise recompute inbound_references
        matching = []
        for n, p in self.pages.iteritems():

            if not p.outbound_references:
                continue
                
            for group, name in p.outbound_references:
                # For same-group references, group is None
                if group is None and (page.name == name):
                    if all:
                        matching.append(p)
                    else:
                        return p

        # now look through all other groups
        if all_groups:
            for group_id, group in get_group_database().root.iteritems():
                wiki = group.get_wiki()
                for n, p in wiki.pages.iteritems():

                    if not p.outbound_references:
                        continue
                    
                    for refgroup, refname in p.outbound_references:
                        if refgroup is self.group and (page.name == refname):
                            if all:
                                matching.append(p)
                            else:
                                return p

        # convert to references format
        in_refs = [p.get_ref() for p in matching]

        # sort references for storage
        in_refs = _sort_refs(in_refs, self.group)

        # record inbound_references in page, since we just recomputed it all
        page.inbound_references = PersistentList(in_refs)

        # return sorted references
        matching = [_ref_to_page(ref, self.group) for ref in in_refs]
        return matching
        
    backlinks = references_to
    
    def is_orphan(self, page):
        """Returns true if page has no references to it, unless it's the index page."""
        if page is self.index_page:
            return False
        if self.references_to(page, all=0):
            return False
        return True

    def highest_score_items(self, count=10):
        """Return list of pages with highest karma, highest first. Zeros are filted out."""
        bykarma = []
        for n, p in self.pages.items():
            bykarma.append((p.get_karma_score(), p.watchable_last_change(), p))
        bykarma.sort()
        items = [p for karma, date, p in bykarma[-count:] if karma > 0]
        items.reverse()
        return items
    
    def orphans(self):
        """Return pages which are not referred to."""
        orphans = []
        for name, page in self.pages.items():
            if not self.references_to(page, all=0):
                orphans.append(page)
                
        bydate = [(p.watchable_modified_date(), p) for p in orphans]
        bydate.sort()
        bydate.reverse()
        return [p for d, p in bydate]
        
        
    def get_unique_name(self, page):
        """Return a unique name using page.name as prefix."""
        cur_index = self.__uniques.get(page.name, 0)
        cur_index += 1
        while self.pages.has_key(page.name + str(cur_index)):
            cur_index += 1
        self.__uniques[page.name] = cur_index
        return page.name + str(cur_index)
        
    def watchable_name(self):
        return self.group.name + ' Workspace'
        
    def watchable_changed(self, now=None):
        Watchable.watchable_changed(self, now)

        # flush recent changes cache
        self.__cached_recent_changes.flush()

        # group changed, too
        self.group.watchable_changed(now)

    def watchable_modified_date(self):
        return self.watchable_last_change()

    def can_read(self, user):
        return self.group.can_read(user)
        
    def _create_default_pages(self):
        pass
        if 0:
            # There should only be a single Puntuation Help page: /help/Punctuation Help
            page = self.new_page('Punctuation Help')
            page.versions[-1].set_raw(_punc_help)
            
            page.versions[-1].set_date(datetime.utcnow())
            page.versions[-1].set_author(self.group.owners[0])
            page.versions[-1].set_title('Punctuation Help')
    
    
class WikiPage(QonPersistent, Watchable, qon.karma.HasKarma, IHasBlog):

    persistenceVersion = 4

    def __init__(self, wiki, name=''):
        Watchable.__init__(self)
        qon.karma.HasKarma.__init__(self)
        self.wiki = wiki
        self.outbound_references = None
        self.inbound_references = None
        self.name = clean_page_name(name)
        self.versions = PersistentList()
        self.blog = Blog(self)
        self.locked_by_user = None
        self.__cached_html = PersistentCache(self._update_html_cache)
        self.__cached_html2 = PersistentCache(self._update_html2_cache)
        self.new_revision(force_new=1)
        
    def upgradeToVersion4(self):
        self.inbound_references = None
        self.version_upgrade_done()

    def upgradeToVersion3(self):
        self.__cached_html2 = PersistentCache(self._update_html2_cache)
        self.version_upgrade_done()

    def upgradeToVersion2(self):
        self.__cached_html = PersistentCache(self._update_html_cache)
        self.version_upgrade_done()

    def upgradeToVersion1(self):
        self.blog.ihb = self
        self.version_upgrade_done()
        
    def __repr__(self):
        return '<%s object at 0x%x: %s>' % (self.__module__ + '.' + self.__class__.__name__,
            id(self), self.name or "*no name*")

    def new_revision(self, set_date=True, author=None, title='', raw='', force_new=0):
        """Create a new revision for this page.
        
        Check to make sure that the new text is actually different
        from the latest revision.  If it's not, then don't bother creating a
        new revision."""
        if force_new or (self.versions[-1].get_raw() != raw):
            w = WikiVersion(page=self, author=author, title=title, raw=raw)
            if set_date:
                w.set_date(datetime.utcnow())
            self.versions.append(w)
            
            self.watchable_changed(w.date)
            if author:
                author.karma_activity_credit()
                
            # before invalidating referring pages, we want to 
            # update the html cache, which has the side effect
            # of updating the outbound references.
            self.invalidate_html_cache()
            unused_html = self.get_cached_html()

            # may seem useless for new pages, but we could be creating
            # a new page that was referred to from another page somewhere
            self._invalidate_referring_pages()
            
            self._p_changed = 1
            
    def _invalidate_referring_pages(self, all_groups=0):
        """Invalidate HTML cache of pages which refer to this one."""

        # we changed default behavior to not scan all groups when invalidating.
        # this means that cross-group links for new pages after this change
        # will not be accurate, until the page(s) linking to the new page
        # is itself modified.

        refs = self.wiki.references_to(self, all_groups=all_groups)
        for p in refs:
            p.invalidate_html_cache()
        
    def latest_edit_by(self, user):
        """Return latest edit by user, or None."""
        rvers = self.versions[:]
        rvers.reverse()
        for version in rvers:
            if version.author is user:
                return version
        return None
        
    def get_comments(self):
        """Return list of comments (BlogItems)."""
        blog_item = self.blog.get_item(0)
        if blog_item:
            return blog_item.get_comments()
        else:
            return []
        
    def get_revision(self, rev_id):
        """Return revision index rev_id or None."""
        rev_id = max(0, rev_id)
        try:
            rev = self.versions[rev_id]
        except IndexError:
            rev = None
        return rev

    def revision_index(self, version):
        """Return revision index of version, or raise ValueError."""
        return self.versions.index(version)

    def merge_revisions(self, base, old, new):
        """Merge the newest revision with older revision, off of base. Returns (merged text, exit_code) or None.
        
        Base may be -1 to signify empty text.
        Exit code is 0 for no conflicts, or 1 if conflicts exist.
        """
        if len(self.versions) < 2:
            return None

        if base == -1:
            base_text = ''
        else:
            base_text = self.versions[base].get_raw()

        old_text = self.versions[old].get_raw()
        new_text = self.versions[new].get_raw()

        merger = Merger(base_text, old_text, new_text)
        merged = merger.merge('Revision %d' % base,
            'Revision %d' % old,
            'Revision %d' % new,
            )

        if not merged:
            return None

        exit_code = 0
        if merger.has_conflicts():
            exit_code = 1

        return (merged, exit_code)


    def watchable_name(self):
        #return self.wiki.group.name + ' ' + self.versions[-1].title
        return self.versions[-1].title or self.name
        
    def watchable_changed(self, now=None):
        # wiki changed, too
        Watchable.watchable_changed(self, now)
        self.wiki.watchable_changed(now)

    def watchable_modified_date(self):
        return self.watchable_last_change()
        
    def last_modified(self):
        sys.stderr.write('WARNING: using deprecated qon.wiki.WikiPage.last_modified.')
        return self.watchable_last_change()

    def who_has_lock(self):
        return self.locked_by_user

    def can_edit(self, user):
        """ A page is editable if either it's not locked by anybody,
        or if the requesting user is the one who holds the lock, or
        if the user is allowed to edit within the group"""
        
        # user must be logged in to edit
        if not user:
            return False
            
        # check lock
        if (self.locked_by_user) and (self.locked_by_user is not user) and (not self.can_manage(user)):
            return False
            
        if self.wiki.group.can_edit(user):
            return True
        
        return False
        
    def can_show(self):
        """Return False if this item should be suppressed due to feedback score."""
        if self.get_karma_score() < qon.karma.min_karma_to_show:
            return False
        return True
        

    def can_lock(self, user):
        """ For now, let only a group owner lock/unlock a page.
        In the future, we may want to consider allowing the original
        page author to lock/unlock as well."""
        return self.wiki.group.is_owner(user)

    def lock(self, user):
        if self.can_lock(user):
            self.locked_by_user = user

    def unlock(self, user):
        if self.can_lock(user):
            self.locked_by_user = None
            
    def can_get_karma_from(self, other):
        return other is not None
        
    # HTML cache methods
    
    def add_html_dependency(self, target):
        """Adds target as something self depends on for its HTML cache."""
        self.__cached_html.add_dependency(target)
        self.__cached_html2.add_dependency(target)
        
    def invalidate_html_cache(self):
        self.__cached_html.flush()
        self.__cached_html2.flush()
        
    def get_cached_html(self):
        return self.__cached_html.get()

    def get_cached_html2(self):
        return self.__cached_html2.get()

    def _update_html_cache(self):
        
        v = self.versions[-1]
        html = v.raw_to_html(v.get_raw())
        
        # take this opportunity to update the page's outbound references
        if hasattr(v, '_v_references'):
            self.set_outbound_references(v._v_references)
            del v._v_references
            
        return html

    def _update_html2_cache(self):
        
        v = self.versions[-1]
        html = v.raw_to_html(v.get_raw(), suppress_tooltip=1)
        
        return html

    def disable_cache(self):
        self.__cached_html.disable_cache()
        self.__cached_html2.disable_cache()

    def cache_disabled(self):
        return self.__cached_html.cache_disabled() or self.__cached_html2.cache_disabled()
  
    def get_ref(self):
        """Return a reference (group, page_name) to this page, for use in
        outbound/inbound references."""
        return (self.wiki.group, self.name)
            
    def set_outbound_references(self, new_out_refs):
        """Record new outbound references."""

        # filter non-existent cross-group page refs out of new_out_refs
        # this interacts with the change that no longer scans all groups
        # for references to new pages. if a cross-group link existed to a new
        # page, this method (pre-filtering) would have neglected to add the inbound
        # link from the cross-group reference, even if both pages had been edited.
        l = []
        for r in new_out_refs:
            group_name, page_name = r
            if not group_name:
                l.append(r)
            else:
                page = _ref_to_page(r, self.wiki.group)
                if page:
                    l.append(r)
        new_out_refs = l

        # get old outbound refs
        old_out_refs = self.outbound_references or []

        # get two lists: items that used to be outbound references but
        # are no longer (old_not_new), and new outbound references that
        # weren't there before (new_not_old)
        old_not_new, new_not_old = xor_lists(old_out_refs, new_out_refs)

        # pre-fill reference to me
        me_ref = self.get_ref()

        # invalidate inbound references of pages that we no longer refer to
        for ref in old_not_new:
            page = _ref_to_page(ref, self.wiki.group)
            if page:    # added by Alex
                page.remove_inbound_reference(me_ref)

        # add inbound references for pages we've added outbound links to
        for ref in new_not_old:
            page = _ref_to_page(ref, self.wiki.group)
            if page:    # could be ref to new page
                page.add_inbound_reference(me_ref)

        # record new outbound references
        self.outbound_references = PersistentList()
        self.outbound_references.extend(new_out_refs)

    def remove_inbound_reference(self, ref):
        if self.inbound_references is not None:
            if ref in self.inbound_references:
                self.inbound_references.remove(ref)

    def add_inbound_reference(self, ref):
        if self.inbound_references is not None:
            if ref not in self.inbound_references:
                self.inbound_references.append(ref)

    # IHasBlog methods not implemented by other base classes
    
    def can_manage(self, user):
        """Who can manage this blog? Group owners."""
        return self.wiki.group.is_owner(user)
        
    def can_read(self, user):
        return self.wiki.can_read(user)
        
    def can_delete_item(self, item):
        """Can't delete item 0, which holds page comments."""
        if self.blog.get_item(0) is item:
            return False
        return True
        
    def can_create_item(self):
        """Users aren't allowed to create new topics in wiki pages."""
        return False
    
    def is_accepted(self):
        return self.wiki.group.is_accepted()
    
    def get_owners(self):
        return self.wiki.group.get_owners()
    
    def is_owner(self, user):
        return self.wiki.group.is_owner(user)
        
    def get_title(self):
        # this is here and in BlogItem
        return self.versions[-1].title or self.name
    
    def get_blog(self):
        return self.blog
    
    def get_wiki(self):
        return self.wiki
    
    def get_name(self):
        return self.name
    
    def get_all_owners(self):
        return self.get_owners()
    
    def get_all_blogs(self):
        return [self.blog]
        
    def get_member_list(self):
        return self.wiki.group.get_member_list()
            
        
class WikiRawText(CompressedText):
    """Minimal class to hold text so WikiVersion doesn't have to read
    complete text off the disk unless it's really needed.
    """
    persistenceVersion = 1
    
    def upgradeToVersion1(self):
        """Refactored code into qon.util.CompressedText."""
        if hasattr(self, '_WikiRawText__raw'):
            self._CompressedText__raw = self._WikiRawText__raw
            del self._WikiRawText__raw
        self.version_upgrade_done()

class WikiVersion(QonPersistent):

    persistenceVersion = 1

    def __init__(self, page, author=None, title='', raw=''):
        self.page = page
        self.date = None
        self.author = None
        self.title = ''
        self.__raw = WikiRawText(raw)
        
        if author:
            self.set_author(author)
        if title:
            self.set_title(title)
            
    def upgradeToVersion1(self):
        self.title = iso_8859_to_utf_8(self.title)
        
    def html(self, debug=0):
        """Return wiki text converted to HTML. If debug is set, ask parser to report errors."""
        
        # don't use cache for debug, or for any revision other than most current
        if debug or (self is not self.page.versions[-1]):
            return self.raw_to_html(self.get_raw(), debug=debug)
        else:
            return self.page.get_cached_html()
            
    def html2(self, debug=0):
        """Return wiki text converted to HTML, second version (no tooltips)."""
        
        # don't use cache for debug, or for any revision other than most current
        if debug or (self is not self.page.versions[-1]):
            return self.raw_to_html(self.get_raw(), debug=debug, suppress_tooltip=1)
        else:
            return self.page.get_cached_html2()
            
    def get_raw(self):
        return self.__raw.get_raw()
    
    def set_raw(self, raw):
        self.__raw.set_raw(raw)
        self.page.invalidate_html_cache()
        
    def set_title(self, title):
        self.title = title
        
    def set_author(self, author):
        self.author = author
        
    def set_date(self, date):
        self.date = date
            
    def raw_to_html(self, raw, debug=0, suppress_tooltip=0):
        """Convert raw test to HTML and return it.
        
        Pass a non-zero numeric value to debug: none/5, info/1, warning/2, error/3, severe/4, or
        zero for no debug (same as 5).
        """
        from qon.ui.blocks.wiki import rst_to_html
        reader = Reader()

        html = rst_to_html(raw, wiki=self.page.wiki, container=self.page, reader=reader,
            debug=debug,
            suppress_tooltip=suppress_tooltip,
            )
        
        # rst parser keeps track of outbound wiki links. extract them
        # and store them in version, for use by Wiki
        refs = getattr(reader.document, '_qon_references', None)
        if refs:
            self._v_references = unique_items(refs)

        return html

class Merger(object):
    """A class which merges two branches from a common ancestor using
    the `merge` tool.
    
    m = Merger(common, branch1, branch2)
    m.merge(common_label, branch1_label, branch2_label)
    """

    def __init__(self, common, b1, b2):
        self.common = common
        self.b1 = b1
        self.b2 = b2
        self.exit = 0

    def has_conflicts(self):
        return self.exit == 1

    def merge(self, label1='', label2='', label3=''):
        """Merge files and return the merged text, or None if an error occurred."""
        
        import tempfile

        # create temp directory to contain files for merge
        prefix = 'qon_merge_'
        dir_path = tempfile.mkdtemp(prefix=prefix)
        fcom_path = os.path.join(dir_path, 'common')
        fb1_path = os.path.join(dir_path, 'branch1')
        fb2_path = os.path.join(dir_path, 'branch2')

        # create temp files
        for info in [(fcom_path, self.common), (fb1_path, self.b1), (fb2_path, self.b2)]:
            f = open(info[0], 'w')
            f.write(info[1])
            f.close()
        
        # get file labels for output
        label1 = label1 or 'file1'
        label2 = label2 or 'file2'
        label3 = label3 or 'file3'

        # run diff3: b1 com b2

        # open a pipe to merge
        # redirect stdin to /dev/null to overcome a child-process "bad file descriptor"
        # error when running under quixote
        p = os.popen("/usr/bin/merge -p -q -L '%s' -L '%s' -L '%s' '%s' '%s' '%s' < /dev/null" % (
            label2, label1, label3,
            fb1_path, fcom_path, fb2_path,
            ))

        # read output, which is merged file
        merged = p.read()

        # close pipe and get exit code
        self.exit = p.close()

        if self.exit:
            # got non-None exit code, actual process exit code
            # is in upper byte (see wait())
            self.exit = self.exit >> 8
        else:
            self.exit = 0

        # diff3 returns 0 for no conflicts, 1 for conflicts, 2 for trouble
        if self.exit not in [0, 1]:
            merged = None

        # delete temp files
        os.remove(fcom_path)
        os.remove(fb1_path)
        os.remove(fb2_path)
        os.rmdir(dir_path)
            
        return merged

# --------------------------------------------------------------
# File stuff
# --------------------------------------------------------------

def datetime_from_iso(iso):
    re_iso = re.compile("(\d\d\d\d)-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d).(\d+)")
    match = re_iso.match(iso)
    if match:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)),
            int(match.group(4)), int(match.group(5)), int(match.group(6)), int(match.group(7)))
    else:
        return None
    
class WikiFile:
    """Class to manage file input/output"""
    
    _revdir_name = 'rev.rev'    # must not conflict with valid wiki page name
    
    def __init__(self, wiki):
        self.wiki = wiki
        
    def read_dir(self, path):
        """Read a directory and create wiki pages for each of the files found."""
        
        revpath = os.path.join(path, self._revdir_name)
        for name in os.listdir(revpath):
            page = self.wiki.new_page(name)
            page.versions = []
            pagepath = os.path.join(revpath, name)
            
            revs = os.listdir(pagepath)
            revs.sort()
            for rev in revs:
                f = open(os.path.join(pagepath, rev), 'r')
                page.new_revision(set_date=False, author=None, title='', raw=f.read())
                f.close()
                page.versions[-1].date = None
        
            
    def write_dir(self, path):
        """Write each wiki page into a file in given directory.
        
        Warning: will clobber existing files.
        Directory format:
            path/           contains flat files with latest version of each file
            path/rev/name/  contains past revisions of name   
            e.g. path/rev/index/0 is rev 0 of wiki.pages['index']
        """
        
        def check_dir(path):
            if not os.access(path, os.R_OK|os.W_OK|os.X_OK):
                os.mkdir(path)
                
        check_dir(path)
        revpath = os.path.join(path, self._revdir_name)
        check_dir(revpath)
            
        for name, page in self.wiki.pages.items():
            f = open(os.path.join(path, name), 'w')
            f.write(page.versions[-1].get_raw())
            f.close()
            
            revdir = os.path.join(revpath, name)
            check_dir(revdir)
            
            index = 0
            for ver in page.versions:
                filename = os.path.join(revdir, str(index))
                f = open(filename, 'w')
                f.write(ver.get_raw())
                f.close()
                index += 1
                
    def _get_snapshot_dir_name(self):
        date = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        return 'snapshot-%s/' % date
        
    def _create_file(self, file_db, source_path, filename):
        sf = file_db.new_file(source_path=source_path)
        sf.filename = filename
        return sf
        
    def write_zip(self, file_db):
        """Create a zip file snapshot of wiki, inserted into file_db.
        
        Returns QonFile object.
        """
        import zipfile, tempfile, shutil
        
        dirname = self._get_snapshot_dir_name()
        path = tempfile.mkdtemp()
        self.write_dir(os.path.join(path, dirname))
        
        zip_temp = tempfile.mkstemp('.zip')[1]
        zip_file = zipfile.ZipFile(zip_temp, 'w')
        
        for root, dirs, files in os.walk(os.path.join(path, dirname)):
            # arcdir is everything in path starting from dirname
            arcdir = root[root.find(dirname):]
            for f in files:
                zip_file.write(os.path.join(root, f), os.path.join(arcdir, f))
        
        zip_file.close()
        
        sf = self._create_file(file_db, zip_temp, 'Workspace Snapshot.zip')
        shutil.rmtree(path)
        os.unlink(zip_temp)
        
        return sf

# --------------------------------------------------------------
# One-time upgrades
#
# Upgrades that don't require a bump in persitenceVersion; these
# are probably called from the command-line
# --------------------------------------------------------------

def upgrade_inbound_refs():
    """Recreate all pages' inbound_references."""
    from base import get_group_database
    
    group_db = get_group_database()
    for g in group_db.root.values():
        for p in g.wiki.pages.values():
            refs = g.wiki.references_to(p)
        transaction_commit()
        print g.get_user_id()

def upgrade_refresh_html_caches():
    """Refresh all html caches."""
    from base import get_group_database
    
    group_db = get_group_database()
    for g in group_db.root.values():
        for p in g.wiki.pages.values():
            html = p.get_cached_html()
            transaction_commit()

def upgrade_invalidate_outbound_refs():
    """Invalidate all outbound references due to type change."""
    from base import get_group_database
    
    group_db = get_group_database()
    for g in group_db.root.values():
        for p in g.wiki.pages.values():
            p.outbound_references = None
            p.invalidate_html_cache()
        transaction_commit()

def upgrade_invalidate_html_caches():
    """Invalidate all HTML caches"""
    from base import get_group_database
    
    group_db = get_group_database()
    for g in group_db.root.values():
        for p in g.wiki.pages.values():
            p.invalidate_html_cache()
        transaction_commit()

def upgrade_wiki_raw_text_format():
    """Compress all old revisions."""
    from base import get_group_database
    import transaction
    group_db = get_group_database()
    for g in group_db.root.values():
        for p in g.wiki.pages.values():
            for v in p.versions:
                v.set_raw(v.get_raw())
            transaction.commit(True)

def add_group_to_wiki_page_blog():
    """Add group reference to each instance of Blog in each WikiPage"""
    from base import get_group_database
    
    group_db = get_group_database()
    for g in group_db.root.values():
        for p in g.wiki.pages.values():
            if not p.blog.ihb:
                p.blog.ihb = g


_default_index_page = '''
%(top_header)s
%(title)s
%(bottom_header)s

*Replace this text with your own description of this group.*

.. contents::

Getting Started
===============

A workspace is different. It's a place where people can work on writing
documents together. Anyone can edit, assuming the group permissions
allow it. Just click Edit on the menu bar at the top of the screen, and
you'll see what I mean.

As you begin to edit more and more complex documents, it's important to
keep this `plain text` clean. Don't be overly concerned about the
*presentation* of your document; instead, focus on the content and
readability in the plain text. If it isn't readable in the Edit box,
your colleagues won't be able to contribute.

One fun thing about workspaces is that you can create new pages just by
naming them in your document. For example, here's a new page now:
Sandbox_ Notice that it's a single word, and followed by a single
underscore. If I wanted to create a page with multiple words, I would
enclose the page in back-ticks, like this: `My experiments`_  To get
that, I typed this: ```My experiments`_``

But remember, just creating a new page doesn't make it easy to find. And
if other people can't find your page, what's the point of working on it?
Make sure you don't create `orphans.` Always think about linking to your
pages from a Home page of some sort. If you can't think of a Home page
for your pages, then at least use an Index page to gather them all in
one place.

Now, another tip on how to format your documents. Remember, the plain
text is the most important thing: it has to be readable to be useful.
So, use plenty of white space. Always leave a blank line between
paragraphs, and before and after headings or lists. Just take a look at
the plain text of this document, and you'll see what I mean.

Also remember to start every paragraph at the left edge of the Edit box;
don't indent paragraphs like they taught you in typing class. If you
indent a paragraph in the plain text, it will end up indented a lot more
on the web page. Use that to your advantage when you like, but
sparingly.

Beyond that, there are a few fancy tricks you might want to learn as you
get more familiar with this workspace. Be sure to refer to the
`/help/Punctuation Help`_ document to learn more if you get stuck.

Now, it's time to get back to work!

Announcements
=============

*Add announcements here*


Directory
=========

*Items you may want to include in your group workspace.*

- People_
- Projects_
- Resources_
'''

