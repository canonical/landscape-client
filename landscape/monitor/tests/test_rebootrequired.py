import os

from landscape.monitor.rebootrequired import RebootRequired
from landscape.tests.helpers import (
    LandscapeTest, MonitorHelper, LogKeeperHelper)
from landscape.tests.mocker import ANY


class RebootRequiredTest(LandscapeTest):

    helpers = [MonitorHelper, LogKeeperHelper]

    def setUp(self):
        super(RebootRequiredTest, self).setUp()
        self.reboot_required_filename = self.makeFile("")
        self.plugin = RebootRequired(self.reboot_required_filename)
        self.monitor.add(self.plugin)
        self.mstore.set_accepted_types(["reboot-required"])

    def test_wb_check_reboot_required(self):
        """
        L{RebootRequired.check_reboot_required} should return C{True} if the
        reboot-required flag file is present, C{False} otherwise.
        """
        self.assertTrue(self.plugin._check_reboot_required())
        os.remove(self.reboot_required_filename)
        self.assertFalse(self.plugin._check_reboot_required())

    def test_wb_create_message(self):
        """
        A message should be created if and only if the reboot-required status
        of the system has changed.
        """
        self.assertEquals(self.plugin._create_message(), {"flag": True})
        self.assertEquals(self.plugin._create_message(), {})

    def test_send_message(self):
        """
        A new C{"reboot-required"} message should be enqueued if and only
        if the reboot-required status of the system has changed.
        """
        self.plugin.send_message()
        self.assertIn("Queueing message with updated reboot-required status.",
                      self.logfile.getvalue())
        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "reboot-required", "flag": True}])
        self.mstore.delete_all_messages()
        self.plugin.send_message()
        self.assertMessages(self.mstore.get_pending_messages(), [])

    def test_run(self):
        """
        If the server can accept them, the plugin should send
        C{reboot-required} messages.
        """
        broker_mock = self.mocker.replace(self.remote)
        broker_mock.send_message(ANY, urgent=True)
        self.mocker.replay()
        self.plugin.run()
        self.mstore.set_accepted_types([])
        self.plugin.run()
