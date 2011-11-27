#!/usr/bin/env python -u
##############################################################################
#
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

# A event listener meant to be subscribed to TICK_60 (or TICK_5)
# events, which restarts any processes that are children of
# supervisord that consume "too much" memory.  Performs horrendous
# screenscrapes of ps output.  Works on Linux and OS X (Tiger/Leopard)
# as far as I know.

# A supervisor config snippet that tells supervisor to use this script
# as a listener is below.
#
# [eventlistener:uptimemon]
# command=python uptimemon.py [options]
# events=TICK_60

"""\
uptimemon.py [-p processname=byte_size]  [-g groupname=byte_size] 

Options:

-p -- specify a process_name=byte_size pair.  Restart the supervisor
      process named 'process_name' when it uses more than byte_size
      RSS.  If this process is in a group, it can be specified using
      the 'process_name:group_name' syntax.

-g -- specify a group_name=byte_size pair.  Restart any process in this group
      when it uses more than byte_size RSS.

The -p and -g options may be specified more than once, allowing for
specification of multiple groups and processes.

A sample invocation:

uptimemon.py -p program1=200MB -p theprog:thegroup=100MB -g thegroup=100MB
"""

import os
import sys
import xmlrpclib

from supervisor import childutils
from supervisor.datatypes import byte_size

def usage():
    import posix
    print __doc__
    sys.exit(posix.EX_USAGE)

class Uptimemon:
    def __init__(self, programs, groups, rpc):
        self.programs = programs
        self.groups = groups
        self.rpc = rpc
        self.stdin = sys.stdin
        self.stdout = sys.stdout
        self.stderr = sys.stderr

    def runforever(self, test=False):
        while 1:
            # we explicitly use self.stdin, self.stdout, and self.stderr
            # instead of sys.* so we can unit test this code
            headers, payload = childutils.listener.wait(self.stdin, self.stdout)

            if not headers['eventname'].startswith('TICK'):
                # do nothing with non-TICK events
                childutils.listener.ok(self.stdout)
                if test:
                    break
                continue

            infos = self.rpc.supervisor.getAllProcessInfo()

            for info in infos:
                name = info['name']
                group = info['group']
                pname = '%s:%s' % (group, name)

                for n in name, pname:
                    if n in self.programs:
                        self.stderr.write('RSS of %s is %s\n' % (pname, rss))
                        if  rss > self.programs[name]:
                            self.restart(pname, rss)
                            continue

                if group in self.groups:
                    self.stderr.write('RSS of %s is %s\n' % (pname, rss))
                    if rss > self.groups[group]:
                        self.restart(pname, rss)
                        continue


            self.stderr.flush()
            childutils.listener.ok(self.stdout)
            if test:
                break

    def restart(self, name, rss):
        self.stderr.write('Restarting %s\n' % name)

        try:
            self.rpc.supervisor.stopProcess(name)
        except xmlrpclib.Fault, what:
            msg = ('Failed to stop process %s (RSS %s), exiting: %s' %
                   (name, rss, what))
            raise

        try:
            self.rpc.supervisor.startProcess(name)
        except xmlrpclib.Fault, what:
            msg = ('Failed to start process %s after stopping it, '
                   'exiting: %s' % (name, what))
            raise

def parse_namesize(option, value):
    try:
        name, size = value.split('=')
    except ValueError:
        print 'Unparseable value %r for %r' % (value, option)
        usage()
    size = parse_size(option, size)
    return name, size

def main():
    import getopt
    short_args="hp:g:"
    long_args=[
        "help",
        "program=",
        "group=",
        ]
    arguments = sys.argv[1:]
    if not arguments:
        usage()
    try:
        opts, args=getopt.getopt(arguments, short_args, long_args)
    except:
        print __doc__
        sys.exit(2)

    programs = {}
    groups = {}

    for option, value in opts:

        if option in ('-h', '--help'):
            usage()

        if option in ('-p', '--program'):
            name, size = parse_namesize(option, value)
            programs[name] = size

        if option in ('-g', '--group'):
            name, size = parse_namesize(option, value)
            groups[name] = size

    rpc = childutils.getRPCInterface(os.environ)
    uptimemon = Uptimemon(programs, groups, rpc)
    uptimemon.runforever()

if __name__ == '__main__':
    main()
    
    
    
