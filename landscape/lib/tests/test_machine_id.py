import os
import unittest
import uuid
from unittest import mock

from landscape.lib import testing
from landscape.lib.machine_id import get_namespaced_machine_id
from landscape.lib.machine_id import LANDSCAPE_CLIENT_APP_UUID
from landscape.lib.machine_id import MACHINE_ID_SIZE


class NameSpacedMachineIdTest(testing.FSTestCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.machine_id = "61f88a7a-d8aa-4a4a-9046-975e5884"
        self.assertEqual(MACHINE_ID_SIZE, len(self.machine_id))
        self.machine_id_file = self.makeFile(content=self.machine_id)

        mock.patch(
            "landscape.lib.machine_id.MACHINE_ID_FILE",
            self.machine_id_file,
        ).start()

        self.addCleanup(mock.patch.stopall)

    def test_get_namespaced_machine_id(self):
        expected = uuid.uuid5(LANDSCAPE_CLIENT_APP_UUID, self.machine_id)
        self.assertEqual(expected, get_namespaced_machine_id())

    def test_empty_file(self):
        empty_file = self.makeFile(content="")

        with mock.patch(
            "landscape.lib.machine_id.MACHINE_ID_FILE",
            empty_file,
        ):
            found = get_namespaced_machine_id()

        self.assertIsNone(found)

    def test_missing_file(self):
        some_file = self.makeFile(content="this message will self-destruct")
        os.unlink(some_file)

        with mock.patch("landscape.lib.machine_id.MACHINE_ID_FILE", some_file):
            found = get_namespaced_machine_id()

        self.assertIsNone(found)

    def test_contents_truncated(self):
        too_long_machine_id = self.machine_id + "0123456789abcdef"
        self.assertEqual(
            self.machine_id,
            too_long_machine_id[:MACHINE_ID_SIZE],
        )
        big_machine_id_file = self.makeFile(content=too_long_machine_id)

        with mock.patch(
            "landscape.lib.machine_id.MACHINE_ID_FILE",
            big_machine_id_file,
        ):
            found = get_namespaced_machine_id()

        expected = uuid.uuid5(LANDSCAPE_CLIENT_APP_UUID, self.machine_id)
        self.assertEqual(expected, found)
