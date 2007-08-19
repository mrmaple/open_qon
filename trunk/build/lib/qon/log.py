"""
$Id: log.py,v 1.6 2005/08/31 06:50:15 alex Exp $

Admin log usage:

import qon.log

logger = qon.log.get_admin_log()

logger.debug(qon.log.msg('debug message'))
    or
qon.log.admin_debug('debug message)

logger.info('info message')
    or
qon.log.admin_info('info message')

etc...

"""
import os, logging
from datetime import datetime
from quixote import get_request
from qon.base import get_user, QonPersistent


def get_admin_log():
    return logging.getLogger('admin')

def admin_info(s):
    return get_admin_log().info(msg(s))
    
def admin_debug(s):
    return get_admin_log().debug(msg(s))
    
def admin_warning(s):
    return get_admin_log().warning(msg(s))
    
def admin_error(s):
    return get_admin_log().error(msg(s))
    
def get_edit_log():
    return logging.getLogger('edit')

def edit_info(s):
    return get_edit_log().info(msg(s))
    
def get_stats_log():
    return logging.getLogger('stats')

def stats_info(s):
    return get_stats_log().info(msg(s))

def get_timing_log():
    return logging.getLogger('timing')

def timing_info(s):
    return get_timing_log().info(msg(s))
    
    
def msg(s):
    """Format a log message to include user information."""
    user_id = 0
    ip = 'NO-IP'
    try:
        user = get_user() or None
        if user:
            user_id = user.get_user_id()
        
        ip = get_request().environ.get('REMOTE_ADDR')
        
    except AttributeError:
        # no publisher
        pass
    
    return '%s\t%s\t%s' % (user_id, ip, s)


class LogDB(QonPersistent):
    def __init__(self):
        self.items = []
        
    def log(self, action, args, undo=None):
        """Log an action. Caller should call commit()."""
        
        try:
            user = get_user() or None
    
            if user:
                user_id = user.get_user_id()
            else:
                user_id = 0
            ip = get_request().environ.get('REMOTE_ADDR')
        except AttributeError:
            # no publisher
            user_id = 0
            ip = ''
            
        time = datetime.utcnow()
        
        logitem = [ip, user_id, time, action, args, undo]
        self.items.append(logitem)
        self._p_changed = 1

def _log_name(s):
    """Return path to log file for filename s."""
    from dulcinea import site_util
    config = site_util.get_config()
    site = os.environ.get('SITE', 'qon')
    return os.path.join(config.defaults().get('log-directory'),
        site,
        s)

def _admin_log_name():
    return _log_name('admin.log')

def _edit_log_name():
    return _log_name('edit.log')

def _stats_log_name():
    return _log_name('stats.log')

def _timing_log_name():
    return _log_name('timing.log')

# create admin log - access via get_admin_log()
_logger = logging.getLogger('admin')
_hdlr = logging.FileHandler(_admin_log_name())
_hdlr.setFormatter(logging.Formatter('%(asctime)s\t%(levelname)s\t%(message)s'))
_logger.addHandler(_hdlr)
_logger.setLevel(logging.INFO)

# create edit log - access via get_edit_log()
_logger = logging.getLogger('edit')
_hdlr = logging.FileHandler(_edit_log_name())
_hdlr.setFormatter(logging.Formatter('%(asctime)s\t%(levelname)s\t%(message)s'))
_logger.addHandler(_hdlr)
_logger.setLevel(logging.INFO)

# create stats log - access via get_stats_log()
_logger = logging.getLogger('stats')
_hdlr = logging.FileHandler(_stats_log_name())
_hdlr.setFormatter(logging.Formatter('%(asctime)s\t%(levelname)s\t%(message)s'))
_logger.addHandler(_hdlr)
_logger.setLevel(logging.INFO)

# create timing log - access via get_timing_log()
_logger = logging.getLogger('timing')
_hdlr = logging.FileHandler(_timing_log_name())
_hdlr.setFormatter(logging.Formatter('%(asctime)s\t%(levelname)s\t%(message)s'))
_logger.addHandler(_hdlr)
_logger.setLevel(logging.INFO)

