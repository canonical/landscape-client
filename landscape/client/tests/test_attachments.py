from unittest import mock
import tempfile
import os

from twisted.trial.unittest import TestCase
from twisted.internet.defer import ensureDeferred

from landscape import VERSION
from landscape.client.attachments import save_attachments
from landscape.lib.persist import Persist

MODULE = "landscape.client.attachments"


class SaveAttachmentsTest(TestCase):
    """Tests for the `save_attachments` function."""

    def setUp(self):
        super().setUp()

        self.dest = tempfile.mkdtemp()
        self.config = mock.Mock(
            url="https://example.com/",
            data_path=self.dest,
        )

        self.persist = Persist(filename=os.path.join(self.dest, "broker.bpickle"))
        self.persist.set("registration.secure-id", b"1")
        self.persist.save()
        self.fetch_async = mock.patch(MODULE + ".fetch_async", new=mock.AsyncMock()).start()

        self.addCleanup(mock.patch.stopall)

    def test_save_attachments(self):
        """attachments are downloaded and saved to the given destination, using the provided uid
        and gid.
        """
        self.fetch_async.side_effect = [
            b"Contents of attachment 1\n",
            b"Contents of attachment 2\n",
        ]

        deferred = ensureDeferred(save_attachments(
            self.config,
            (("attachment-1.txt", 1), ("attachment-2.txt", 2)),
            self.dest,
            uid=1000,
            gid=1000,
        ))

        headers = {
            "User-Agent": "landscape-client/" + VERSION,
            "Content-Type": "application/octet-stream",
            "X-Computer-ID": "1",
        }

        def check(_):
            self.assertEqual(self.fetch_async.mock_calls, [
                mock.call("https://example.com/attachment/1", cainfo=mock.ANY, headers=headers),
                mock.call("https://example.com/attachment/2", cainfo=mock.ANY, headers=headers),
            ])

            with open(os.path.join(self.dest, "attachment-1.txt")) as a1:
                self.assertEqual("Contents of attachment 1\n", a1.read())

            with open(os.path.join(self.dest, "attachment-2.txt")) as a2:
                self.assertEqual("Contents of attachment 2\n", a2.read())

        deferred.addBoth(check)
        return deferred

    def test_save_attachment_inline(self):
        """A 'legacy' attachment inline in the parameters is simply saved."""
        deferred = ensureDeferred(save_attachments(
            self.config,
            (("attachment-1.txt", "Contents of attachment 1\n"),),
            self.dest,
            uid=1000,
            gid=1000,
        ))

        def check(_):
            self.fetch_async.assert_not_called()

            with open(os.path.join(self.dest, "attachment-1.txt")) as a1:
                self.assertEqual("Contents of attachment 1\n", a1.read())

        deferred.addBoth(check)
        return deferred
