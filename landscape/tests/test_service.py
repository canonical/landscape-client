import logging
import signal

from landscape.reactor import FakeReactor
from landscape.deployment import Configuration
from landscape.service import LandscapeService
from landscape.amp import (
    ComponentProtocolFactory, RemoteComponentConnector)
from landscape.tests.helpers import LandscapeTest
from landscape.tests.mocker import ANY


class TestComponent(object):
    name = "monitor"


class RemoteTestComponentCreator(RemoteComponentConnector):
    component = TestComponent


class TestService(LandscapeService):
    service_name = TestComponent.name


class LandscapeServiceTest(LandscapeTest):

    def setUp(self):
        super(LandscapeServiceTest, self).setUp()
        self.config = Configuration()
        self.config.data_path = self.makeDir()
        self.reactor = FakeReactor()
        signal.signal(signal.SIGUSR1, signal.SIG_DFL)

    def tearDown(self):
        super(LandscapeServiceTest, self).tearDown()
        signal.signal(signal.SIGUSR1, signal.SIG_DFL)

    def test_create_persist(self):
        """
        If a {persist_filename} attribute is defined, a L{Persist} with that
        filename will be created.
        """

        class PersistService(TestService):
            persist_filename = self.makeFile(content="")

        service = PersistService(self.config)
        self.assertEquals(service.persist.filename, service.persist_filename)

    def test_no_persist_without_filename(self):
        """
        If no {persist_filename} attribute is defined, no C{persist} attribute
        will be available.
        """
        service = TestService(self.config)
        self.assertFalse(hasattr(service, "persist"))

    def test_install_bpickle_dbus(self):
        """
        A L{LandscapeService} installs the DBus extensions of bpickle.
        """
        dbus_mock = self.mocker.replace("landscape.lib.bpickle_dbus.install")
        dbus_mock()
        self.mocker.replay()
        TestService(self.config)

    def test_usr1_rotates_logs(self):
        """
        SIGUSR1 should cause logs to be reopened.
        """
        logging.getLogger().addHandler(logging.FileHandler(self.makeFile()))
        # Store the initial set of handlers
        original_streams = [handler.stream for handler in
                            logging.getLogger().handlers if
                            isinstance(handler, logging.FileHandler)]

        # Instantiating LandscapeService should register the handler
        TestService(self.config)
        # We'll call it directly
        handler = signal.getsignal(signal.SIGUSR1)
        self.assertTrue(handler)
        handler(None, None)
        new_streams = [handler.stream for handler in
                       logging.getLogger().handlers if
                       isinstance(handler, logging.FileHandler)]

        for stream in new_streams:
            self.assertTrue(stream not in original_streams)

    def test_ignore_sigusr1(self):
        """
        SIGUSR1 is ignored if we so request.
        """
        # Instantiating LandscapeService should not register the
        # handler if we request to ignore it.
        self.config.ignore_sigusr1 = True
        TestService(self.config)

        handler = signal.getsignal(signal.SIGUSR1)
        self.assertFalse(handler)

    def test_start_stop_service(self):
        """
        The L{startService} and makes the service start listening on a
        socket for incoming connections.
        """
        service = TestService(self.config)
        service.factory = ComponentProtocolFactory()
        service.startService()
        connector = RemoteTestComponentCreator(self.reactor, self.config)

        def assert_port(ignored):
            self.assertTrue(service.port.connected)
            connector.disconnect()
            service.stopService()

        connected = connector.connect()
        return connected.addCallback(assert_port)

    def test_start_uses_want_pid(self):
        """
        The L{startService} method sets the C{wantPID} flag when listening,
        in order to remove stale socket files from previous runs.
        """
        service = TestService(self.config)
        service.factory = ComponentProtocolFactory(self.reactor, self.config)
        service.reactor._reactor = self.mocker.mock()
        service.reactor._reactor.listenUNIX(ANY, ANY, wantPID=True)
        self.mocker.replay()
        service.startService()
