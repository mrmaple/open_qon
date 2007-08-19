#!/usr/bin/env python
"""$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/toboso/bin/create_db $
$Id: create_db,v 1.24 2005/04/12 04:45:46 pierre Exp $

Create an initial database.
"""

import os
os.environ['SITE'] = 'qon'
from qon.base import open_database, close_database
from qon.dbtools import init_database, add_real_data, essential_content
from qon.group_db import create_initial_groups
from qon.tags_db import initialize_tagging

if __name__ == "__main__":
    db = open_database("file:/www/var/qon.fs")
    init_database(db)
    add_real_data(db)
    create_initial_groups()
    initialize_tagging()
    essential_content(db)
    get_transaction().commit()
    db.close()
