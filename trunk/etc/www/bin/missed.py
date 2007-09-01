#!/www/python/bin/python
"""
$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/dulcinea/bin/missed.py $
$Id: $

This script runs the python module named on the command line
with __name__ == '__main__' and reports lines not executed.
Works without change for ptl.

Put '#n' in lines that you don't want missed.py to report as
missed.
"""
from dulcinea.code_util import report_missed_lines, main

main(report_missed_lines)
