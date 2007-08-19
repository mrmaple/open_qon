"""
$Id: atom.py,v 1.8 2005/06/14 05:47:29 jimc Exp $

Atom support

:Author:    Jim Carroll
"""
import sha, base64, re
from datetime import datetime, timedelta

from qon.util import dt_to_iso, iso_to_dt

# max age to accept attempted authentication
_max_nonce_age = timedelta(seconds=3*60)


def create_nonce():
    """Return a cryptographically random string."""
    default_seed = 'ifh2847fhsn"lqOEYd@#Djh(&'
    hash = sha.new(default_seed)
    hash.update(str(datetime.utcnow()))
    return hash.hexdigest()
    
def create_password_digest(password, creation=None, nonce=None):
    """Create a password digest using the given creation time in ISO 8601,
    or use the current time. Returns (digest, creation, nonce).
    """
    if not creation:
        creation = dt_to_iso(datetime.utcnow())
    
    if not nonce:
        nonce = create_nonce()
        
    digest = base64.encodestring(nonce + creation + password).replace("\n", "")
    return (digest, creation, nonce)
    
def create_authorization_header(username, password, creation=None, nonce=None):
    """Create and return an authorization header. Returns (header, creation, nonce)."""
    
    digest, creation, nonce = create_password_digest(password, creation, nonce)
    
    header = 'UsernameToken Username="%s", PasswordDigest="%s", Created="%s", Nonce="%s"' % (
        username, digest, creation, nonce
        )
    
    return (header, creation, nonce)

def valid_password_digest(password, digest, creation, nonce, max_age=None):
    """Return True if digest is a valid digest of password.
    
    >>> digest, creation, nonce = create_password_digest('foo')
    >>> valid_password_digest('foo', digest, creation, nonce)
    True
    >>> digest, creation, nonce = create_password_digest('foo', '2005-01-01T12:00:00Z')
    >>> valid_password_digest('foo', digest, creation, nonce)   # too old
    False
    """
    
    if not digest or not creation or not nonce:
        return False
        
    if not max_age:
        max_age = _max_nonce_age
    
    # don't accept creation times that are too old
    now = datetime.utcnow()
    created_dt = iso_to_dt(creation)
    if (now - created_dt) > max_age:
        return False
    
    test_digest, ignore_x, ignore_y = create_password_digest(password, creation, nonce)
    return test_digest == digest

def parse_authorization_header(header):
    """Parse a header as returned by create_authorization_header into its
    component parts. Returns tuple containing (username, password_digest, created, nonce).
    
    >>> header, creation, nonce = create_authorization_header('foo', 'bar')
    >>> digest, creation, nonce = create_password_digest('bar', creation, nonce)
    >>> p_username, p_digest, p_created, p_nonce = parse_authorization_header(header)
    >>> p_username == 'foo'
    True
    >>> p_digest == digest
    True
    >>> p_created == creation
    True
    >>> p_nonce == nonce
    True
    
    >>> from qon.user import User
    >>> foo = User('jimc')
    >>> foo.set_password('bar')
    >>> header, creation, nonce = create_authorization_header('foo', foo.get_password_hash())
    >>> username, digest, created, nonce = parse_authorization_header(header)
    >>> username == 'foo'
    True
    >>> valid_password_digest(foo.get_password_hash(), digest, created, nonce)
    True
    """
    
    re_header = re.compile('UsernameToken\s+Username="(.*)",\s+PasswordDigest="(.*)",\s+Created="(.*)",\s+Nonce="(.*)"')
    
    match = re_header.match(header)
    if match:
        return match.groups()
    return None
    

