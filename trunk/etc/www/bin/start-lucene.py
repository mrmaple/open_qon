#!/www/python/bin/python

"""
start-lucene.py

Script invoked by site to start the lucene server
"""

import os
from dulcinea import site_util

site_util.ensure_uid_gid_not_root()

config = site_util.get_config()

for site in site_util.list_sites():
    if not config.has_option(site, 'lucene-address'):
        continue
    
    # get server ip and port
    ip, port = site_util.parse_address(config.get(site, 'lucene-address'))
    
    # db
    db = os.path.join(config.get(site, 'var-directory'),
        '%s_lucene' % site)
    
    # log
    log = os.path.join(config.get(site, 'log-directory'), site, 'lucene')
    
    # build java invokation arguments
    java = config.get(site, 'java')
    args = '-classpath %(classpath)s Server %(port)s %(db)s %(log)s' % \
        dict(classpath=config.get(site, 'lucene-classpath'),
            port=port,
            db=db,
            log=log,
        )
    
    pid = os.spawnv(os.P_NOWAIT, java, [
        java,
        '-classpath',
        config.get(site, 'lucene-classpath'),
        'Server',
        str(port),
        db,
        log,
        ])
    
    pid_file = site_util.get_pid_file_name('lucene', site)
    f = open(pid_file, 'w')
    f.write(str(pid))
    f.close()
