import mock

from landscape.lib.testing import LogKeeperHelper
from landscape.client.monitor.rebootrequired import RebootRequired
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper


class RebootRequiredTest(LandscapeTest):

    helpers = [MonitorHelper, LogKeeperHelper]

    def setUp(self):
        super(RebootRequiredTest, self).setUp()
        self.reboot_required_filename = self.makeFile()
        self.plugin = RebootRequired(self.reboot_required_filename)
        self.monitor.add(self.plugin)
        self.mstore.set_accepted_types(["reboot-required-info"])

    def test_wb_get_flag(self):
        """
        L{RebootRequired._get_flag} returns C{True} if the reboot-required
        flag file is present, C{False} otherwise.
        """
        self.assertFalse(self.plugin._get_flag())
        self.makeFile(path=self.reboot_required_filename, content="")
        self.assertTrue(self.plugin._get_flag())

    def test_wb_get_packages(self):
        """
        L{RebootRequired._get_packages} returns the packages listed in the
        reboot-required packages file if present, or an empty list otherwise.
        """
        self.assertEqual([], self.plugin._get_packages())
        self.makeFile(path=self.reboot_required_filename + ".pkgs",
                      content="foo\nbar\n")
        self.assertEqual(["bar", "foo"], self.plugin._get_packages())

    def test_wb_get_packages_with_duplicates(self):
        """
        The list of packages returned by L{RebootRequired._get_packages} does
        not contain duplicate values.
        """
        self.assertEqual([], self.plugin._get_packages())
        self.makeFile(path=self.reboot_required_filename + ".pkgs",
                      content="foo\nfoo\n")
        self.assertEqual(["foo"], self.plugin._get_packages())

    def test_wb_get_packages_with_blank_lines(self):
        """
        Blank lines are ignored by L{RebootRequired._get_packages}.
        """
        self.assertEqual([], self.plugin._get_packages())
        self.makeFile(path=self.reboot_required_filename + ".pkgs",
                      content="bar\n\nfoo\n")
        self.assertEqual(["bar", "foo"], self.plugin._get_packages())

    def test_wb_create_message(self):
        """
        A message should be created if and only if the reboot-required status
        of the system has changed.
        """
        self.assertEqual({"flag": False, "packages": []},
                         self.plugin._create_message())
        self.makeFile(path=self.reboot_required_filename, content="")
        self.assertEqual({"flag": True},
                         self.plugin._create_message())
        self.makeFile(path=self.reboot_required_filename + ".pkgs",
                      content="foo\n")
        self.assertEqual({"packages": [u"foo"]},
                         self.plugin._create_message())

    def test_send_message(self):
        """
        A new C{"reboot-required-info"} message should be enqueued if and only
        if the reboot-required status of the system has changed.
        """
        self.makeFile(path=self.reboot_required_filename + ".pkgs",
                      content="foo\n")
        self.makeFile(path=self.reboot_required_filename, content="")
        self.plugin.send_message()
        self.assertIn("Queueing message with updated reboot-required status.",
                      self.logfile.getvalue())
        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "reboot-required-info",
                              "flag": True,
                              "packages": [u"foo"]}])
        self.mstore.delete_all_messages()
        self.plugin.send_message()
        self.assertMessages(self.mstore.get_pending_messages(), [])

    def test_run_interval(self):
        """
        The L{RebootRequired} plugin will be scheduled to run every 15 minutes.
        """
        self.assertEqual(900, self.plugin.run_interval)

    def test_run_immediately(self):
        """
        The L{RebootRequired} plugin will be run immediately at startup.
        """
        self.assertTrue(True, self.plugin.run_immediately)

    def test_run(self):
        """
        If the server can accept them, the plugin should send
        C{reboot-required} messages.
        """
        with mock.patch.object(self.remote, "send_message"):
            self.plugin.run()
            self.remote.send_message.assert_called_once_with(
                mock.ANY, mock.ANY, urgent=True)
        self.mstore.set_accepted_types([])
        self.plugin.run()

    def test_resynchronize(self):
        """
        The "resynchronize" reactor message cause the plugin to send fresh
        data.
        """
        self.plugin.run()
        self.reactor.fire("resynchronize", scopes=["package"])
        self.plugin.run()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 2)
