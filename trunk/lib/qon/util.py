"""
$Id: util.py,v 1.57 2007/05/01 11:41:29 jimc Exp $

"""
import zlib, string
from datetime import datetime
from ZODB.POSException import POSKeyError
from dulcinea.database import format_oid
import quixote.html
from qon.base import QonPersistent, get_connection, get_user, get_group_database
import re
from math import sqrt, cos, acos, sin
from qon import local

from qon.ui import messages
_ = messages.t

def dt_to_iso(dt):
    """Convert UTC datetime dt to ISO 8601 format."""
    return '%sZ' % dt.replace(microsecond=0).isoformat()
    
def iso_to_dt(iso):
    """Convert ISO 8601 format to datetime. Returns None if invalid format."""
    from time import strptime
    
    try:
        (Y, M, D, h, m, s, wd, yd, dst) = strptime(iso, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        return None

    return datetime(Y, M, D, h, m, s)

def iso_8859_to_utf_8(s):
    """Attempt to convert an iso-8859-1 string to utf-8."""
    if (not s) or (type(s) is not str):
        return s
    
    # microsoft sucks: although we have always asked for iso-8859-1
    # form submissions, browsers accept curly quotes and other binary
    # characters from microsoft software. Therefore, we don't know
    # for sure if our text is pure iso-8859-1 or windows-1252, which is
    # microsoft's non-standard extension. 
    # the good news is that windows-1252 is a superset of iso-8859-1, so
    # why am I complaining? (cp1252 is a synonmym of windows-1252.)
    
    new_s = s.decode('windows-1252', 'replace').encode('utf-8')
    return new_s

def get_page_template(name, format):
    """Attempt to fetch contents of page 'name' from template group.
    format must be 'text' or 'html'. Returns None if page does not
    exist or is empty.

    If 'html' format is requested, returns htmltext object.

    By convention, template page names start with '_live_tmpl_' and this
    function will prepend this prefix automatically.
    """
    _template_prefix = '_live_tmpl_'

    if not name.startswith(_template_prefix):
        name = _template_prefix + name
    
    try:
        page = get_group_database()['sitedev'].wiki.pages[name]
    except KeyError:
        return None

    # check for empty raw text in case page has been cleared;
    # cached html will never be fully empty
    raw = page.versions[-1].get_raw()
    if not raw:
        return None
    
    if format == 'html':
        return quixote.html.htmltext(page.get_cached_html())
    else:
        return raw

class CompressedText(QonPersistent):
    """Minimal class to hold text so objects doesn't have to read
    complete text off the disk unless it's really needed.
    """

    persistenceVersion = 1

    def __init__(self, raw=''):
        self.__raw = None
        self.set_raw(raw)

    def upgradeToVersion1(self):
        try:
            raw = self.get_raw()
        except AttributeError:
            if hasattr(self, '_WikiRawText__raw'):
                self.__raw = self._WikiRawText__raw
                del self._WikiRawText__raw
            raw = self.get_raw()

        self.set_raw(iso_8859_to_utf_8(raw))
        
    def get_raw(self):
        if self.__raw is None:
            return ''
        
        try:
            return zlib.decompress(self.__raw)
        except zlib.error:
            return self.__raw
    
    def set_raw(self, raw):
        if raw:
            self.__raw = zlib.compress(raw)
        else:
            self.__raw = None

def xml_escape(s, escape_quote=False):
    """Return string with &, <, >, and " escaped."""
    from xml.sax.saxutils import escape
    d = {}
    if escape_quote:
        d = {'"': ''}
    return escape(s, d)

def html_unescape (s):
    s = s.replace("&lt;", "<")
    s = s.replace("&gt;", ">")
    s = s.replace("&quot;", '"')
    s = s.replace("&amp;", "&")
    return s

def sort_list(l, func, count=0, reverse=True):
    """Given l with items i, return new list reverse-sorted by func(i) for
    each item."""
    byf = [(func(i), i) for i in l]
    byf.sort()
    if count:
        byf = byf[-count:]
    if reverse:
        byf.reverse()
    return [i for f, i in byf]

def pad_list(l, count, pad):
    """Pad list l IN PLACE to count length, adding as many `pad's as necessary.
    
    >>> a=[1,2,3]
    >>> pad_list(a, 10, None)
    >>> a
    [1, 2, 3, None, None, None, None, None, None, None]
    """
    if len(l) < count:
        l.extend([pad,] * (count-len(l)))
    return None
    
def pad_lists(lists, max_count, pad):
    """Pad lists IN PLACE to size of largest list, not exceeding max_count, with pad."""
    
    maxl = 0
    for l in lists:
        length = len(l)
        if length > maxl:
            maxl = length
    
    maxl = min(max_count, maxl)
    
    for l in lists:
        pad_list(l, maxl, pad)

def zip_lists(*lists):
    """Zip any # of lists together.  Each list should have an equal
    # of elements."""
    cells = []
    size_of_each_list = len(lists[0])
    for x in range(size_of_each_list):
        for l in lists:
            cells.append(l[x])
    return cells

def unique_items(list):
    """Return list with unique items only, preserving order."""
    seen = {}
    newlist = []
    for i in list:
        if not seen.has_key(i):
            seen[i] = 1
            newlist.append(i)
    return newlist
    
def remove_left_duplicates(list):
    """Mutate list IN PLACE to remove leftmost duplicate entries.
    
    Returns None to remind you that list is mutated in place.

    >>> l=[1,1,2,3,2,4] 
    >>> remove_left_duplicates(l)
    >>> l
    [1, 3, 2, 4]
    """
    seen = {}
    to_remove = []
    for i in list:
        if seen.has_key(i):
            to_remove.append(i)
        else:
            seen[i] = 1
    
    for i in to_remove:
        list.remove(i)  # removes first occurence

    return None

def del_keys_with_val(map, val):
    keys_to_del = []
    for k, v in map.iteritems():
        if v == val:
            keys_to_del.append(k)
    for k in keys_to_del:
        del map[k]

def xor_lists(a, b):
    """Return two lists: items in a but not in b, and items in b but not in a.
    
    >>> xor_lists([1, 2, 3, 4, 10, 20], [2, 3, 4, 5, 6])
    ([1, 10, 20], [5, 6])
    >>> xor_lists([], [1, 2])
    ([], [1, 2])
    """
    a_map = {}
    b_map = {}
    
    for i in a:
        a_map[i] = 1
    for i in b:
        b_map[i] = 1

    a_not_b = []
    b_not_a = []
    for k in a_map.keys():
        if not b_map.has_key(k):
            a_not_b.append(k)
    for k in b_map.keys():
        if not a_map.has_key(k):
            b_not_a.append(k)
    return (a_not_b, b_not_a)

def url_quote_no_slashes(s):
    """Return string suitable for URL, with slashes replaced by underscores."""
    if s is None:
        return ''
    return quixote.html.url_quote(s.replace('/', '_'))

def coerce_to_list(x):
    if type(x) is not list:
        x = [x]
    return x

def get_oid(oid):
    """Return an item from the database with OID == oid."""
    try:
        return get_connection()[oid]
    except POSKeyError:
        raise KeyError("OID not found: %s" % format_oid(oid))

# Packed User IDs

_pack_uid_version = 0       # format version
_pack_uid_struct = '=BL'    # uchar: version, ulong: uid
_unpack_uid_version = 0     # unpacked version: 'u123456789'

def pack_user_id(uid):
    """Return a binary packed user id which is more space efficient than a string.
    
    >>> unpack_user_id(pack_user_id('u999999999'))
    'u999999999'
    >>> unpack_user_id(pack_user_id('u000000000'))
    'u000000000'
    >>> unpack_user_id(pack_user_id('u000000123'))
    'u000000123'
    """    
    from struct import pack
    try:
        return pack(_pack_uid_struct, _pack_uid_version, int(uid[1:]))
    except ValueError:
        # we barf on user ids like 'jimc'
        return uid

def unpack_user_id(data):
    """Unpack a binary user id.
    """    
    
    from struct import unpack
    try:
        (version, uid) = unpack(_pack_uid_struct, data)
    except:
        # we barf on user ids like 'jimc'
        return data
    else:
        assert version == _pack_uid_version
    
    return 'u%09d' % uid


def pack_ip(ip):
    """Return 4-byte packed ip from quad-dot notation.
    
    >>> pack_ip('127.0.0.1')
    '\\x7f\\x00\\x00\\x01'
    """
    from struct import pack
    (b1, b2, b3, b4) = ip.split('.')
    return pack('=BBBB', int(b1), int(b2), int(b3), int(b4))

def unpack_ip(packed_ip):
    """Return IP address in quad-dot string from packed form.
    >>> unpack_ip('\\x7f\\x00\\x00\\x01')
    '127.0.0.1'
    """
    from struct import unpack
    return '.'.join([str(x) for x in unpack('=BBBB', packed_ip)])

def shroud_email(e):
    email = 'someone (at) ' + e[e.find('@')+1:]
    return email

def format_age(td):
    # takes a timedelta
    if td.days:
        # jc: added years and weeks
        if td.days > 365:
            years = td.days // 365
            if years > 1:
                return _("%i years ago") % years
            else:
                return ("last year")
        if td.days > 7:
            weeks = td.days // 7
            if weeks > 1:
                return _("%s weeks ago") % weeks
            else:
                return('last week')
        # jc: end of modifications
        if td.days > 1:
            return _('%s days ago') % td.days
        else:
            return _('yesterday')
    else:
        hours = td.seconds / 3600
        if hours:
            if hours > 1:
                return _('%s hours ago') % hours
            else:
                return _('1 hour ago')
        minutes = td.seconds / 60
        if minutes:
            if minutes > 1:
                return _('%s minutes ago') % minutes
            else:
                return _('1 minute ago')

    return _('%s seconds ago') % td.seconds

def format_ago(dt, now=None):
    # takes a datetime, subtracts from utcnow and calls format_age
    if dt is None:
        return 'never'
    if now is None:
        now = datetime.utcnow()
    return format_age(now - dt)

def format_time_remaining(dt, now=None, detail=False):
    """ Takes a datetime and displays time remaining.
    
    >>> from datetime import datetime
    >>> now=datetime(2005, 1, 1, 0, 0, 0)
    >>> dt = datetime(2005, 1, 1, 0, 0, 1)
    >>> format_time_remaining(dt, now=now, detail=False)
    '1 second'
    >>> format_time_remaining(dt, now=now, detail=True)
    '1 second'

    >>> dt = datetime(2005, 1, 1, 0, 0, 10)
    >>> format_time_remaining(dt, now=now, detail=False)
    '10 seconds'
    >>> format_time_remaining(dt, now=now, detail=True)
    '10 seconds'

    >>> dt = datetime(2005, 1, 1, 1, 0, 0)
    >>> format_time_remaining(dt, now=now, detail=False) # special case
    '1 hour'
    >>> format_time_remaining(dt, now=now, detail=True)
    '1 hour'

    >>> dt = datetime(2005, 1, 1, 1, 50, 0)
    >>> format_time_remaining(dt, now=now, detail=False) # special case
    '1 hour, 50 minutes'
    >>> format_time_remaining(dt, now=now, detail=True)
    '1 hour, 50 minutes'

    >>> dt = datetime(2005, 1, 1, 1, 1, 0)
    >>> format_time_remaining(dt, now=now, detail=True)
    '1 hour, 1 minute'

    >>> dt = datetime(2005, 1, 1, 3, 30, 0)
    >>> format_time_remaining(dt, now=now, detail=False)
    '3 hours'

    >>> dt = datetime(2005, 1, 2, 0, 0, 0)
    >>> format_time_remaining(dt, now=now, detail=False)
    '24 hours'
    >>> format_time_remaining(dt, now=now, detail=True)
    '1 day, 0 hours'

    >>> dt = datetime(2005, 1, 2, 1, 0, 0)
    >>> format_time_remaining(dt, now=now, detail=False)
    '25 hours'
    >>> format_time_remaining(dt, now=now, detail=True)
    '1 day, 1 hour'

    >>> dt = datetime(2005, 1, 4, 0, 0, 0)
    >>> format_time_remaining(dt, now=now, detail=False)
    '3 days'
    >>> format_time_remaining(dt, now=now, detail=True)
    '3 days, 0 hours'

    >>> dt = datetime(2005, 1, 4, 1, 0, 0)
    >>> format_time_remaining(dt, now=now, detail=False)
    '3 days'
    >>> format_time_remaining(dt, now=now, detail=True)
    '3 days, 1 hour'
    """
    
    def get_plural(num):
        if num == 1:    return ''
        else:           return 's'
    
    if dt is None:
        return 'never'
    if now is None:
        now = datetime.utcnow()
    
    td = dt - now
    
    # get hours remainder
    hours = td.seconds / 3600

    if td.days:
        if td.days > 1:
            if detail:
                plural = get_plural(hours)
                return _('%d days, %d hour%s') % (td.days, hours, plural)
            else:
                return _('%d days') % td.days
    
    # special case for 1 day
    if detail:
        if td.days == 1:
            plural = get_plural(hours)
            return _('%d day, %d hour%s') % (td.days, hours, plural)
    
    # add non-zero days to hour count
    hours += (td.days * 24)
    
    if hours > 1:
        if detail:
            minutes = (td.seconds - (hours * 3600)) / 60
            plural = get_plural(minutes)
            return _('%d hours, %d minute%s') % (hours, minutes, plural)
        else:
            return _('%d hours') % hours
    
    # special case for 1 hour: display detail version
    if hours == 1:
        minutes = (td.seconds - (hours * 3600)) / 60
        plural = get_plural(minutes)
        if minutes:
            return _('%d hour, %d minute%s') % (hours, minutes, plural)
        else:
            return _('%d hour') % (hours)
    
    minutes = td.seconds / 60

    if minutes > 1:
        if detail:
            seconds = td.seconds - (minutes * 60)
            plural = get_plural(seconds)
            return _('%d minutes, %d second%s') % (minutes, seconds, plural)
        else:
            return _('%d minutes') % minutes
    
    # special case for 1 minute
    if detail:
        if minutes == 1:
            seconds = td.seconds - (minutes * 60)
            plural = get_plural(seconds)
            return _('%d minutes, %d second%s') % (minutes, seconds, plural)
    
    plural = get_plural(td.seconds)
    return _('%d second%s') % (td.seconds, plural)
    
def is_camel_case(name):
    """Return True if name is in CamelCase.

    >>> is_camel_case('CamelCase')
    True
    >>> is_camel_case('AWordCamel')
    False
    >>> is_camel_case('XYZ')
    False
    >>> is_camel_case('VeryLongSentenceWithManyWords')
    True
    """

    if not name or len(name) < 4:
        return False

    # must be a single word, no spaces
    if name != name.split()[0]:
        return False

    # must start with cap
    if name[0] not in string.uppercase:
        return False

    # must be followed by non-cap
    if name[1] not in string.lowercase:
        return False

    # must have at least one more cap-non-cap pattern
    index = 2
    max_index = len(name) - 1
    for x in name[index:]:
        if x in string.uppercase:
            if index == max_index:
                return False
            if name[index+1] in string.lowercase:
                return True
        index += 1

    return False

def un_camel_case(title):
    """Return a spaced out version of CamelCase words.
    
    >>> un_camel_case('foo')
    'foo'
    >>> un_camel_case('CamelCase')
    'Camel Case'
    >>> un_camel_case('LongishCoupleOfWords')
    'Longish Couple Of Words'
    >>> un_camel_case('ThisIsAVeryLongPageName')
    'This Is A Very Long Page Name'
    >>> un_camel_case('This is a regular title.')
    'This is a regular title.'
    >>> un_camel_case('EndingW')
    'EndingW'
    """

    if not is_camel_case(title):
        return title

    # rebuild string with spaces
    index = 0
    new_title = ''

    for c in title:
        if c in string.uppercase:
            if index:
                new_title += ' '
        new_title += c
        index += 1

    return new_title
        


from quixote.sendmail import sendmail as qx_sendmail
from quixote.sendmail import RFC822Mailbox
from dulcinea import local

def sendmail (subject, msg_body, to_addrs,
              from_addr=None, reply_to=None, smtp_sender=None,
              cc_addrs=None, extra_headers=None,
              smtp_recipients=None, force=False):
    """
    Wrapper for Quixote's sendmail() function.  Differences:
      * respects the local.SUPPRESS_EMAIL config setting
        except when the force keyword argument is true
      * optionally adds "Reply-To" header
      * if smtp_sender not supplied, defaults to MAIL_SMTP_SENDER
        defined in local module rather than the addr-spec
        in from_addr

    See quixote.sendmail module for details (including argument types).
    This version removes code always adding Precedence: Junk headers in
    original duclinea.sendmail code.
    """
    if not force and local.SUPPRESS_EMAIL:
        print '-' * 40
        print 'To: %s' % to_addrs
        print 'Subject: %s\n' % subject
        print msg_body
        print '-' * 40
        return

    # Control over the actual (SMTP) recipient of this message is now in
     # the hands of Quixote's sendmail(), guided by the mail_debug_addr
    # setting in the publisher's config.

    if extra_headers is None:
        #extra_headers = ['Content-Type: text/html']
        extra_headers = []

    if reply_to is not None:
        reply_to = [RFC822Mailbox(args).format() for args in reply_to]
        extra_headers.append("Reply-To: %s" % ", ".join(reply_to))

    if smtp_sender is None:
        smtp_sender=local.MAIL_SMTP_SENDER

    # pmo: we just want the from address to be specified in this local.MAIL_SMTP_SENDER variable
    if from_addr is None:
        from_addr=smtp_sender

    qx_sendmail(subject, msg_body, to_addrs,
                from_addr=from_addr, extra_headers=extra_headers,
                cc_addrs=cc_addrs, smtp_sender=smtp_sender,
                smtp_recipients=smtp_recipients)


def get_canonical_name(server_name):
    """Given hostname server_name, return canonical name, usually something like www.ned.com.
    Returns None if server_name should be unchanged.
    
    >>> get_canonical_name('localhost')
    
    >>> get_canonical_name('joes-computer.local')

    >>> get_canonical_name('ned.com')
    'www.ned.com'
    >>> get_canonical_name('delta.ned.com')
    'www.ned.com'
    >>> get_canonical_name('www.ned.com')

    """
    
    # don't munge access via localhost
    if server_name in ['localhost']:
        return None
    
    # don't munge '.local' names
    if server_name.endswith('.local'):
        return None
    
    if not server_name.startswith('www.'):
    
        # chop off any subdomains if we can. E.g., delta.ned.com becomes
        # ned.com. If for some reason we get here with something like
        # localhost or fooble, we'll just pass it through, and it will end
        # up redirecting to www.fooble
        parts = server_name.split('.')
        if len(parts) >= 2:
            server_name = '.'.join([parts[-2], parts[-1]])
        
        return 'www.' + server_name
    
    return None

def check_ip_monitor(user, ipaddress):
    """ Called from ui whenever a user signs in.  Notifies us if a user
    signs in under an IP address she has never signed in under before,
    and that IP address is in the monitored list.
    The list of monitored IPs and the emails of folks to be notified
    are kept in a workspace page in sitedev called admin_ip_monitor. """

    # first check if the user is signing in under a new ip address.
    #  if not, don't bother continuing
    ips = user.get_ip_addresses().iteritems()
    for k,v in ips:
        if ipaddress == k:
            return
    
    # now get the special page
    try:
        fullpage = get_group_database()['sitedev'].get_wiki().pages['admin_ip_monitor'].versions[-1].get_raw()
    except:
        return

    # and parse it for ips and emails
    ips_text, emails_text = fullpage.split("Notify:")
    ips = re.compile('(\d+\.\d+\.\d+\.\d+)').findall(ips_text)
    emails = re.compile('([a-zA-Z0-9_\-]+@[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+)').findall(emails_text)

    # if the ipaddress is being monitored, then send out an alert email
    import smtplib
    if (len(emails)>0) and (ipaddress in ips):
        message = '%s (%s) signed in from %s' % (user.get_user_id(), user.display_name(), ipaddress)
        sendmail("IP Monitor Alert", message, emails)

def tail_lines(filename, linesback = 10, avgcharsperline = 75):
    """
    Contributed to Python Cookbook by Ed Pascoe (2003)
    Adapted by Alex Poon (2005)
    """
    try:
        fd = open(filename, 'r')
    except IOError, err:
        return []
    
    while 1:
        try:
            fd.seek(-1 * avgcharsperline * linesback, 2)
        except IOError:
            fd.seek(0)

        if fd.tell() == 0:
            atstart = 1
        else:
            atstart = 0

        lines = fd.read().split("\n")
        if (len(lines) > (linesback+1)) or atstart:
            break

        avgcharsperline=avgcharsperline * 1.3

    if len(lines) > linesback:
        start = len(lines) - linesback - 1
    else:
        start = 0

    return lines[start:len(lines)-1]

def standardize_url(url):
    if url and 'http' not in url:
        url = 'http://' + url
    return url

def standardize_lon_lat_coord(coord):
    """ converts something like N 37° 19' 14'' or N 37 19.2 or +37.2306
    to 37.2306 """
    deg = 0.0
    min = 0.0
    sec = 0.0
    decimal_result = 0.0

    if not coord or len(coord)==0:
        return None

    numbers = re.compile('([\d\.]+)').findall(coord)
    if len(numbers) == 0:
        return None
    if len(numbers) >= 1:
        deg = float(numbers[0])
    if len(numbers) >= 2:
        min = float(numbers[1])
    if len(numbers) >= 3:
        sec = float(numbers[2])
        
    decimal_result = deg + min/60.0 + sec/3600.0
        
    # figure out if we should go negative
    coord = coord.lower()
    if 'n' in coord or 'e' in coord or '+' in coord:
        return decimal_result    
    if 'w' in coord or 's' in coord or '-' in coord:
        return -decimal_result

    return decimal_result     

def _diff_180(d):
    d = abs(d)
    if (d >=180):
        return 360-d
    return d    

def distance_lat_long_fastest(lat1, lon1, lat2, lon2):
    """
    returns distance in miles between two points.
    points are lat/longs in decimal degrees.
    fastest, but up to 10% off.
    """
    x = 69.1 * _diff_180(lat2 - lat1)
    y = 53.0 * _diff_180(lon2 - lon1)
    return sqrt(x*x + y*y)

def distance_lat_long_fast(lat1, lon1, lat2, lon2):
    """
    returns distance in miles between two points.
    points are lat/longs in decimal degrees,
    with + meaning N and W, and - meaning S and E
    very fast and more accurate than the fastest version.
    """
    x = 69.1 * _diff_180(lat2 - lat1)
    y = 69.1 * _diff_180(lon2 - lon1) * cos(lat1/57.3)
    return sqrt(x*x + y*y)

def distance_lat_long_slow(lat1, lon1, lat2, lon2):
    """
    returns distance in miles between two points.
    points are lat/longs in decimal degrees.
    accurate, but about twice as slow as the other methods.
    """
    return 3963.0 * acos(sin(lat1/57.2958) * sin(lat2/57.2958) + cos(lat1/57.2958) * cos(lat2/57.2958) *  cos(lon2/57.2958 -lon1/57.2958))
    
def _test():
    import doctest, util
    return doctest.testmod(util)
    
if __name__ == "__main__":
    _test()
