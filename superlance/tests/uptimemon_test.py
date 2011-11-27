import sys
import unittest
from mock import *
from StringIO import StringIO
import logging
from logging.handlers import BufferingHandler
from superlance.uptimemon import Uptimemon

class TestHandler(BufferingHandler):
    def __init__(self):
        # BufferingHandler takes a "capacity" argument
        # so as to know when to flush. As we're overriding
        # shouldFlush anyway, we can set a capacity of zero.
        # You can call flush() manually to clear out the
        # buffer.
        BufferingHandler.__init__(self, 0)

    def shouldFlush(self):
        return False

    def emit(self, record):
        self.buffer.append(record.__dict__)


class UptimemonTests(unittest.TestCase):

    def setUp(self):
        logging.root.setLevel(logging.INFO)
        handler = TestHandler()
        logging.root.addHandler(handler)
        self.log = handler.buffer

    def test_roundhouse_once_should_react_to_tick_events(self):
        programs = {'foo':600}
        groups = {}
        uptimemon = Uptimemon(programs, groups, MagicMock())
        uptimemon.react_to_tick = Mock()

        uptimemon.stdin = StringIO()
        uptimemon.stdout = StringIO()
        uptimemon.stdin.write('eventname:TICK_5 len:0\n')
        uptimemon.stdin.seek(0)
        uptimemon.roundhouse_once()
        assert uptimemon.react_to_tick.call_count == 1

    def test_roundhouse_once_should_not_react_to_non_tick_events(self):
        programs = {'foo':600}
        groups = {}
        uptimemon = Uptimemon(programs, groups, Mock())
        uptimemon.react_to_tick = Mock()

        uptimemon.stdin = StringIO()
        uptimemon.stdout = StringIO()
        uptimemon.stdin.write('eventname:NOTATICK len:0\n')
        uptimemon.stdin.seek(0)
        uptimemon.roundhouse_once()
        assert uptimemon.react_to_tick.call_count == 0

    def test_react_to_tick_should_call_check_process_on_every_process(self):
        rpc = Mock()
        rpc.supervisor.getAllProcessInfo.return_value = ({}, {}, {})
        uptimemon = Uptimemon({}, {}, rpc)
        uptimemon.check_process_info = Mock()
        uptimemon.react_to_tick()
        assert uptimemon.check_process_info.call_count == 3

    def test_check_process_info_should_restart_processes(self):
        uptimemon = Uptimemon({'foo':600}, {}, Mock())
        uptimemon.restart = Mock()
        uptimemon.check_process_info(
            name='foo',
            group='group',
            now=1700,
            start=1000,
            statename='RUNNING')
        uptimemon.restart.assert_called_with('group:foo')
        assert self.log[0]['msg'] == 'Process %s is running since %i seconds, longer than allowed %i'

    def test_check_process_info_should_restart_processes_by_group(self):
        uptimemon = Uptimemon({}, {'foo':600}, Mock())
        uptimemon.restart = Mock()
        uptimemon.check_process_info(
            name='a_name',
            group='foo',
            now=1700,
            start=1000,
            statename='RUNNING')
        uptimemon.restart.assert_called_with('foo:a_name')
        assert self.log[0]['msg'] == 'Process %s is running since %i seconds, longer than allowed %i'

    def test_check_process_info_should_restart_processes_by_full_name(self):
        uptimemon = Uptimemon({'group:foo':600}, {}, Mock())
        uptimemon.restart = Mock()
        uptimemon.check_process_info(
            name='foo',
            group='group',
            now=1700,
            start=1000,
            statename='RUNNING')
        uptimemon.restart.assert_called_with('group:foo')
        assert self.log[0]['msg'] == 'Process %s is running since %i seconds, longer than allowed %i'

    def test_check_process_info_should_not_restart_not_running(self):
        uptimemon = Uptimemon({'group:foo':600}, {}, Mock())
        uptimemon.restart = Mock()
        uptimemon.check_process_info(
            name='foo',
            group='group',
            now=1700,
            start=1000,
            statename='STOPPED')
        assert not uptimemon.restart.called

    def test_should_not_restart_if_process_uptime_not_defined(self):
        uptimemon = Uptimemon({}, {}, Mock())
        uptimemon.restart = Mock()
        uptimemon.check_process_info(
            name='foo',
            group='group',
            now=1700,
            start=1000,
            statename='RUNNING')
        assert not uptimemon.restart.called

    def test_restart_should_warn_when_stopping_failed(self):
        import xmlrpclib
        rpc = Mock()
        rpc.supervisor.stopProcess.side_effect = xmlrpclib.Fault(13, 'failed')
        uptimemon = Uptimemon({}, {}, rpc)

        uptimemon.restart('process')
        self.assertEquals(self.log[0]['msg'], 'Restarting %s')
        self.assertEquals(self.log[1]['msg'], 'Failed to stop process %s: %s')

    def test_restart_should_warn_when_starting_failed(self):
        import xmlrpclib
        rpc = Mock()
        rpc.supervisor.startProcess.side_effect = xmlrpclib.Fault(13, 'failed')
        uptimemon = Uptimemon({}, {}, rpc)

        uptimemon.restart('process')
        self.assertEquals(self.log[0]['msg'], 'Restarting %s')
        self.assertEquals(self.log[1]['msg'], 'Failed to start process %s after stopping it: %s')

if __name__ == '__main__':
    unittest.main()
