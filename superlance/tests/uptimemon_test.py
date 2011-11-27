import sys
import unittest
from mock import *
from StringIO import StringIO
import logging
from logging.handlers import BufferingHandler
from superlance.tests.dummy import *
from superlance.uptimemon import Uptimemon
from supervisor.childutils import listener, pcomm

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
    def _getTargetClass(self):
        from superlance.memmon import Memmon
        return Memmon
    
    def _makeOne(self, *opts):
        return self._getTargetClass()(*opts)

    def _makeOnePopulated(self, programs, groups, any):
        rpc = DummyRPCServer()
        sendmail = 'cat - > /dev/null'
        email = 'chrism@plope.com'
        memmon = self._makeOne(programs, groups, any, sendmail, email, rpc)
        memmon.stdin = StringIO()
        memmon.stdout = StringIO()
        memmon.stderr = StringIO()
        memmon.pscommand = 'echo 22%s'
        return memmon
        
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
        rpc.supervisor.getAllProcessInfo.return_value = range(3)
        uptimemon = Uptimemon({}, {}, rpc)
        uptimemon.check_process_info = Mock()
        uptimemon.react_to_tick()
        assert uptimemon.check_process_info.call_count == 3

    def test_check_process_info_should_restart_processes(self):
        logging.root.setLevel(logging.INFO)
        handler = TestHandler()
        logging.root.addHandler(handler)
        name = 'foo'
        uptimemon = Uptimemon({name:600}, {}, Mock())
        uptimemon.restart = Mock()
        uptimemon.check_process_info({
            'name':name,
            'group':'group',
            'now':1700,
            'starttime':1000})
        uptimemon.restart.assert_called_with(name)
        assert handler.buffer[0]['msg'] == 'Process %s is running since %i seconds, longer than allowed %i'

    def test_runforever_tick_programs(self):
        programs = {'foo':0, 'bar':0, 'baz_01':0 }
        groups = {}
        any = None
        memmon = self._makeOnePopulated(programs, groups, any)
        memmon.stdin.write('eventname:TICK len:0\n')
        memmon.stdin.seek(0)
        memmon.runforever(test=True)
        lines = memmon.stderr.getvalue().split('\n')
        self.assertEqual(len(lines), 8)
        self.assertEqual(lines[0], 'Checking programs foo=0, bar=0, baz_01=0')
        self.assertEqual(lines[1], 'RSS of foo:foo is 2264064')
        self.assertEqual(lines[2], 'Restarting foo:foo')
        self.assertEqual(lines[3], 'RSS of bar:bar is 2265088')
        self.assertEqual(lines[4], 'Restarting bar:bar')
        self.assertEqual(lines[5], 'RSS of baz:baz_01 is 2265088')
        self.assertEqual(lines[6], 'Restarting baz:baz_01')
        self.assertEqual(lines[7], '')
        mailed = memmon.mailed.split('\n')
        self.assertEqual(len(mailed), 4)
        self.assertEqual(mailed[0], 'To: chrism@plope.com')
        self.assertEqual(mailed[1],
                         'Subject: memmon: process baz:baz_01 restarted')
        self.assertEqual(mailed[2], '')
        self.failUnless(mailed[3].startswith('memmon.py restarted'))

    def test_runforever_tick_groups(self):
        programs = {}
        groups = {'foo':0}
        any = None
        memmon = self._makeOnePopulated(programs, groups, any)
        memmon.stdin.write('eventname:TICK len:0\n')
        memmon.stdin.seek(0)
        memmon.runforever(test=True)
        lines = memmon.stderr.getvalue().split('\n')
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], 'Checking groups foo=0')
        self.assertEqual(lines[1], 'RSS of foo:foo is 2264064')
        self.assertEqual(lines[2], 'Restarting foo:foo')
        self.assertEqual(lines[3], '')
        mailed = memmon.mailed.split('\n')
        self.assertEqual(len(mailed), 4)
        self.assertEqual(mailed[0], 'To: chrism@plope.com')
        self.assertEqual(mailed[1],
          'Subject: memmon: process foo:foo restarted')
        self.assertEqual(mailed[2], '')
        self.failUnless(mailed[3].startswith('memmon.py restarted'))

    def test_runforever_tick_any(self):
        programs = {}
        groups = {}
        any = 0
        memmon = self._makeOnePopulated(programs, groups, any)
        memmon.stdin.write('eventname:TICK len:0\n')
        memmon.stdin.seek(0)
        memmon.runforever(test=True)
        lines = memmon.stderr.getvalue().split('\n')
        self.assertEqual(len(lines), 8)
        self.assertEqual(lines[0], 'Checking any=0')
        self.assertEqual(lines[1], 'RSS of foo:foo is 2264064')
        self.assertEqual(lines[2], 'Restarting foo:foo')
        self.assertEqual(lines[3], 'RSS of bar:bar is 2265088')
        self.assertEqual(lines[4], 'Restarting bar:bar')
        self.assertEqual(lines[5], 'RSS of baz:baz_01 is 2265088')
        self.assertEqual(lines[6], 'Restarting baz:baz_01')
        self.assertEqual(lines[7], '')
        mailed = memmon.mailed.split('\n')
        self.assertEqual(len(mailed), 4)

    def test_runforever_tick_programs_and_groups(self):
        programs = {'baz_01':0}
        groups = {'foo':0}
        any = None
        memmon = self._makeOnePopulated(programs, groups, any)
        memmon.stdin.write('eventname:TICK len:0\n')
        memmon.stdin.seek(0)
        memmon.runforever(test=True)
        lines = memmon.stderr.getvalue().split('\n')
        self.assertEqual(len(lines), 7)
        self.assertEqual(lines[0], 'Checking programs baz_01=0')
        self.assertEqual(lines[1], 'Checking groups foo=0')
        self.assertEqual(lines[2], 'RSS of foo:foo is 2264064')
        self.assertEqual(lines[3], 'Restarting foo:foo')
        self.assertEqual(lines[4], 'RSS of baz:baz_01 is 2265088')
        self.assertEqual(lines[5], 'Restarting baz:baz_01')
        self.assertEqual(lines[6], '')
        mailed = memmon.mailed.split('\n')
        self.assertEqual(len(mailed), 4)
        self.assertEqual(mailed[0], 'To: chrism@plope.com')
        self.assertEqual(mailed[1],
                         'Subject: memmon: process baz:baz_01 restarted')
        self.assertEqual(mailed[2], '')
        self.failUnless(mailed[3].startswith('memmon.py restarted'))

    def test_runforever_tick_programs_norestart(self):
        programs = {'foo': sys.maxint}
        groups = {}
        any = None
        memmon = self._makeOnePopulated(programs, groups, any)
        memmon.stdin.write('eventname:TICK len:0\n')
        memmon.stdin.seek(0)
        memmon.runforever(test=True)
        lines = memmon.stderr.getvalue().split('\n')
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], 'Checking programs foo=%s' % sys.maxint)
        self.assertEqual(lines[1], 'RSS of foo:foo is 2264064')
        self.assertEqual(lines[2], '')
        self.assertEqual(memmon.mailed, False)

    def test_stopprocess_fault_tick_programs_norestart(self):
        programs = {'foo': sys.maxint}
        groups = {}
        any = None
        memmon = self._makeOnePopulated(programs, groups, any)
        memmon.stdin.write('eventname:TICK len:0\n')
        memmon.stdin.seek(0)
        memmon.runforever(test=True)
        lines = memmon.stderr.getvalue().split('\n')
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], 'Checking programs foo=%s' % sys.maxint)
        self.assertEqual(lines[1], 'RSS of foo:foo is 2264064')
        self.assertEqual(lines[2], '')
        self.assertEqual(memmon.mailed, False)

    def test_stopprocess_fails_to_stop(self):
        programs = {'BAD_NAME': 0}
        groups = {}
        any = None
        memmon = self._makeOnePopulated(programs, groups, any)
        memmon.stdin.write('eventname:TICK len:0\n')
        memmon.stdin.seek(0)
        from supervisor.process import ProcessStates
        memmon.rpc.supervisor.all_process_info =  [ {
            'name':'BAD_NAME',
            'group':'BAD_NAME',
            'pid':11,
            'state':ProcessStates.RUNNING,
            'statename':'RUNNING',
            'start':0,
            'stop':0,
            'spawnerr':'',
            'now':0,
            'description':'BAD_NAME description',
             } ]
        import xmlrpclib
        self.assertRaises(xmlrpclib.Fault, memmon.runforever, True)
        lines = memmon.stderr.getvalue().split('\n')
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], 'Checking programs BAD_NAME=%s' % 0)
        self.assertEqual(lines[1], 'RSS of BAD_NAME:BAD_NAME is 2264064')
        self.assertEqual(lines[2], 'Restarting BAD_NAME:BAD_NAME')
        self.failUnless(lines[3].startswith('Failed'))
        mailed = memmon.mailed.split('\n')
        self.assertEqual(len(mailed), 4)
        self.assertEqual(mailed[0], 'To: chrism@plope.com')
        self.assertEqual(mailed[1],
          'Subject: memmon: failed to stop process BAD_NAME:BAD_NAME, exiting')
        self.assertEqual(mailed[2], '')
        self.failUnless(mailed[3].startswith('Failed'))
        
if __name__ == '__main__':
    unittest.main()  
