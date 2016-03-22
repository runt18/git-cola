from __future__ import division, absolute_import, unicode_literals

import os
import sys

from cola import core
from cola.i18n import N_


class Interaction(object):
    """Prompts the user and answers questions"""

    VERBOSE = bool(os.getenv('GIT_COLA_VERBOSE'))

    @staticmethod
    def information(title,
                    message=None, details=None, informative_text=None):
        if message is None:
            message = title
        scope = {}
        scope['title'] = title
        scope['title_dashes'] = '-' * len(title)
        scope['message'] = message
        scope['details'] = details and '\n'+details or ''
        scope['informative_text'] = (informative_text and
                '\n'+informative_text or '')
        sys.stdout.write("""
{title!s}
{title_dashes!s}
{message!s}{details!s}{informative_text!s}\n""".format(**scope))

    @classmethod
    def critical(cls, title, message=None, details=None):
        """Show a warning with the provided title and message."""
        cls.information(title, message=message, details=details)

    @classmethod
    def confirm(cls, title, text, informative_text, ok_text,
                icon=None, default=True):

        cls.information(title, message=text,
                        informative_text=informative_text)
        if default:
            prompt = '{0!s}? [Y/n] '.format(ok_text)
        else:
            prompt = '{0!s}? [y/N] '.format(ok_text)
        sys.stdout.write(prompt)
        answer = sys.stdin.readline().strip()
        if answer:
            result = answer.lower().startswith('y')
        else:
            result = default
        return result

    @classmethod
    def question(cls, title, message, default=True):
        return cls.confirm(title, message, '',
                           ok_text=N_('Continue'), default=default)

    @classmethod
    def run_command(cls, title, cmd):
        cls.log('$ ' + core.list2cmdline(cmd))
        status, out, err = core.run_command(cmd)
        cls.log_status(status, out, err)
        return status, out, err

    @classmethod
    def confirm_config_action(cls, name, opts):
        return cls.confirm(N_('Run %s?') % name,
                           N_('Run the "%s" command?') % name,
                           '',
                           ok_text=N_('Run'))

    @classmethod
    def log_status(cls, status, out, err=None):
        msg = (
           (out and ((N_('Output: %s') % out) + '\n') or '') +
           (err and ((N_('Errors: %s') % err) + '\n') or '') +
           N_('Exit code: %s') % status
        )
        cls.log(msg)

    @classmethod
    def log(cls, message):
        if cls.VERBOSE:
            core.stdout(message)

    safe_log = log
