#!/usr/bin/env python -u
##############################################################################
#
# Copyright (c) 2011 Ilya Margolin
# Copyright (c) 2007 Agendaless Consulting and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the BSD-like license at
# http://www.repoze.org/LICENSE.txt.  A copy of the license should accompany
# this distribution.  THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL
# EXPRESS OR IMPLIED WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND
# FITNESS FOR A PARTICULAR PURPOSE
#
##############################################################################


"""
uptimemon.py [-p processname=uptime_seconds]  [-g groupname=uptime_seconds]

An event listener meant to be subscribed to TICK_60 (or TICK_5)
events, which restarts any processes that are children of
supervisord that run longer than specified.

A supervisor config snippet that tells supervisor to use this script
as a listener is below.

[eventlistener:uptimemon]
command=python uptimemon.py [options]
events=TICK_60

Options:

-p -- specify a process_name=uptime_seconds pair.  Restart the supervisor
      process named 'process_name' when it runs longer than uptime_seconds.
      If this process is in a group, it can be specified using the
      'process_name:group_name' syntax.

-g -- specify a group_name=uptime_seconds pair.  Restart any process in this
      group when it runs longer than uptime_seconds.

The -p and -g options may be specified more than once, allowing for
specification of multiple groups and processes.

A sample invocation:

uptimemon.py -p program1=600 -p thegroup:theprog=3600 -g thegroup=3600
"""

import os
import sys
import xmlrpclib
import logging

from supervisor import childutils


def usage():
    import posix
    print __doc__
    sys.exit(posix.EX_USAGE)


class Uptimemon:

    def __init__(self, uptime_per_program, uptime_per_group, rpc):
        self.uptime_per_program = uptime_per_program
        self.uptime_per_group = uptime_per_group
        self.rpc = rpc
        self.stdin = sys.stdin
        self.stdout = sys.stdout
        self.stderr = sys.stderr

    def roundhouse_forever(self):
        while 1:
            self.roundhouse_once()

    def roundhouse_once(self):
        # we explicitly use self.stdin, self.stdout, and self.stderr
        # instead of sys.* so we can unit test this code
        headers, payload = childutils.listener.wait(self.stdin, self.stdout)

        logging.info('headers: %s, payload: %s', headers, payload)
        if headers['eventname'].startswith('TICK'):
            self.react_to_tick()

        childutils.listener.ok(self.stdout)

    def react_to_tick(self):
        infos = self.rpc.supervisor.getAllProcessInfo()

        for info in infos:
            self.check_process_info(**info)

        self.stderr.flush()

    def check_process_info(self, name=None, group=None, now=None,
            start=None, statename=None):
        uptime = now - start
        full_name = '%s:%s' % (group, name)

        if statename != 'RUNNING':
            return

        max_uptime = (self.uptime_per_program.get(name)
                or self.uptime_per_program.get(full_name)
                or self.uptime_per_group.get(group))

        if not max_uptime:
            return

        if uptime > max_uptime:
            logging.info('Process %s is running since %i seconds, longer than '
                    'allowed %i', name, uptime, max_uptime)
            self.restart(full_name)

    def restart(self, name):
        logging.info('Restarting %s', name)

        try:
            self.rpc.supervisor.stopProcess(name)
        except xmlrpclib.Fault, e:
            logging.warning('Failed to stop process %s: %s', name, e)

        try:
            self.rpc.supervisor.startProcess(name)
        except xmlrpclib.Fault, e:
            logging.warning('Failed to start process %s after stopping it: %s',
                    name, e)


def parse_option(option, value):
    try:
        name, uptime = value.split('=')
        uptime = long(uptime)
        return name, uptime
    except ValueError:
        print 'Unparseable value %r for %r' % (value, option)
        usage()


def main():
    import getopt

    short_args = "hp:g:"
    long_args = [
        "help",
        "program=",
        "group=",
        ]
    arguments = sys.argv[1:]
    if not arguments:
        usage()
    try:
        opts, args = getopt.getopt(arguments, short_args, long_args)
    except:
        usage()

    uptime_per_program = {}
    uptime_per_group = {}

    for option, value in opts:
        if option in ('-h', '--help'):
            usage()

        if option in ('-p', '--program'):
            name, uptime = parse_option(option, value)
            uptime_per_program[name] = uptime

        if option in ('-g', '--group'):
            name, uptime = parse_option(option, value)
            uptime_per_group[name] = uptime

    logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s %(levelname)s %(message)s')
    rpc = childutils.getRPCInterface(os.environ)
    uptimemon = Uptimemon(uptime_per_program, uptime_per_group, rpc)
    uptimemon.roundhouse_forever()

if __name__ == '__main__':
    main()
