#!/www/python/bin/python
"""
$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/dulcinea/bin/unused_imports.py $
$Id: $

Reports imports of names that are not in code in the importing file.

Even though a name is not used in code in the importing file, the
import may still be necessary.  For example, names are sometimes
imported in module A for the purpose of being imported from A in other
modules, or for side effects.  Sancho scripts often use imported names
in test code that is stored in strings, and this script doesn't detect
that usage.  Quixote applications often import names that only appear
in _q_export lists, and this script will report them as unused
imports.  The bottom line is that you may use this script to locate
suspicious imports, but you still need to be careful about actually
deleting imports.
"""

from dulcinea.code_util import report_unused_imports, main

main(report_unused_imports)
