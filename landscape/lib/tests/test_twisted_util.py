import os

from landscape.tests.helpers import LandscapeTest
from landscape.lib.twisted_util import spawn_process


class SpawnProcessTest(LandscapeTest):

    def setUp(self):
        self.command = self.makeFile("#!/bin/sh\necho -n $@")
        os.chmod(self.command, 0755)

    def tearDown(self):
        os.unlink(self.command)

    def _write_command(self, command):
        command_file = open(self.command, "w")
        command_file.write(command)
        command_file.close()

    def test_spawn_process_return_value(self):
        """
        The process is executed and returns the expected exit code.
        """
        self._write_command("#!/bin/sh\nexit 2")

        def callback((out, err, code)):
            self.assertEqual(out, "")
            self.assertEqual(err, "")
            self.assertEqual(code, 2)

        result = spawn_process(self.command)
        result.addCallback(callback)
        return result

    def test_spawn_process_output(self):
        """
        The process returns the expected standard output.
        """
        def callback((out, err, code)):
            self.assertEqual(out, "a b")
            self.assertEqual(err, "")
            self.assertEqual(code, 0)

        result = spawn_process(self.command, args=("a", "b"))
        result.addCallback(callback)
        return result

    def test_spawn_process_error(self):
        """
        The process returns the expected standard error.
        """

        self._write_command("#!/bin/sh\necho -n $@ >&2")

        def callback((out, err, code)):
            self.assertEqual(out, "")
            self.assertEqual(err, "a b")
            self.assertEqual(code, 0)

        result = spawn_process(self.command, args=("a", "b"))
        result.addCallback(callback)
        return result
