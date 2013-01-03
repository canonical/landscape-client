from landscape.monitor.updatemanager import UpdateManager
from landscape.tests.helpers import (
    LandscapeTest, MonitorHelper, LogKeeperHelper)
from landscape.tests.mocker import ANY


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
        L{UpdateManager.get_prompt} returns the value of the
        variable C{Prompt} in the update-manager's configuration.
        """
        content = """
[DEFAULT]
Prompt=lts
"""
        self.makeFile(path=self.update_manager_filename, content=content)
        self.assertEqual("lts", self.plugin._get_prompt())
