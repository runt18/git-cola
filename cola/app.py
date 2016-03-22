# Copyright (C) 2009, 2010, 2011, 2012, 2013
# David Aguilar <davvid@gmail.com>
"""Provides the main() routine and ColaApplication"""
from __future__ import division, absolute_import, unicode_literals

import argparse
import os
import shutil
import signal
import sys

# Make homebrew work by default
if sys.platform == 'darwin':
    from distutils import sysconfig
    python_version = sysconfig.get_python_version()
    homebrew_mods = '/usr/local/lib/python{0!s}/site-packages'.format(python_version)
    if os.path.isdir(homebrew_mods):
        sys.path.append(homebrew_mods)


errmsg = """Sorry, you do not seem to have PyQt4 installed.
Please install it before using git-cola.
e.g.: sudo apt-get install python-qt4
"""

# /usr/include/sysexits.h
#define EX_OK           0   /* successful termination */
#define EX_USAGE        64  /* command line usage error */
#define EX_NOINPUT      66  /* cannot open input */
#define EX_UNAVAILABLE  69  /* service unavailable */
EX_OK = 0
EX_USAGE = 64
EX_NOINPUT = 66
EX_UNAVAILABLE = 69


try:
    from cola import sipcompat
except ImportError:
    sys.stderr.write(errmsg)
    sys.exit(EX_UNAVAILABLE)

sipcompat.initialize()

try:
    from PyQt4 import QtCore
except ImportError:
    sys.stderr.write(errmsg)
    sys.exit(EX_UNAVAILABLE)

from PyQt4 import QtGui
from PyQt4.QtCore import SIGNAL

# Import cola modules
from cola import cmds
from cola import core
from cola import compat
from cola import fsmonitor
from cola import git
from cola import gitcfg
from cola import icons
from cola import i18n
from cola import qtcompat
from cola import qtutils
from cola import resources
from cola import utils
from cola import version
from cola.decorators import memoize
from cola.i18n import N_
from cola.interaction import Interaction
from cola.models import main
from cola.widgets import cfgactions
from cola.widgets import startup
from cola.settings import Session


def setup_environment():
    # Allow Ctrl-C to exit
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Session management wants an absolute path when restarting
    sys.argv[0] = sys_argv0 = core.abspath(sys.argv[0])

    # Spoof an X11 display for SSH
    os.environ.setdefault('DISPLAY', ':0')

    if not core.getenv('SHELL', ''):
        for shell in ('/bin/zsh', '/bin/bash', '/bin/sh'):
            if os.path.exists(shell):
                compat.setenv('SHELL', shell)
                break

    # Setup the path so that git finds us when we run 'git cola'
    path_entries = core.getenv('PATH', '').split(os.pathsep)
    bindir = os.path.dirname(sys_argv0)
    path_entries.append(bindir)
    path = os.pathsep.join(path_entries)
    compat.setenv('PATH', path)

    # We don't ever want a pager
    compat.setenv('GIT_PAGER', '')

    # Setup *SSH_ASKPASS
    git_askpass = core.getenv('GIT_ASKPASS')
    ssh_askpass = core.getenv('SSH_ASKPASS')
    if git_askpass:
        askpass = git_askpass
    elif ssh_askpass:
        askpass = ssh_askpass
    elif sys.platform == 'darwin':
        askpass = resources.share('bin', 'ssh-askpass-darwin')
    else:
        askpass = resources.share('bin', 'ssh-askpass')

    compat.setenv('GIT_ASKPASS', askpass)
    compat.setenv('SSH_ASKPASS', askpass)

    # --- >8 --- >8 ---
    # Git v1.7.10 Release Notes
    # =========================
    #
    # Compatibility Notes
    # -------------------
    #
    #  * From this release on, the "git merge" command in an interactive
    #   session will start an editor when it automatically resolves the
    #   merge for the user to explain the resulting commit, just like the
    #   "git commit" command does when it wasn't given a commit message.
    #
    #   If you have a script that runs "git merge" and keeps its standard
    #   input and output attached to the user's terminal, and if you do not
    #   want the user to explain the resulting merge commits, you can
    #   export GIT_MERGE_AUTOEDIT environment variable set to "no", like
    #   this:
    #
    #        #!/bin/sh
    #        GIT_MERGE_AUTOEDIT=no
    #        export GIT_MERGE_AUTOEDIT
    #
    #   to disable this behavior (if you want your users to explain their
    #   merge commits, you do not have to do anything).  Alternatively, you
    #   can give the "--no-edit" option to individual invocations of the
    #   "git merge" command if you know everybody who uses your script has
    #   Git v1.7.8 or newer.
    # --- >8 --- >8 ---
    # Longer-term: Use `git merge --no-commit` so that we always
    # have a chance to explain our merges.
    compat.setenv('GIT_MERGE_AUTOEDIT', 'no')


# style note: we use camelCase here since we're masquerading a Qt class
class ColaApplication(object):
    """The main cola application

    ColaApplication handles i18n of user-visible data
    """

    def __init__(self, argv, locale=None, gui=True):
        cfgactions.install()
        i18n.install(locale)
        qtcompat.install()
        qtutils.install()
        icons.install()

        QtCore.QObject.connect(fsmonitor.instance(), SIGNAL('files_changed'),
                               self._update_files)

        if gui:
            self._app = current(tuple(argv))
            self._app.setWindowIcon(icons.cola())
        else:
            self._app = QtCore.QCoreApplication(argv)

    def activeWindow(self):
        """Wrap activeWindow()"""
        return self._app.activeWindow()

    def desktop(self):
        return self._app.desktop()

    def exec_(self):
        """Wrap exec_()"""
        return self._app.exec_()

    def set_view(self, view):
        if hasattr(self._app, 'view'):
            self._app.view = view

    def _update_files(self):
        # Respond to file system updates
        cmds.do(cmds.Refresh)


