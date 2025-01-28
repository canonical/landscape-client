import os
import tempfile
from unittest import mock

from twisted.internet.defer import ensureDeferred
from twisted.trial.unittest import TestCase

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

        self.persist = Persist(
            filename=os.path.join(self.dest, "broker.bpickle"),
        )
        self.persist.set("registration.secure-id", b"1")
        self.persist.save()
        self.fetch_async = mock.patch(
            MODULE + ".fetch_async",
            new=mock.AsyncMock(),
        ).start()

        self.uid = os.getuid()
        self.gid = os.getgid()

        self.addCleanup(mock.patch.stopall)

    def test_save_attachments(self):
        """attachments are downloaded and saved to the given destination, using
        the provided uid and gid.
        """
        self.fetch_async.side_effect = [
            b"Contents of attachment 1\n",
            b"Contents of attachment 2\n",
        ]

        deferred = ensureDeferred(
            save_attachments(
                self.config,
                (("attachment-1.txt", 1), ("attachment-2.txt", 2)),
                self.dest,
                uid=self.uid,
                gid=self.gid,
            ),
        )

        headers = {
            "User-Agent": "landscape-client/" + VERSION,
            "Content-Type": "application/octet-stream",
            "X-Computer-ID": "1",
        }

        def check(_):
            self.assertEqual(
                self.fetch_async.mock_calls,
                [
                    mock.call(
                        "https://example.com/attachment/1",
                        cainfo=mock.ANY,
                        headers=headers,
                    ),
                    mock.call(
                        "https://example.com/attachment/2",
                        cainfo=mock.ANY,
                        headers=headers,
                    ),
                ],
            )

            a1 = os.path.join(self.dest, "attachment-1.txt")
            a2 = os.path.join(self.dest, "attachment-2.txt")
            a1_stat = os.stat(a1)
            a2_stat = os.stat(a2)

            self.assertEqual(a1_stat.st_uid, self.uid)
            self.assertEqual(a1_stat.st_gid, self.gid)
            self.assertEqual(a2_stat.st_uid, self.uid)
            self.assertEqual(a2_stat.st_gid, self.gid)

            with open(a1) as a1fp:
                self.assertEqual("Contents of attachment 1\n", a1fp.read())

            with open(a2) as a2fp:
                self.assertEqual("Contents of attachment 2\n", a2fp.read())

        deferred.addBoth(check)
        return deferred

    def test_save_attachment_inline(self):
        """A 'legacy' attachment inline in the parameters is simply saved."""
        deferred = ensureDeferred(
            save_attachments(
                self.config,
                (("attachment-1.txt", "Contents of attachment 1\n"),),
                self.dest,
                uid=self.uid,
                gid=self.gid,
            ),
        )

        def check(_):
            self.fetch_async.assert_not_called()

            a1 = os.path.join(self.dest, "attachment-1.txt")
            a1_stat = os.stat(a1)

            self.assertEqual(a1_stat.st_uid, self.uid)
            self.assertEqual(a1_stat.st_gid, self.gid)

            with open(a1) as a1fp:
                self.assertEqual("Contents of attachment 1\n", a1fp.read())

        deferred.addBoth(check)
        return deferred
