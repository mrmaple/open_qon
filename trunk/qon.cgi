#!/opt/local/bin/python

# Example driver script for the Quixote demo: publishes the contents of
# the quixote.demo package.

import sys, os
sys.path.insert(1, './lib')	# XXX Is there a better way to do this?
os.environ['SITE'] = 'qon'

from dulcinea import local
from dulcinea.persistent_session import DulcineaSession, DulcineaSessionManager
from dulcinea.ui.publisher import DulcineaPublisher
from quixote import enable_ptl, Publisher
from quixote.publish import SessionPublisher


local.open_database('file:/www/var/qon.fs')

# Install the import hook that enables PTL modules.
enable_ptl()

# Create a Publisher instance 
#app = QONPublisher('qon.demo.session', session_mgr=local.get_session_manager())
app = SessionPublisher('qon.ui.qslash', session_mgr=local.get_session_manager())

# (Optional step) Read a configuration file
app.read_config("qon.conf")

# Open the configured log files
app.setup_logs()

# Enter the publishing main loop
app.publish_cgi()