@memoize
def current(argv):
    return ColaQApplication(list(argv))


class ColaQApplication(QtGui.QApplication):

    def __init__(self, argv):
        QtGui.QApplication.__init__(self, argv)
        self.view = None ## injected by application_start()

    def event(self, e):
        if e.type() == QtCore.QEvent.ApplicationActivate:
            cfg = gitcfg.current()
            if cfg.get('cola.refreshonfocus', False):
                cmds.do(cmds.Refresh)
        return QtGui.QApplication.event(self, e)

    def commitData(self, session_mgr):
        """Save session data"""
        if self.view is None:
            return
        sid = session_mgr.sessionId()
        skey = session_mgr.sessionKey()
        session_id = '{0!s}_{1!s}'.format(sid, skey)
        session = Session(session_id, repo=core.getcwd())
        self.view.save_state(settings=session)


def process_args(args):
    if args.version:
        # Accept 'git cola --version' or 'git cola version'
        version.print_version()
        sys.exit(EX_OK)

    # Handle session management
    restore_session(args)

    # Bail out if --repo is not a directory
    repo = core.decode(args.repo)
    if repo.startswith('file:'):
        repo = repo[len('file:'):]
    repo = core.realpath(repo)
    if not core.isdir(repo):
        errmsg = N_('fatal: "%s" is not a directory.  '
                    'Please specify a correct --repo <path>.') % repo
        core.stderr(errmsg)
        sys.exit(EX_USAGE)

    # We do everything relative to the repo root
    os.chdir(args.repo)
    return repo


def restore_session(args):
    # args.settings is provided when restoring from a session.
    args.settings = None
    if args.session is None:
        return
    session = Session(args.session)
    if session.load():
        args.settings = session
        args.repo = session.repo


def application_init(args, update=False):
    """Parses the command-line arguments and starts git-cola
    """
    # Ensure that we're working in a valid git repository.
    # If not, try to find one.  When found, chdir there.
    setup_environment()
    process_args(args)

    app = new_application(args)
    model = new_model(app, args.repo,
                      prompt=args.prompt, settings=args.settings)
    if update:
        model.update_status()
    cfg = gitcfg.current()
    return ApplicationContext(args, app, cfg, model)


def application_start(context, view, monitor_refs_only=False):
    """Show the GUI and start the main event loop"""
    # Store the view for session management
    context.app.set_view(view)

    # Make sure that we start out on top
    view.show()
    view.raise_()

    # Scan for the first time
    runtask = qtutils.RunTask(parent=view)
    init_update_task(view, runtask, context.model)

    # Start the filesystem monitor thread
    fsmonitor.instance().start(monitor_refs_only)

    msg_timer = QtCore.QTimer()
    msg_timer.setSingleShot(True)
    msg_timer.connect(msg_timer, SIGNAL('timeout()'), _send_msg)
    msg_timer.start(0)

    # Start the event loop
    result = context.app.exec_()

    # All done, cleanup
    fsmonitor.instance().stop()
    QtCore.QThreadPool.globalInstance().waitForDone()

    tmpdir = utils.tmpdir()
    shutil.rmtree(tmpdir, ignore_errors=True)

    return result


def add_common_arguments(parser):
    # We also accept 'git cola version'
    parser.add_argument('--version', default=False, action='store_true',
                        help='print version number')

    # Specifies a git repository to open
    parser.add_argument('-r', '--repo', metavar='<repo>', default=core.getcwd(),
                        help='open the specified git repository')

    # Specifies that we should prompt for a repository at startup
    parser.add_argument('--prompt', action='store_true', default=False,
                        help='prompt for a repository')

    # Resume an X Session Management session
    parser.add_argument('-session', metavar='<session>', default=None,
                        help=argparse.SUPPRESS)


def new_application(args):
    # Initialize the app
    return ColaApplication(sys.argv)


def new_model(app, repo, prompt=False, settings=None):
    model = main.model()
    valid = False
    if not prompt:
        valid = model.set_worktree(repo)
        if not valid:
            # We are not currently in a git repository so we need to find one.
            # Before prompting the user for a repostiory, check if they've
            # configured a default repository and attempt to use it.
            default_repo = gitcfg.current().get('cola.defaultrepo')
            if default_repo:
                valid = model.set_worktree(default_repo)

    while not valid:
        # If we've gotten into this loop then that means that neither the
        # current directory nor the default repository were available.
        # Prompt the user for a repository.
        startup_dlg = startup.StartupDialog(app.activeWindow(),
                                            settings=settings)
        gitdir = startup_dlg.find_git_repo()
        if not gitdir:
            sys.exit(EX_NOINPUT)
        valid = model.set_worktree(gitdir)

    # Finally, go to the root of the git repo
    os.chdir(model.git.worktree())
    return model


def init_update_task(parent, runtask, model):
    """Update the model in the background

    git-cola should startup as quickly as possible.

    """

    def update_status():
        model.update_status(update_index=True)

    task = qtutils.SimpleTask(parent, update_status)
    runtask.start(task)


def _send_msg():
    if git.GIT_COLA_TRACE == 'trace':
        msg = 'info: debug mode enabled using GIT_COLA_TRACE=trace'
        Interaction.log(msg)


class ApplicationContext(object):

    def __init__(self, args, app, cfg, model):
        self.args = args
        self.app = app
        self.cfg = cfg
        self.model = model
