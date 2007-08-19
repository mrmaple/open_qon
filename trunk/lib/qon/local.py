from qon.base import open_database, get_session_manager, get_connection, \
     get_user_database, get_group_database
     
SITE = 'ned'
SITE_NAME = 'ned.com'
SUPPRESS_EMAIL = 0

# Used as the default SMTP sender for mail sent by the site (ie. by
# dulcinea.sendmail.sendmail()), so that any bounces will go to us.
MAIL_SMTP_SENDER = 'ned.com <folks@ned.com>'
MAIL_SERVER = 'smtp.gmavt.net'

# Set to prohibit file uploads
NO_FILE_UPLOAD = False

# WARNING: setting this to False defeats secure authentication:
# If False, everything will go through http
HTTPS_LOGIN = 0

LOCALHOST = False

#------------------------------------------------------
# Cache and performance logging stuff

# If set to True, database.py will use QonClientCache and QonFileCache
#  instead of the vanilla ClientCache and FileCache classes.
# This allows you to call print(db.storage._cache.fc.get_formatted_cache_stats())
#  in the opendb qon console for cache diagnostics.
# It also makes it so that the timing.log will report not only long calls, but also
#  the cache stats for those long calls.  Hint: if you use this while
#  setting LOG_TIMING_MIN_MS to 0, you can tail -f timing.log and monitor
#  the cache after every call in real-time.
# Note: regardless of this setting, database.py uses QonClientStorage instead
#  of ClientStorage to workaround ClientStorage's cache_size bug.
CACHE_INSTRUMENTATION = False

# Only applicable if CACHE_INSTRUMENTATION is True.
#  Setting this to True will have get_formatted_cache_stats() print out the
#  *actual* objects, rather than just an object tally.  You should normally
#  set this to False.
VERBOSE_CACHE_LOGGING = False

# Any requests that take longer than this in ms will be logged by publisher.py to timing.log.
#  Set to 0 to log ALL calls.
#  e.g. 10000 = 10 sec
LOG_TIMING_MIN_MS = 10000
