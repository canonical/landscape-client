from landscape.tests.helpers import LandscapeTest

from landscape.lib.command import run_command, CommandError


class CommandTest(LandscapeTest):

    def setUp(self):
        super(CommandTest, self).setUp()

    def test_basic(self):
        self.assertEquals(run_command("echo test"), "test")

    def test_non_0_exit_status(self):
        try:
            run_command("false")
        except CommandError, error:
            self.assertEquals(error.command, "false")
            self.assertEquals(error.output, "")
            self.assertEquals(error.exit_status, 1)
        else:
            self.fail("CommandError not raised")

    def test_error_str(self):
        self.assertEquals(str(CommandError("test_command", 1, "test output")),
                          "Command 'test_command' exited with status 1 "
                          "(test output)")

    def test_error_repr(self):
        self.assertEquals(repr(CommandError("test_command", 1, "test output")),
                          "<CommandError command=<test_command> "
                          "exit_status=1 output=<test output>>")
