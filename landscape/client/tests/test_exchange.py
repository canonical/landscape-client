"""Tests for the `landscape.client.exchange` utility functions."""
from unittest import TestCase
from unittest import mock

from landscape import SERVER_API
from landscape import VERSION
from landscape.lib import bpickle

from landscape.client.exchange import exchange_messages


class ExchangeMessagesTestCase(TestCase):
    """Tests for the `exchange_messages` function."""

    def setUp(self):
        super().setUp()

        self.fetch_mock = mock.patch("landscape.client.exchange.fetch").start()
        self.logging_mock = mock.patch(
            "landscape.client.exchange.logging"
        ).start()

        self.addCleanup(mock.patch.stopall)

    def test_success(self):
        """A successful exchange results in a response and appropriate
        logging.
        """
        payload = {"messages": [{"type": "my-message-type", "some-value": 5}]}

        mock_response = {
            "server-api": "3.2",
            "server-uuid": b"my-server-uuid",
            "messages": [{"type": "my-server-message-type", "other-value": 6}]
        }

        self.fetch_mock.return_value = bpickle.dumps(mock_response)

        server_response = exchange_messages(
            payload,
            "https://my-server.local/message-system",
            cainfo="mycainfo",
            computer_id="my-secure-id",
            exchange_token=b"my-exchange-token",
        )

        self.assertEqual(server_response.server_api, "3.2")
        self.assertEqual(server_response.server_uuid, b"my-server-uuid")
        self.assertEqual(
            server_response.messages,
            [{"type": "my-server-message-type", "other-value": 6}]
        )
        self.fetch_mock.assert_called_once_with(
            "https://my-server.local/message-system",
            post=True,
            data=bpickle.dumps(payload),
            headers={
                "X-Message-API": SERVER_API.decode(),
                "User-Agent": f"landscape-client/{VERSION}",
                "Content-Type": "application/octet-stream",
                "X-Computer-ID": "my-secure-id",
                "X-Exchange-Token": "my-exchange-token",
            },
            cainfo="mycainfo",
            curl=mock.ANY,
        )
        self.assertEqual(self.logging_mock.debug.call_count, 2)
        self.logging_mock.info.assert_called_once()
        self.logging_mock.exception.assert_not_called()

    def test_fetch_exception(self):
        """If the HTTP `fetch` raises an exception, it is logged and raised."""
        payload = {"messages": [{"type": "my-message-type", "some-value": 6}]}

        self.fetch_mock.side_effect = Exception("OOPS")

        with self.assertRaises(Exception) as exc_context:
            exchange_messages(
                payload,
                "https://my-server.local/message-system"
            )

        self.assertIn("OOPS", str(exc_context.exception))
        self.fetch_mock.assert_called_once()
        self.logging_mock.debug.assert_called_once()
        self.logging_mock.exception.assert_called_once_with(
            "Error contacting the server at https://my-server.local/message"
            "-system."
        )

    def test_bpickle_exception(self):
        """If the deserialization of the server response raises an exception,
        it is logged and raised.
        """
        payload = {"messages": [{"type": "my-message-type", "some-value": 7}]}

        self.fetch_mock.return_value = b"thisisnotbpickled"

        with self.assertRaises(ValueError):
            exchange_messages(
                payload,
                "https://my-server.local/message-system",
            )

        self.fetch_mock.assert_called_once()
        self.logging_mock.debug.assert_called_once()
        self.logging_mock.exception.assert_called_once_with(
            "Server returned invalid data: b'thisisnotbpickled'"
        )
