from landscape.tests.helpers import LandscapeTest

from landscape.lib.command import run_command, CommandError


class CommandTest(LandscapeTest):

    def setUp(self):
        super(CommandTest, self).setUp()

    def test_basic(self):
        self.assertEquals(run_command("echo test"), "test")

    def test_non_0_exit_status(self):
        self.assertRaises(CommandError, run_command, "false")

    def test_error_str(self):
        self.assertEquals(str(CommandError(1)),
                          "Command exited with status 1")

    def test_error_repr(self):
        self.assertEquals(repr(CommandError(1)),
                          "<CommandError exit_status=1>")
