from twisted.internet.defer import succeed, fail

try:
    from imagestore.eucaservice import FakeEucaInfo
except ImportError:
    FakeEucaInfo = None

from landscape.manager.eucalyptus import Eucalyptus, start_service_hub
from landscape.tests.mocker import MockerTestCase, ANY
from landscape.tests.helpers import LandscapeTest, ManagerHelper


fake_version_output = """\
Eucalyptus version: 1.6.2
"""

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
    """A fake version of L{EucalyptusInfo} for use in tests."""

    def __init__(self, version_output=None, walrus_output=None,
                 cluster_controller_output=None,
                 storage_controller_output=None, node_controller_output=None):
        self._version_output = version_output
        self._walrus_output = walrus_output
        self._cluster_controller_output = cluster_controller_output
        self._storage_controller_output = storage_controller_output
        self._node_controller_output = node_controller_output

    def get_version_info(self):
        return succeed(self._version_output)

    def get_walrus_info(self):
        return succeed(self._walrus_output)

    def get_cluster_controller_info(self):
        return succeed(self._cluster_controller_output)

    def get_storage_controller_info(self):
        return succeed(self._storage_controller_output)

    def get_node_controller_info(self):
        return succeed(self._node_controller_output)


class FakeServiceHub(object):

    def __init__(self, result):
        self._result = result
        self.stopped = 0

    def addTask(self, task_handler):
        return self._result

    def stop(self):
        self.stopped += 1


class EucalyptusTest(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super(EucalyptusTest, self).setUp()
        message_type = Eucalyptus.message_type
        error_message_type = Eucalyptus.error_message_type
        self.broker_service.message_store.set_accepted_types(
            [message_type, error_message_type])
        self.service_hub = None

    def get_plugin(self, result=None):
        self.service_hub = FakeServiceHub(result)
        plugin = Eucalyptus(
            service_hub_factory=lambda data_path: self.service_hub,
            eucalyptus_info_factory=lambda tools: FakeEucalyptusInfo(
                fake_version_output, fake_walrus_output,
                fake_cluster_controller_output, fake_storage_controller_output,
                fake_node_controller_output))
        self.manager.add(plugin)
        return plugin

    def test_plugin_registers_with_a_name(self):
        """
        L{Eucalyptus} provides a C{plugin_name}, which is used
        when the plugin is registered with the manager plugin registry.
        """
        plugin = self.get_plugin()
        self.assertIs(plugin, self.manager.get_plugin("eucalyptus-manager"))

    def test_run_interval(self):
        """The L{Eucalyptus} plugin is run every 15 minutes."""
        plugin = self.get_plugin()
        self.assertEqual(900, plugin.run_interval)

    def test_run_with_successful_message(self):
        """
        If credentials are available and no problems occur while retrieving
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
                               "url_for_s3": "http://fake/url",
                               "eucalyptus_version": "1.6.2"},
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

    def test_run_not_accepted_types(self):
        """
        If the C{eucalyptus-info message type is not accepted, the plugin
        doesn't even try to run.
        """
        self.broker_service.message_store.set_accepted_types([])

        def check(ignore):
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [])

        plugin = Eucalyptus(lambda x: 1/0, lambda x: 1/0)
        self.manager.add(plugin)
        deferred = plugin.run()
        deferred.addCallback(check)
        return deferred

    def test_successful_run_stops_service_hub(self):
        """
        The C{ServiceHub} is stopped once data has been retrieved and
        converted into a message to send to the server.
        """
        plugin = self.get_plugin(succeed(FakeEucaInfo()))

        def check(ignore):
            self.assertEqual(1, self.service_hub.stopped)

        deferred = plugin.run()
        deferred.addCallback(check)
        return deferred

    def test_run_with_failure_message(self):
        """
        If a failure occurs while attempting to retrieve information about
        Eucalyptus, such as the C{imagestore} package not being available, an
        error message is sent to the server.
        """

        def check(ignore):
            error_message = (
                "Traceback (failure with no frames): "
                "<type 'exceptions.ZeroDivisionError'>: KABOOM!\n")
            expected = {"type": "eucalyptus-info-error",
                        "error": error_message}
            self.assertMessages(
                self.broker_service.message_store.get_pending_messages(),
                [expected])

        plugin = self.get_plugin(fail(ZeroDivisionError("KABOOM!")))
        deferred = plugin.run()
        deferred.addCallback(check)
        return deferred

    def test_failed_run_stops_service_hub(self):
        """
        The C{ServiceHub} is stopped once data has been retrieved and
        converted into a message to send to the server.
        """
        plugin = self.get_plugin(fail(ZeroDivisionError("KABOOM!")))

        def check(ignore):
            self.assertEqual(1, self.service_hub.stopped)

        deferred = plugin.run()
        deferred.addCallback(check)
        return deferred

    if FakeEucaInfo is None:
        skip_message = "imagestore module not available"
        test_failed_run_stops_service_hub.skip = skip_message
        test_run_with_failure_message.skip = skip_message
        test_run_with_successful_message.skip = skip_message
        test_successful_run_stops_service_hub.skip = skip_message


class EucalyptusWithoutImageStoreTest(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super(EucalyptusWithoutImageStoreTest, self).setUp()
        message_type = Eucalyptus.message_type
        self.broker_service.message_store.set_accepted_types([message_type])
        self.plugin = Eucalyptus(service_hub_factory=lambda x: 1/0)
        self.manager.add(self.plugin)

    def test_plugin_disabled_on_imagestore_import_fail(self):
        """
        When L{Eucalyptus.run} is called it tries to import code
        from the C{imagestore} package.  The plugin disables itself if an
        exception is raised during this process (such as C{ImportError}, for
        example).
        """
        self.assertTrue(self.plugin.enabled)
        self.log_helper.ignore_errors(ZeroDivisionError)
        self.plugin.run()
        self.assertFalse(self.plugin.enabled)


class StartServiceHubTest(MockerTestCase):
    """Tests for L{start_service_hub}."""

    def test_start_service_hub(self):
        """
        L{start_service_hub} creates and starts the L{ServiceHub} used to
        retrieve information about Eucalyptus.
        """
        from twisted.internet import reactor

        euca_service_factory = self.mocker.replace(
            "imagestore.eucaservice.EucaService", passthrough=False)
        service_hub_factory = self.mocker.replace(
            "imagestore.lib.service.ServiceHub", passthrough=False)
        euca_service = object()

        self.expect(
            euca_service_factory(reactor,
                                 "/data/path/eucalyptus")).result(euca_service)
        service_hub = service_hub_factory()
        self.expect(service_hub.addService(euca_service))
        self.expect(service_hub.start())
        self.mocker.replay()
        start_service_hub("/data/path")

    if FakeEucaInfo is None:
        skip_message = "imagestore module not available"
        test_start_service_hub.skip = skip_message
