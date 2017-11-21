import os
import unittest

from landscape.lib import testing
from landscape.lib.fs import create_text_file
from landscape.lib.twisted_util import spawn_process


class SpawnProcessTest(testing.TwistedTestCase, testing.FSTestCase,
                       unittest.TestCase):

    def setUp(self):
        super(SpawnProcessTest, self).setUp()
        self.command = self.makeFile("#!/bin/sh\necho -n $@")
        os.chmod(self.command, 0o755)

    def test_spawn_process_return_value(self):
        """
        The process is executed and returns the expected exit code.
        """
        create_text_file(self.command, "#!/bin/sh\nexit 2")

        def callback(args):
            out, err, code = args
            self.assertEqual(out, b"")
            self.assertEqual(err, b"")
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
            self.assertEqual(out, b"a b")
            self.assertEqual(err, b"")
            self.assertEqual(code, 0)

        result = spawn_process(self.command, args=("a", "b"))
        result.addCallback(callback)
        return result

    def test_spawn_process_error(self):
        """
        The process returns the expected standard error.
        """
        create_text_file(self.command, "#!/bin/sh\necho -n $@ >&2")

        def callback(args):
            out, err, code = args
            self.assertEqual(out, b"")
            self.assertEqual(err, b"a b")
            self.assertEqual(code, 0)

        result = spawn_process(self.command, args=("a", "b"))
        result.addCallback(callback)
        return result

    def test_spawn_process_callback(self):
        """
        If a callback for process output is provieded, it is called for every
        line of output.
        """
        create_text_file(self.command, "#!/bin/sh\n/bin/echo -ne $@")
        param = r"some text\nanother line\nok, last one\n"
        expected = [b"some text", b"another line", b"ok, last one"]
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
        create_text_file(self.command, "#!/bin/sh\n/bin/echo -ne $@")
        param = r"some text\nanother line\n\n\n"
        expected = [b"some text", b"another line", b"", b""]
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
        create_text_file(self.command, "#!/bin/sh\n/bin/echo -ne $@")
        param = r"some text\nanother line\nok, last one"
        expected = [b"some text", b"another line", b"ok, last one"]
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
        create_text_file(self.command, "#!/bin/sh\n/bin/cat")

        def callback(args):
            out, err, code = args
            self.assertEqual(b"hello", out)

        result = spawn_process(self.command, stdin="hello")
        result.addCallback(callback)
        return result

    def test_spawn_process_with_signal(self):
        """
        In case the process gets terminated by a signal, it raises a
        C{SignalError}.
        """
        # This script will kill itself.
        create_text_file(self.command, """\
#!/bin/sh
kill $$
""")

        def callback(args):
            raise RuntimeError("Errback was not called.")

        def errback(failure):
            out, err, code = failure.value.args
            self.assertEqual(out, b"")
            self.assertEqual(err, b"")
            self.assertEqual(code, 15)  # 15 for SIGTERM

        result = spawn_process(self.command)
        result.addCallbacks(callback, errback)
        return result
