from landscape.manager.eucalyptus import EucalyptusCloudManager
from landscape.tests.helpers import LandscapeTest, ManagerHelper


class EucalyptusCloudManagerTest(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super(EucalyptusCloudManagerTest, self).setUp()
        message_type = EucalyptusCloudManager.message_type
        self.broker_service.message_store.set_accepted_types([message_type])
        self.plugin = EucalyptusCloudManager()
        self.manager.add(self.plugin)

    def test_plugin_registers_with_a_name(self):
        """
        L{EucalyptusCloudManager} provides a C{plugin_name}, which is used
        when the plugin is registered with the manager plugin registry.
        """
        plugin_name = self.plugin.plugin_name
        self.assertIs(self.plugin, self.manager.get_plugin(plugin_name))

    def test_wb_plugin_deregisters_on_imagestore_import_fail(self):
        """
        When L{EucalyptusCloudManager.run} is called it tries to import code
        from the C{imagestore} package.  The plugin disables itself if an
        exception is raised during this process.
        """
        plugin_name = self.plugin.plugin_name
        self.assertIs(self.plugin, self.manager.get_plugin(plugin_name))
        self.plugin._start_service_hub = lambda: 1/0
        self.plugin.run()
        self.assertRaises(KeyError, self.manager.get_plugin, plugin_name)
