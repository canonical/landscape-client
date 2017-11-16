import mock

from landscape.lib.testing import LogKeeperHelper
from landscape.client.monitor.updatemanager import UpdateManager
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper


class UpdateManagerTest(LandscapeTest):
    """
    Tests relating to the L{UpdateManager} monitoring plug-in, which should
    notice changes to update-manager's configuration and report these back to
    landscape server.
    """

    helpers = [MonitorHelper, LogKeeperHelper]

    def setUp(self):
        super(UpdateManagerTest, self).setUp()
        self.update_manager_filename = self.makeFile()
        self.plugin = UpdateManager(self.update_manager_filename)
        self.monitor.add(self.plugin)
        self.mstore.set_accepted_types(["update-manager-info"])

    def test_get_prompt(self):
        """
        L{UpdateManager._get_prompt} returns the value of the
        variable C{Prompt} in the update-manager's configuration.
        """
        content = """
[DEFAULT]
Prompt=lts
"""
        self.makeFile(path=self.update_manager_filename, content=content)
        self.assertEqual("lts", self.plugin._get_prompt())

    def test_get_prompt_with_invalid_value_configured(self):
        """
        L{update_manager._get_prompt} returns "normal" if an invalid value
        is specified in the file.  A warning is also logged.
        """
        content = """
[DEFAULT]
Prompt=zarniwhoop
"""
        self.makeFile(path=self.update_manager_filename, content=content)
        self.assertEqual("normal", self.plugin._get_prompt())

    def test_get_prompt_with_missing_config_file(self):
        """
        When the configuration file does not exist we just return "normal".
        Any machine that doesn't have update-manager installed would fit into
        this category, so there's no need to warn about it.
        """
        self.plugin.update_manager_filename = "/I/Do/Not/Exist"
        self.assertEqual("normal", self.plugin._get_prompt())

    def test_send_message(self):
        """
        A new C{"update-manager-info"} message should be enqueued if and only
        if the update-manager status of the system has changed.
        """
        content = """
[DEFAULT]
Prompt=never
"""
        self.makeFile(path=self.update_manager_filename, content=content)
        self.plugin.send_message()
        self.assertIn("Queueing message with updated update-manager status.",
                      self.logfile.getvalue())
        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "update-manager-info",
                              "prompt": u"never"}])
        self.mstore.delete_all_messages()
        self.plugin.send_message()
        self.assertMessages(self.mstore.get_pending_messages(), [])

    def test_run_interval(self):
        """
        The L{UpdateManager} plugin will be scheduled to run every hour.
        """
        self.assertEqual(3600, self.plugin.run_interval)

    def test_run_immediately(self):
        """
        The L{UpdateManager} plugin will be run immediately at startup.
        """
        self.assertTrue(True, self.plugin.run_immediately)

    def test_run(self):
        """
        If the server can accept them, the plugin should send
        C{update-manager} messages.
        """
        with mock.patch.object(self.remote, "send_message"):
            self.plugin.run()
            self.remote.send_message.assert_called_once_with(
                mock.ANY, mock.ANY)
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
