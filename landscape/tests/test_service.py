import logging
import signal

from landscape.service import LandscapeService
from landscape.tests.helpers import LandscapeTest


class LandscapeServiceTest(LandscapeTest):

    def setUp(self):
        super(LandscapeServiceTest, self).setUp()
        signal.signal(signal.SIGUSR1, signal.SIG_DFL)

    def tearDown(self):
        super(LandscapeServiceTest, self).tearDown()
        signal.signal(signal.SIGUSR1, signal.SIG_DFL)

    def test_create_persist(self):
        """
        If a {persist_filename} attribute is defined, a L{Persist} with that
        filename will be created.
        """

        class FakeService(LandscapeService):
            persist_filename = self.makeFile(content="")
            service_name = "monitor"

        service = FakeService(None)
        self.assertEquals(service.persist.filename, service.persist_filename)

    def test_no_persist_without_filename(self):
        """
        If no {persist_filename} attribute is defined, no C{persist} attribute
        will be available.
        """

        class FakeService(LandscapeService):
            service_name = "monitor"

        service = FakeService(None)
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
        LandscapeService(None)
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

        class Configuration:
            ignore_sigusr1 = True

        # Instantiating LandscapeService should not register the
        # handler if we request to ignore it.
        config = Configuration()
        LandscapeService(config)

        handler = signal.getsignal(signal.SIGUSR1)
        self.assertFalse(handler)
