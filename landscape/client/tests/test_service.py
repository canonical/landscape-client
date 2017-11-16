import logging
import signal

from twisted.internet import reactor
from twisted.internet.task import deferLater

from landscape.lib.testing import FakeReactor
from landscape.client.deployment import Configuration
from landscape.client.service import LandscapeService
from landscape.client.tests.helpers import LandscapeTest


class TestComponent(object):
    name = "monitor"


class TestService(LandscapeService):
    service_name = TestComponent.name


class LandscapeServiceTest(LandscapeTest):

    def setUp(self):
        super(LandscapeServiceTest, self).setUp()
        self.config = Configuration()
        self.config.data_path = self.makeDir()
        self.makeDir(path=self.config.sockets_path)
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
            persist_filename = self.makePersistFile(content="")

        service = PersistService(self.config)
        self.assertEqual(service.persist.filename, service.persist_filename)

    def test_no_persist_without_filename(self):
        """
        If no {persist_filename} attribute is defined, no C{persist} attribute
        will be available.
        """
        service = TestService(self.config)
        self.assertFalse(hasattr(service, "persist"))

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

        def check(ign):
            new_streams = [handler.stream for handler in
                           logging.getLogger().handlers if
                           isinstance(handler, logging.FileHandler)]

            for stream in new_streams:
                self.assertTrue(stream not in original_streams)

        # We need to give some room for the callFromThread to run
        d = deferLater(reactor, 0, lambda: None)
        return d.addCallback(check)

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
