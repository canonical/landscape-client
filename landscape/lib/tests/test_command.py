from landscape.tests.helpers import LandscapeTest

from landscape.lib.command import run_command, CommandError


class CommandTest(LandscapeTest):

    def setUp(self):
        super(CommandTest, self).setUp()

    def test_basic(self):
        self.assertEqual(run_command("echo test"), "test")

    def test_non_0_exit_status(self):
        try:
            run_command("false")
        except CommandError, error:
            self.assertEqual(error.command, "false")
            self.assertEqual(error.output, "")
            self.assertEqual(error.exit_status, 1)
        else:
            self.fail("CommandError not raised")

    def test_error_str(self):
        self.assertEqual(str(CommandError("test_command", 1, "test output")),
                         "'test_command' exited with status 1 "
                         "(test output)")

    def test_error_repr(self):
        self.assertEqual(repr(CommandError("test_command", 1, "test output")),
                         "<CommandError command=<test_command> "
                         "exit_status=1 output=<test output>>")