class Feed(object):
    """Represents an Atom feed."""
    
    def __init__(self):
        self.version = "0.3"    # required
        self.lang = "en-US"     # optional
        self.title = None       # required
        self.url = None         # required
        self.author = None      # optional if each entry has author
        self.contributors = []  # optional
        self.tagline = None     # optional
        self.id = None          # optional
        self.generator = None   # optional
        self.copyright = None   # optional
        self.info = None        # optional
        self.modified = None    # required: format ISO 8601: 2003-12-13T18:30:02Z
        self.entries = []

    def set_modified(self, dt):
        """Takes a UTC DateTime."""
        self.modified = dt_to_iso(dt)

    def output(self):
        """Return feed as XML string."""
        feed = []
        feed.append('''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <?xml-stylesheet href="http://www.blogger.com/styles/atom.css" type="text/css"?>
            <feed version="%(version)s" xmlns="http://purl.org/atom/ns#" xml:lang="%(lang)s">
            <title mode="escaped" type="text/html">%(title)s</title>
            <link rel="alternate" type="text/html" href="%(url)s" />
            <modified>%(modified)s</modified>
            ''' % self.__dict__
        )
        
        # auto-generate info if none provided
        if self.info:
            feed.append('''<info>%s</info>''' % self.info)
        else:
            feed.append('''<info mode="xml" type="text/html">
                <div xmlns="http://www.w3.org/1999/xhtml">This is an Atom formatted XML site feed. It is intended to be viewed in a Newsreader or syndicated to another site. Please visit the <a href="http://help.blogger.com/bin/answer.py?answer=697">Blogger Help</a> for more info.</div>
                </info>
                ''')
        
        if self.author:
            feed.append('''<author>%s</author>''' % self.author.output())
        for person in self.contributors:
            feed.append('''<contributor>%s</contributor>''' % person.output())
        if self.tagline:
            feed.append('''<tagline mode="escaped" type="text/html">%s</tagline>''' % self.tagline)
        if self.id:
            feed.append('''<id>%s</id>''' % self.id)
        if self.generator:
            feed.append('''<generator>%s</generator>''' % self.generator)
        if self.copyright:
            feed.append('''<copyright>%s</copyright>''' % self.copyright)
        for entry in self.entries:
            feed.append(entry.output())
        feed.append('''</feed>\n''')
        return '\n'.join(feed)

class Entry(object):
    """Represents an Atom entry (atom:entry)."""
    
    def __init__(self, base_url):
        self.base_url = base_url    # required
        self.title = None           # required
        self.url = None             # required
        self.author = None          # optional; required unless atom:feed has author
        self.contributors = []      # optional
        self.id = None              # optional
        self.modified = None        # required
        self.issued = None          # required
        self.created = None         # optional
        self.summary = None         # optional
        self.content = None         # optional
        self.comments = None        # optional
        self.feed = None            # optional
        self.feed_title = ''        # optional
        
    def set_modified(self, dt):
        """Takes a UTC DateTime."""
        self.modified = dt_to_iso(dt)

    def set_issued(self, dt):
        """Takes a UTC DateTime."""
        self.issued = dt_to_iso(dt)

    def set_created(self, dt):
        """Takes a UTC DateTime."""
        self.created = dt_to_iso(dt)

    def output(self):
        """Return entry as XML string."""
        entry = []
        entry.append('''<entry>
            <title mode="escaped" type="text/html">%(title)s</title>
            <link rel="alternate" type="text/html" href="%(url)s" />
            <issued>%(issued)s</issued>
            <modified>%(modified)s</modified>
            ''' % self.__dict__)
        
        if self.feed:
            entry.append('''<link rel="service.feed" type="application/atom+xml" href="%s" title="%s" />''' % (self.feed, self.feed_title))
        if self.comments:
            entry.append('''<link rel="comments" type="application/atom+xml" href="%s" />''' % self.comments)
        if self.author:
            entry.append('''<author>%s</author>''' % self.author.output())
        for person in self.contributors:
            entry.append('''<contributor>%s</contributor>''' % person.output())
        if self.id:
            entry.append('''<id>%s</id>''' % self.id)
        if self.created:
            entry.append('''<created>%s</created>''' % self.created)
        if self.summary:
            entry.append('''<summary type="application/xhtml+xml" xml:base="%s" xml:space="preserve">
                <div xmlns="http://www.w3.org/1999/xhtml">%s</div></summary>''' % (self.base_url, self.summary))
        if self.content:
            #entry.append('''<content type="application/xhtml+xml" xml:base="%s" xml:space="preserve">
            #    <div xmlns="http://www.w3.org/1999/xhtml">%s</div></content>''' % (self.base_url, self.content))
            entry.append('''<content type="text/html" mode="escaped" xml:base="%s" xml:space="preserve">%s</content>''' % (self.base_url, self.content))
        
        entry.append('''</entry>''')
        return '\n'.join(entry)
        
    
class Person(object):
    """Represents an Atom Person."""
    
    def __init__(self, name=None):
        self.name = name        # required
        self.url = None         # optional
        self.email = None       # optional

    def output(self):
        person = []
        person.append('''<name>%s</name>''' % self.name)
        if self.url:
            person.append('''<url>%s</url>''' % self.url)
        if self.email:
            person.append('''<email>%s</email>''' % self.email)
        
        return '\n'.join(person)



def _test():
    import doctest, atom
    return doctest.testmod(atom)
    
if __name__ == "__main__":
    _test()
