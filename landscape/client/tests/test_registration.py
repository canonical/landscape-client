"""Unit tests for registration utility functions."""
from unittest import mock, TestCase

from landscape.lib.fetch import HTTPCodeError
from landscape.lib.fetch import PyCurlError

from landscape.client.exchange import ServerResponse
from landscape.client.registration import (
    ClientRegistrationInfo,
    RegistrationException,
    register,
)


class RegisterTestCase(TestCase):
    """Tests for the `register` function."""

    def setUp(self):
        super().setUp()

        self.exchange_messages_mock = mock.patch(
            "landscape.client.registration.exchange_messages"
        ).start()

        self.addCleanup(mock.patch.stopall)

    def test_success(self):
        """A successful registration call results in a `RegistationInfo`
        object.
        """
        client_info = ClientRegistrationInfo(
            access_group="",
            account_name="testy",
            computer_title="Test Computer",
        )

        self.exchange_messages_mock.return_value = ServerResponse(
            "3.2",
            b"thisisaserveruuid",
            [{"type": "set-id", "id": "mysecureid", "insecure-id": 1}],
        )
        registration_info = register(
            client_info,
            "https://my-server.local/message-system",
        )

        self.assertEqual(registration_info.insecure_id, 1)
        self.assertEqual(registration_info.secure_id, "mysecureid")
        self.assertEqual(registration_info.server_uuid, b"thisisaserveruuid")

    def test_exchange_http_code_error_404(self):
        """If a 404 is raised during the message exchange, a
        `RegistrationException` is raised.
        """
        client_info = ClientRegistrationInfo(
            access_group="",
            account_name="testy",
            computer_title="Test Computer",
        )

        self.exchange_messages_mock.side_effect = HTTPCodeError(
            http_code=404,
            body=""
        )

        with self.assertRaises(RegistrationException):
            register(client_info, "https://my-server.local/message-system")

    def test_exchange_http_code_error_non_404(self):
        """If a non-404 is raised during the message exchange, it is re-raised.
        """
        client_info = ClientRegistrationInfo(
            access_group="",
            account_name="testy",
            computer_title="Test Computer",
        )

        self.exchange_messages_mock.side_effect = HTTPCodeError(
            http_code=400,
            body=""
        )

        with self.assertRaises(HTTPCodeError):
            register(client_info, "https://my-server.local/message-system")

    def test_exchange_pycurl_error_ssl(self):
        """If a pycurl SSL exception is raised during the message exchange, a
        `RegistrationException` is raised.
        """
        client_info = ClientRegistrationInfo(
            access_group="",
            account_name="testy",
            computer_title="Test Computer",
        )

        self.exchange_messages_mock.side_effect = PyCurlError(
            error_code=60,
            message=""
        )

        with self.assertRaises(RegistrationException):
            register(client_info, "https://my-server.local/message-system")

    def test_exchange_pycurl_error_non_ssl(self):
        """If a pycurl non-SSL exception is raised during the message exchange,
        it is re-raised.
        """
        client_info = ClientRegistrationInfo(
            access_group="",
            account_name="testy",
            computer_title="Test Computer",
        )

        self.exchange_messages_mock.side_effect = PyCurlError(
            error_code=61,
            message=""
        )

        with self.assertRaises(PyCurlError):
            register(client_info, "https://my-server.local/message-system")

    def test_no_messages(self):
        """If there are no messages in the server's response, a
        `RegistrationException` is raised.
        """
        client_info = ClientRegistrationInfo(
            access_group="",
            account_name="testy",
            computer_title="Test Computer",
        )

        self.exchange_messages_mock.return_value = ServerResponse(
            "3.2",
            server_uuid=b"thisisaserveruuid",
            messages=[],
        )

        with self.assertRaises(RegistrationException) as exc_context:
            register(client_info, "https://my-server.local/message-system")

        self.assertIn("No messages", str(exc_context.exception))

    def test_no_set_id_message(self):
        """If there's no 'set-id' message in the server's response, a
        `RegistrationException` is raised.
        """
        client_info = ClientRegistrationInfo(
            access_group="",
            account_name="testy",
            computer_title="Test Computer",
        )

        self.exchange_messages_mock.return_value = ServerResponse(
            "3.2",
            server_uuid=b"thisisaserveruuid",
            messages=[{"type": "unknown-message-type"}],
        )

        with self.assertRaises(RegistrationException) as exc_context:
            register(client_info, "https://my-server.local/message-system")

        self.assertIn("Did not receive ID", str(exc_context.exception))
