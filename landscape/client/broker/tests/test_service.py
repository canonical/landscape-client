import os
import stat
from unittest.mock import Mock, patch

from landscape.client.broker.amp import RemoteBrokerConnector
from landscape.client.broker.service import BrokerService
from landscape.client.broker.tests.helpers import BrokerConfigurationHelper
from landscape.client.broker.transport import HTTPTransport
from landscape.client.tests.helpers import LandscapeTest
from landscape.lib.testing import FakeReactor


class FakeBrokerService(BrokerService):
    reactor_factory = FakeReactor


class BrokerServiceTest(LandscapeTest):
    helpers = [BrokerConfigurationHelper]

    def setUp(self):
        super().setUp()

        self.service = FakeBrokerService(self.config)

    def test_persist(self):
        """
        A L{BrokerService} instance has a proper C{persist} attribute.
        """
        self.assertEqual(
            self.service.persist.filename,
            os.path.join(self.config.data_path, "broker.bpickle"),
        )

    def test_transport(self):
        """
        A L{BrokerService} instance has a proper C{transport} attribute.
        """
        self.assertTrue(isinstance(self.service.transport, HTTPTransport))
        self.assertEqual(self.service.transport.get_url(), self.config.url)

    def test_message_store(self):
        """
        A L{BrokerService} instance has a proper C{message_store} attribute.
        """
        self.assertEqual(self.service.message_store.get_accepted_types(), ())

    def test_identity(self):
        """
        A L{BrokerService} instance has a proper C{identity} attribute.
        """
        self.assertEqual(self.service.identity.account_name, "some_account")

    def test_pinger(self):
        """
        A L{BrokerService} instance has a proper C{pinger} attribute. Its
        interval value is configured with the C{ping_interval} value.
        """
        self.assertEqual(self.service.pinger.get_url(), self.config.ping_url)
        self.assertEqual(30, self.service.pinger.get_interval())
        self.config.ping_interval = 20
        service = BrokerService(self.config)
        self.assertEqual(20, service.pinger.get_interval())

    def test_registration(self):
        """
        A L{BrokerService} instance has a proper C{registration} attribute.
        """
        self.assertEqual(self.service.registration.should_register(), False)

    def test_start_stop(self):
        """
        The L{BrokerService.startService} method makes the process start
        listening to the broker socket, and starts the L{Exchanger} and
        the L{Pinger} as well.
        """
        self.service.exchanger.start = Mock()
        self.service.pinger.start = Mock()
        self.service.exchanger.stop = Mock()

        self.service.startService()
        reactor = FakeReactor()
        connector = RemoteBrokerConnector(reactor, self.config)
        connected = connector.connect()
        connected.addCallback(lambda remote: remote.get_server_uuid())
        connected.addCallback(lambda x: connector.disconnect())
        connected.addCallback(lambda x: self.service.stopService())

        self.service.exchanger.start.assert_called_with()
        self.service.pinger.start.assert_called_with()
        self.service.exchanger.stop.assert_called_with()

    @patch("landscape.client.broker.service.FILE_MODE", 0o666)
    @patch("landscape.client.broker.service.DIRECTORY_MODE", 0o700)
    def test_sets_correct_permissions_on_files_and_dirs(self):
        FILE_MODE = 0o666
        DIRECTORY_MODE = 0o700

        message_directory = os.path.join(self.config.data_path, "messages")
        dir1 = self.makeDir(dirname=message_directory)
        file1 = self.makeFile(content="hello", dirname=dir1)
        file2 = self.makeFile(content="world", dirname=message_directory)

        os.chmod(message_directory, 0o755)
        os.chmod(dir1, 0o755)
        os.chmod(file1, 0o644)
        os.chmod(file2, 0o644)

        instance = FakeBrokerService(self.config)
        instance.set_message_permissions()

        self.assertEqual(
            stat.S_IMODE(os.stat(message_directory).st_mode), DIRECTORY_MODE
        )
        self.assertEqual(stat.S_IMODE(os.stat(dir1).st_mode), DIRECTORY_MODE)
        self.assertEqual(stat.S_IMODE(os.stat(file1).st_mode), FILE_MODE)
        self.assertEqual(stat.S_IMODE(os.stat(file2).st_mode), FILE_MODE)

    @patch("landscape.client.broker.service.FILE_MODE", 0o666)
    @patch("landscape.client.broker.service.DIRECTORY_MODE", 0o700)
    def test_sets_correct_permissions_on_files_and_dirs_with_symlink(self):
        FILE_MODE = 0o666
        DIRECTORY_MODE = 0o700

        message_directory = os.path.join(self.config.data_path, "messages")
        dir1 = self.makeDir(dirname=message_directory)
        file1 = self.makeFile(content="hello", dirname=dir1)
        # file2 is outside the message directory
        file2 = self.makeFile(content="world", dirname=self.config.data_path)

        symlink_path = os.path.join(message_directory, "link-to-file2")
        os.symlink(file2, symlink_path)

        os.chmod(message_directory, 0o755)
        os.chmod(dir1, 0o755)
        os.chmod(file1, 0o644)
        os.chmod(file2, 0o644)

        instance = FakeBrokerService(self.config)
        instance.set_message_permissions()

        self.assertEqual(
            stat.S_IMODE(os.stat(message_directory).st_mode),
            DIRECTORY_MODE,
        )
        self.assertEqual(
            stat.S_IMODE(os.stat(dir1).st_mode),
            DIRECTORY_MODE,
        )
        self.assertEqual(
            stat.S_IMODE(os.stat(file1).st_mode),
            FILE_MODE,
        )

        self.assertTrue(os.path.islink(symlink_path))
        self.assertEqual(
            os.readlink(symlink_path),
            file2,
        )
        self.assertEqual(
            stat.S_IMODE(os.stat(file2).st_mode),
            0o644,
        )
