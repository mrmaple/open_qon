#!/www/python/bin/python

"""$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/dulcinea/bin/start-zeo.py $
$Id: $

Script invoked by the site command to start zeod.
"""

import sys, os

from dulcinea import site_util
site_util.ensure_uid_gid_not_root()
config = site_util.get_config()
site = sys.argv[1]
pid_file_name = site_util.get_pid_file_name ('zeo', site)
ip, port = site_util.parse_address(config.get(site, 'zeo-address'))
assert site_util.is_local(config.get(site, 'zeo-address'))
db = os.path.join(config.get(site, 'var-directory'), '%s.fs' % site)

site_log_dir = os.path.join(config.get(site, 'log-directory'), site)
zeo_log = os.path.join(site_log_dir, 'zeo.log')

# XXX pmo modified to use zeoctl instead
# XXX zeo_log from site.conf is ignored; see /www/etc/zeo.conf instead

zeod = config.defaults().get('zeod')
#os.execve(zeod, (zeod, '-p', str(port), '-P', pid_file_name, db),
#          {'STUPID_LOG_FILE': zeo_log, 'STUPID_LOG_SEVERITY': '100'}
#         )

os.execv(zeod, (zeod, 'start'))
