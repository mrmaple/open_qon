"""$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/dulcinea/lib/script_util.py $
$Id: script_util.py,v 1.2 2004/04/17 00:41:41 jimc Exp $

Various utility functions and classes that are handy when writing good
ol'-fashioned command-line scripts.
"""

import sys, os, time, traceback, pdb

# We only import Option here so that scripts can import it from us,
# without having to import from optik directly.
import optparse
from optparse import Option

# Optik OptionValues instance; set by OptionParser.parse_args(),
# and consulted by various functions here (eg. for 'verbose'
# or 'commit' flags)
_optparse_options = None

class OptionParser (optparse.OptionParser):
    """OptionParse subclass that provides some standard command-line
    options:
      -v
      --verbose   
      -q, --quiet
      -n, --dry-run

    'verbose' defaults to 1, so scripts should be moderately chatty
    by default.  Use the 'log()' function to emit messages according
    to the user-specified verbosity level.

    Instance attributes: none
    """

    standard_option_list = optparse.OptionParser.standard_option_list + [
        Option('-v', action='count', dest='verbose', default=1,
               help="increment verbosity level"),
        Option('--verbose', action='store', type='int', dest='verbose',
               metavar="N", help="set verbosity level to N"),
        Option('-q', '--quiet', action='store_false', dest='verbose',
               help="turn off verbosity (no output except errors)"),
        Option('-n', '--dry-run', action='store_true',
               dest='dry_run', default=0,
               help="don't commit changes to the database"),
        ]


    def parse_args (self, args=None, values=None):
        global _optparse_options
        (_optparse_options, args) = optparse.OptionParser.parse_args(self, args,
                                                               values)
        return (_optparse_options, args)


# -- Output utility functions ------------------------------------------

def writenow (msg, file=None):
    if file is None:
        file = sys.stdout
    file.write(msg)
    file.flush()

def warn (msg):
    print >>sys.stderr, "warning: %s" % msg

def error (msg):
    print >>sys.stderr, "error: %s" % msg

def die (msg):
    sys.exit(msg)


# -- Miscellaneous utility functions -----------------------------------

def get_user_info ():
    """Return a "user@hostname" string.
    """
    import socket
    user_id = os.environ.get("USER") or os.environ.get("LOGNAME") or "?"
    host = socket.gethostname()
    return "%s@%s" % (user_id, host)


# -- High-level utility functions --------------------------------------
# (You *must* call 'parse_args()' on some OptionParser instance
# before using either: log() or commit()!)

def log (msg, threshold=1, options=None):
    global _optparse_options
    if options is None:
        options = _optparse_options
    if options.verbose >= threshold:
        writenow(msg)

def commit (options=None):
    global _optparse_options
    if options is None:
        options = _optparse_options
    if options.dry_run:
        log("skipping commit\n", threshold=2)
    else:
        log("committing...", options=options)
        get_transaction().commit()
        log("done\n", options=options)

def run ():
    """Run the 'main()' function from the '__main__' module, handling
    some common exceptions in a user-friendly way.
    """
    try:
        import __main__
        __main__.main()
    except (OSError, IOError), err:
        die("%s: %s" % (err.filename, err.strerror))

class Debugger(pdb.Pdb):
    """
    Calling the constructor of this class puts you in the
    interactive debugger.  This is like pdb.post_mortem, except
    that the traceback is printed and the exit command works.
    """
    def __init__ (self):
        pdb.Pdb.__init__(self)
        (exc_type, exc_value, tb) = sys.exc_info()
        up = 0
        if tb is None:
            try:
                raise 
            except:
                (exc_type, exc_value, tb) = sys.exc_info()
            down = 1 
        self.reset()
        while tb.tb_next is not None:
            tb = tb.tb_next
        self.interaction(tb.tb_frame, tb)

    def interaction (self, frame, traceback):
        self.setup(frame, traceback)
        self.curindex = self.curindex - 1
        self.curframe = self.stack[self.curindex][0]
        self.lineno = None
        self.do_explain()
        self.cmdloop()
        self.forget()

    def do_explain (self, arg=None):
        print "\n"
        for stack_entry in self.stack[self.curindex-3:-1]:
            self.print_stack_entry(stack_entry)
        print
        self.do_args(None)
        print
        self.do_list("%s,13" % (self.curframe.f_lineno - 12))

    def help_explain (self):
        print """
Print a slice of the stack, args to this function, and list the list the
section of code being executed.
"""

    def do_exit (self, arg):
        os._exit(1)

    def help_exit (self):
        print """Terminate this process."""

def verbose (arg, _depth=1):
    """Print arg, eval(arg), and then report the time it took."""
    frame = sys._getframe(_depth)
    start = time.time()
    print arg
    result = eval(arg, frame.f_globals, frame.f_locals)
    finish = time.time()
    print '%s completed in %1.3f seconds.' % (arg, finish-start)
    return result

def verbose_catch (arg):
    """
    Like verbose(), but drop into the debugger
    on exceptions.
    """
    try:
        verbose(arg, _depth=2)
    except SystemExit:
        raise
    except:
        print arg, 'FAILED'
        Debugger()

def verbose_main (fun):
    """
    verbose_main parses a command line and calls fun
    with a first argument set to either verbose
    or else to verbose_catch.
    Command line arguments not declared as options here are passed on
    as arguments to fun.
    """
    usage = "usage: %prog [options] [dbfile]"
    parser = OptionParser(usage)
    parser.add_option("-c", "--catch-errors", action="store_true",
                      help=("catch exceptions from update code and "
                            "drop into pdb (default: let it crash"))
    (options, args) = parser.parse_args()
    if options.catch_errors:
        fun(verbose_catch, *args)
    else:
        fun(verbose, *args)


