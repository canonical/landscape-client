import unittest

from twisted.internet.defer import Deferred

from landscape.lib.testing import FSTestCase
from landscape.lib.testing import ProcessDataBuilder
from landscape.lib.testing import TwistedTestCase
from landscape.sysinfo.processes import Processes
from landscape.sysinfo.sysinfo import SysInfoPluginRegistry


class ProcessesTest(FSTestCase, TwistedTestCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.fake_proc = self.makeDir()
        self.processes = Processes(proc_dir=self.fake_proc)
        self.sysinfo = SysInfoPluginRegistry()
        self.sysinfo.add(self.processes)
        self.builder = ProcessDataBuilder(self.fake_proc)

    def test_run_returns_succeeded_deferred(self):
        result = self.processes.run()
        self.assertTrue(isinstance(result, Deferred))
        called = []

        def callback(result):
            called.append(True)

        result.addCallback(callback)
        self.assertTrue(called)

    def test_number_of_processes(self):
        """The number of processes is added as a header."""
        for i in range(3):
            self.builder.create_data(
                i,
                self.builder.RUNNING,
                uid=0,
                gid=0,
                process_name=f"foo{i:d}",
            )
        self.processes.run()
        self.assertEqual(self.sysinfo.get_headers(), [("Processes", "3")])

    def test_no_zombies(self):
        self.processes.run()
        self.assertEqual(self.sysinfo.get_notes(), [])

    def test_number_of_zombies(self):
        """The number of zombies is added as a note."""
        self.builder.create_data(
            99,
            self.builder.ZOMBIE,
            uid=0,
            gid=0,
            process_name="ZOMBERS",
            stat_data="0 0 Z 0 0 0 0",
        )
        self.processes.run()
        self.assertEqual(
            self.sysinfo.get_notes(),
            ["There is 1 zombie process."],
        )

    def test_multiple_zombies(self):
        """Stupid English, and its plurality"""
        for i in range(2):
            self.builder.create_data(
                i,
                self.builder.ZOMBIE,
                uid=0,
                gid=0,
                process_name=f"ZOMBERS{i:d}",
                stat_data="0 0 Z 0 0 0 0",
            )
        self.processes.run()
        self.assertEqual(
            self.sysinfo.get_notes(),
            ["There are 2 zombie processes."],
        )
