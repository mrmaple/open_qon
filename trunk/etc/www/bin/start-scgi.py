#!/www/python/bin/python
'''$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/dulcinea/bin/start-scgi.py $
$Id: start-scgi.py,v 1.11 2007/05/15 16:27:09 jimc Exp $

Script invoked by site command to start scgi.
'''

import os, sys
import ZODB, ZEO
import pwd
import socket
from scgi.quixote_handler import QuixoteHandler, scgi_server, debug
from dulcinea import local
from dulcinea import site_util
from dulcinea.ui.publisher import DulcineaPublisher

from qon import local

site = os.environ['SITE'] = sys.argv[1]

site_util.ensure_uid_gid_not_root()
config = site_util.get_config()
pid_file_name = site_util.get_pid_file_name('scgi', site)
ip, port = site_util.parse_address(config.get(site, 'scgi-address'))
site_log_dir = os.path.join(config.get(site, 'log-directory'), site)
error_log = os.path.join(site_log_dir, 'error.log')
assert site_util.is_local(config.get(site, 'scgi-address'))

def get_publisher():
    """Get publisher from config file. -- pmo"""
    s_pub = config.get(site, 'publisher')
    modulename = s_pub[:s_pub.rfind('.')]
    klassname = s_pub[s_pub.rfind('.')+1:]
    __import__(modulename)
    module = sys.modules[modulename]
    klass = getattr(module, klassname)
    return klass()

def create_site_publisher(site):
    local.open_database()
    
    # pmo fix this to get publisher from config file
    # publisher = DulcineaPublisher()
    
    publisher = get_publisher()
    
    # set config options
    publisher.config.form_tokens = 1
    publisher.config.display_exceptions = 0
    publisher.config.secure_errors = 1
    publisher.config.session_cookie_path = '/'
#    if local.BACKUPDELTA:
#        publisher.config.session_cookie_name= 'qx_backupdelta_session'
    site_log_dir = os.path.join(config.get(site, 'log-directory'), site)
    publisher.config.access_log = os.path.join(site_log_dir, 'access.log')
    publisher.config.error_log = error_log
    publisher.config.compress_pages = 1
    administrator = site_util.get_administrator_address()
    if site_util.is_live(site):
        publisher.config.error_email = administrator[0]
        publisher.config.mail_from = administrator
    elif site_util.is_staging(site):
        publisher.config.error_email = administrator[0]
        publisher.config.mail_from = administrator
        publisher.config.mail_debug_addr = administrator[0]
    else: # devel
        publisher.config.display_exceptions = 1
        publisher.config.secure_errors = 0
        publisher.config.fix_trailing_slash = 0
        user = pwd.getpwuid(os.geteuid())[0] # Owner of the SCGI process
        user_email = user + '@' + socket.getfqdn()
        publisher.config.mail_debug_addr = user_email
        publisher.config.mail_from = user_email
    # Adjust any values that are set in the site configuration.
    for config_var in publisher.config.config_vars:
        if config.has_option(site, config_var):
            setattr(publisher.config, config_var,
                    config.get(site, config_var))
    publisher.setup_logs()

    # We have to commit the current transaction here, just in case there wasn't
    # an existing session manager object in the ZODB.  In the case,
    # get_session_manager() created a new session manager and added it to the
    # ZODB root, but then start_request() will call sync(), losing the
    # modification to the ZODB root.  The net result is that, without the
    # following commit, the session manager is never written to disk and
    # sessions are always immediately thrown away.
    get_transaction().note('create_site_publisher')
    get_transaction().commit()

    return publisher


class Handler (QuixoteHandler):
    prefix = ""

    def __init__(self, *args, **kwargs):
        scgi_server.SCGIHandler.__init__(self, *args, **kwargs)
        self.publisher = create_site_publisher(site)
        debug("SCGI server for %s starting up (pid %d)" % (site, os.getpid()))


site_util.log_to(error_log)

if site_util.is_live(site) or site_util.is_staging(site):
    max_children = 4
else:
    max_children = 1 # faster for development

pid = os.fork()
if pid == 0:
    pid = os.getpid()
    pidfile = open(pid_file_name, 'w')
    pidfile.write(str(pid))
    pidfile.close()
    try:
        scgi_server.SCGIServer(Handler, port=port,
                               max_children=max_children).serve()
    finally:
        # grandchildren get here too, don't let them unlink the pid
        if pid == os.getpid():
            try:
                os.unlink(pid_file_name)
            except OSError:
                pass

