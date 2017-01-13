import os

from landscape.tests.helpers import LandscapeTest
from landscape.lib.twisted_util import spawn_process
from landscape.lib.fs import create_file


class SpawnProcessTest(LandscapeTest):

    def setUp(self):
        super(SpawnProcessTest, self).setUp()
        self.command = self.makeFile("#!/bin/sh\necho -n $@")
        os.chmod(self.command, 0o755)

    def test_spawn_process_return_value(self):
        """
        The process is executed and returns the expected exit code.
        """
        create_file(self.command, "#!/bin/sh\nexit 2")

        def callback(args):
            out, err, code = args
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
        def callback(args):
            out, err, code = args
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
        create_file(self.command, "#!/bin/sh\necho -n $@ >&2")

        def callback(args):
            out, err, code = args
            self.assertEqual(out, "")
            self.assertEqual(err, "a b")
            self.assertEqual(code, 0)

        result = spawn_process(self.command, args=("a", "b"))
        result.addCallback(callback)
        return result

    def test_spawn_process_callback(self):
        """
        If a callback for process output is provieded, it is called for every
        line of output.
        """
        create_file(self.command, "#!/bin/sh\n/bin/echo -ne $@")
        param = r"some text\nanother line\nok, last one\n"
        expected = ["some text", "another line", "ok, last one"]
        lines = []

        def line_received(line):
            lines.append(line)

        def callback(args):
            out, err, code = args
            self.assertEqual(expected, lines)

        result = spawn_process(self.command, args=(param,),
                               line_received=line_received)
        result.addCallback(callback)
        return result

    def test_spawn_process_callback_multiple_newlines(self):
        """
        If output ends with more than one newline, empty lines are preserved.
        """
        create_file(self.command, "#!/bin/sh\n/bin/echo -ne $@")
        param = r"some text\nanother line\n\n\n"
        expected = ["some text", "another line", "", ""]
        lines = []

        def line_received(line):
            lines.append(line)

        def callback(args):
            out, err, code = args
            self.assertEqual(expected, lines)

        result = spawn_process(self.command, args=(param,),
                               line_received=line_received)
        result.addCallback(callback)
        return result

    def test_spawn_process_callback_no_newline(self):
        """
        If output ends without a newline, the line is still passed to the
        callback.
        """
        create_file(self.command, "#!/bin/sh\n/bin/echo -ne $@")
        param = r"some text\nanother line\nok, last one"
        expected = ["some text", "another line", "ok, last one"]
        lines = []

        def line_received(line):
            lines.append(line)

        def callback(args):
            out, err, code = args
            self.assertEqual(expected, lines)

        result = spawn_process(self.command, args=(param,),
                               line_received=line_received)
        result.addCallback(callback)
        return result

    def test_spawn_process_with_stdin(self):
        """
        Optionally C{spawn_process} accepts a C{stdin} argument.
        """
        create_file(self.command, "#!/bin/sh\n/bin/cat")

        def callback(args):
            out, err, code = args
            self.assertEqual("hello", out)

        result = spawn_process(self.command, stdin="hello")
        result.addCallback(callback)
        return result
