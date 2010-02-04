from twisted.internet.defer import succeed

from imagestore.eucaservice import FakeEucaInfo

from landscape.manager.eucalyptus import EucalyptusCloudManager
from landscape.tests.helpers import LandscapeTest, ManagerHelper


fake_walrus_output = """\
registered walruses:
  walrus 10.0.1.113
"""

fake_cluster_controller_output = """\
registered clusters:
  dynamite 10.0.1.113
"""

fake_storage_controller_output = """\
registered storage controllers:
  dynamite 10.0.1.113
"""

fake_node_controller_output = """\
registered nodes:
  10.1.1.71  canyonedge   i-2DC5056F i-5DE5176D
  10.1.1.72  canyonedge
  10.1.1.73  canyonedge
  10.1.1.74  canyonedge
  10.1.1.75  canyonedge
"""

class FakeEucalyptusInfo(object):

    def __init__(self, walrus_output=None, cluster_controller_output=None,
                 storage_controller_output=None, node_controller_output=None):
        self._walrus_output = walrus_output
        self._cluster_controller_output = cluster_controller_output
        self._storage_controller_output = storage_controller_output
        self._node_controller_output = node_controller_output

    def get_walrus_info(self):
        return self._walrus_output

    def get_cluster_controller_info(self):
        return self._cluster_controller_output

    def get_storage_controller_info(self):
        return self._storage_controller_output

    def get_node_controller_info(self):
        return self._node_controller_output


class FakeServiceHub(object):

    def __init__(self, result):
        self._result = result
        self.stopped = 0

    def addTask(self, task_handler):
        return self._result

    def stop(self):
        self.stopped += 1


class EucalyptusCloudManagerTest(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super(EucalyptusCloudManagerTest, self).setUp()
        message_type = EucalyptusCloudManager.message_type
        self.broker_service.message_store.set_accepted_types([message_type])

    def get_plugin(self, result=None):
        plugin = EucalyptusCloudManager(
            service_hub_factory=lambda data_path: FakeServiceHub(result),
            eucalyptus_info_factory=lambda tools: FakeEucalyptusInfo(
                fake_walrus_output, fake_cluster_controller_output,
                fake_storage_controller_output, fake_node_controller_output))
        self.manager.add(plugin)
        return plugin

    def test_plugin_registers_with_a_name(self):
        """
        L{EucalyptusCloudManager} provides a C{plugin_name}, which is used
        when the plugin is registered with the manager plugin registry.
        """
        plugin = self.get_plugin()
        self.assertIs(plugin, self.manager.get_plugin(plugin.plugin_name))

    def test_run_with_successful_message(self):
        """
        If credentials are available and on problems occur while retrieving
        information from C{euca_conf}, a message with information about
        Eucalyptus is queued.
        """
        def check(ignore):
            expected = {
                "type": "eucalyptus-info",
                "basic_info": {"access_key": "AcCeSsKeY123",
                               "certificate_path": "/fake/path",
                               "cloud_certificate_path": "/fake/path",
                               "private_key_path": "/fake/path",
                               "secret_key": None,
                               "url_for_ec2": "http://fake/url",
                               "url_for_s3": "http://fake/url"},
                "cluster_controller_info": fake_cluster_controller_output,
                "node_controller_info": fake_node_controller_output,
                "storage_controller_info": fake_storage_controller_output,
                "walrus_info": fake_walrus_output}
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [expected])

        plugin = self.get_plugin(succeed(FakeEucaInfo()))
        deferred = plugin.run()
        deferred.addCallback(check)
        return deferred


class EucalyptusCloudManagerWithoutImageStoreTest(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super(EucalyptusCloudManagerWithoutImageStoreTest, self).setUp()
        message_type = EucalyptusCloudManager.message_type
        self.broker_service.message_store.set_accepted_types([message_type])

    def test_plugin_deregisters_on_imagestore_import_fail(self):
        """
        When L{EucalyptusCloudManager.run} is called it tries to import code
        from the C{imagestore} package.  The plugin disables itself if an
        exception is raised during this process (such as C{ImportError}, for
        example).
        """
        plugin = EucalyptusCloudManager(service_hub_factory=lambda: 1/0)
        self.manager.add(plugin)
        self.assertIs(plugin, self.manager.get_plugin(plugin.plugin_name))
        plugin.run()
        self.assertRaises(KeyError, self.manager.get_plugin,
                          plugin.plugin_name)
