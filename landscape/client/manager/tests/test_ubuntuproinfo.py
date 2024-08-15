import json
import os
import tempfile
from datetime import datetime
from unittest import mock

from landscape.client.manager.ubuntuproinfo import get_ubuntu_pro_info
from landscape.client.manager.ubuntuproinfo import UbuntuProInfo
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import ManagerHelper


class UbuntuProInfoTest(LandscapeTest):
    """Ubuntu Pro info plugin tests."""

    helpers = [ManagerHelper]

    def setUp(self):
        super().setUp()
        self.mstore = self.broker_service.message_store
        self.mstore.set_accepted_types(["ubuntu-pro-info"])

    def test_ubuntu_pro_info(self):
        """Tests calling `ua status`."""
        plugin = UbuntuProInfo()

        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                stdout='"This is a test"',
            )
            self.manager.add(plugin)
            plugin.run()

        run_mock.assert_called()
        messages = self.mstore.get_pending_messages()
        self.assertTrue(len(messages) > 0)
        self.assertTrue("ubuntu-pro-info" in messages[0])
        self.assertEqual(messages[0]["ubuntu-pro-info"], '"This is a test"')

    def test_ubuntu_pro_info_no_pro(self):
        """Tests calling `pro status` when it is not installed."""
        plugin = UbuntuProInfo()
        self.manager.add(plugin)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.side_effect = FileNotFoundError()
            plugin.run()

        messages = self.mstore.get_pending_messages()
        run_mock.assert_called_once()
        self.assertTrue(len(messages) > 0)
        self.assertTrue("ubuntu-pro-info" in messages[0])
        self.assertIn("errors", messages[0]["ubuntu-pro-info"])

    def test_get_ubuntu_pro_info_core(self):
        """In Ubuntu Core, there is no pro info, so mock the minimum necessary
        parameters to register with Server.
        """
        with mock.patch(
            "landscape.client.manager.ubuntuproinfo.IS_CORE",
            new="1",
        ):
            ubuntu_pro_info = get_ubuntu_pro_info()

        def datetime_is_aware(d):
            """https://docs.python.org/3/library/datetime.html#determining-if-an-object-is-aware-or-naive"""  # noqa
            return d.tzinfo is not None and d.tzinfo.utcoffset(d) is not None

        self.assertIn("effective", ubuntu_pro_info)
        self.assertIn("expires", ubuntu_pro_info)
        contract = ubuntu_pro_info["contract"]
        self.assertIn("landscape", contract["products"])

        expires = datetime.fromisoformat(ubuntu_pro_info["expires"])
        effective = datetime.fromisoformat(ubuntu_pro_info["effective"])
        self.assertTrue(datetime_is_aware(expires))
        self.assertTrue(datetime_is_aware(effective))

    def test_persistence_unchanged_data(self):
        """If data hasn't changed, a new message is not sent"""
        plugin = UbuntuProInfo()
        self.manager.add(plugin)
        data = '"Initial data!"'

        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                stdout=data,
            )
            plugin.run()

        messages = self.mstore.get_pending_messages()
        run_mock.assert_called_once()
        self.assertEqual(1, len(messages))
        self.assertTrue("ubuntu-pro-info" in messages[0])
        self.assertEqual(messages[0]["ubuntu-pro-info"], data)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                stdout=data,
            )
            plugin.run()

        run_mock.assert_called_once()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(1, len(messages))

    def test_persistence_changed_data(self):
        """New data will be sent in a new message in the queue"""
        plugin = UbuntuProInfo()
        self.manager.add(plugin)

        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                stdout='"Initial data!"',
            )
            plugin.run()

        messages = self.mstore.get_pending_messages()
        run_mock.assert_called_once()
        self.assertEqual(1, len(messages))
        self.assertTrue("ubuntu-pro-info" in messages[0])
        self.assertEqual(messages[0]["ubuntu-pro-info"], '"Initial data!"')

        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                stdout='"New data!"',
            )
            plugin.run()

        run_mock.assert_called_once()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(2, len(messages))
        self.assertEqual(messages[1]["ubuntu-pro-info"], '"New data!"')

    def test_persistence_reset(self):
        """Resetting the plugin will allow a message with identical data to
        be sent"""
        plugin = UbuntuProInfo()
        self.manager.add(plugin)
        data = '"Initial data!"'

        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                stdout=data,
            )
            plugin.run()

        messages = self.mstore.get_pending_messages()
        run_mock.assert_called_once()
        self.assertEqual(1, len(messages))
        self.assertTrue("ubuntu-pro-info" in messages[0])
        self.assertEqual(messages[0]["ubuntu-pro-info"], data)

        plugin._reset()

        with mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                stdout=data,
            )
            plugin.run()

        run_mock.assert_called_once()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(2, len(messages))
        self.assertTrue("ubuntu-pro-info" in messages[1])
        self.assertEqual(messages[1]["ubuntu-pro-info"], data)

    @mock.patch.multiple(
        "landscape.client.manager.ubuntuproinfo",
        IS_SNAP=True,
        UA_DATA_DIR=tempfile.gettempdir(),
    )
    def test_pro_status_file_read_for_snap(self):
        """The snap should read the status file instead of calling `pro`."""
        temp_file_path = os.path.join(tempfile.gettempdir(), "status.json")
        with open(temp_file_path, "w") as fp:
            mocked_info = {
                "_schema_version": "0.1",
                "account": {
                    "created_at": "2024-01-08T13:26:52+00:00",
                    "external_account_ids": [],
                    "id": "zYxWvU_sRqPoNmLkJiHgFeDcBa9876543210ZyXwVuTsRqPon",
                    "name": "jane.doe@example.com",
                },
                "foo": "bar"
            }
            json.dump(mocked_info, fp)

        ubuntu_pro_info = get_ubuntu_pro_info()
        del mocked_info["foo"]
        self.assertEqual(mocked_info, ubuntu_pro_info)

        os.remove(temp_file_path)

    @mock.patch.multiple(
        "landscape.client.manager.ubuntuproinfo",
        IS_SNAP=True,
        UA_DATA_DIR="/i/do/not/exist",
    )
    def test_pro_status_file_not_found_for_snap(self):
        """The snap will return {} if the status file is not found."""
        ubuntu_pro_info = get_ubuntu_pro_info()
        self.assertEqual({}, ubuntu_pro_info)

    def test_mock_info_sent_for_core_snap(self):
        """
        Ensure that a Core snap still receives mocked ubuntu pro info even if
        the snap generally doesn't support *real* ubuntu pro info
        """
        with mock.patch.multiple(
            "landscape.client.manager.ubuntuproinfo",
            IS_CORE=True,
            IS_SNAP=True,
        ):
            ubuntu_pro_info = get_ubuntu_pro_info()

        self.assertIn("effective", ubuntu_pro_info)
        self.assertIn("expires", ubuntu_pro_info)
        contract = ubuntu_pro_info["contract"]
        self.assertIn("landscape", contract["products"])
