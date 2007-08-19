"""
$Id: messages.py,v 1.13 2006/03/22 02:45:41 alex Exp $

This file contains frequently used messages, as well as an importable
translator hook::

  from messages import t
  _ = t

Take care when using pre-defined messages from this file. For
example::

  import messages
  print _(messages.site_title)

"""
from quixote import get_publisher, get_request
from quixote.html import href
from qon import local

def t(text):
    """Return translated text.
    
    This is a standard hook to gettext, but with a twist: since our
    Quixote app runs in an app server, the typical global gettext
    approach doesn't work, because requests come in from different users
    and languages.
    
    We therefore have to check the HTTPRequest object to find the
    appropriate translator.
    """
    
    publisher = get_publisher()
    if not publisher:
        return text
    
    try:
        request = get_request()
    except AttributeError:
        # publisher has no request during import/load of this module
        return text
        
    if not request or not hasattr(request, 'gettext'):
        # gettext attr is installed by QonPublisher
        return text
        
    return request.gettext(text)

_ = t

base_url = '''http://www.ned.com/'''
home_url = '''http://www.ned.com/home/'''
if local.HTTPS_LOGIN:
    login_url = '''https://www.ned.com/home/'''
else:
    login_url = '''http://www.ned.com/home/'''

short_domain = '''ned.com'''
full_url_host = '''www.ned.com'''

site_title = _('ned.com')
preview_text = _('''<p class="alert">Preview your changes and make any necessary corrections below.
Then be sure to hit the Save button to record your changes.</p>''')

preview_text_send = _('''<p class="alert">Preview your changes and make any necessary corrections below.
Then be sure to hit the Send button to send your message.</p>''')

publisher = _('Maplesong')
copyright_notice = _('Copyright (c) 2007 Maplesong')


del _
