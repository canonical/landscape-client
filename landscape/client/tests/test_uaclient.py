from dataclasses import dataclass
from unittest import TestCase, mock

from landscape.client.environment import IS_CORE, IS_SNAP
from landscape.client.uaclient import (
    ConnectivityException,
    ContractAPIException,
    InvalidTokenException,
    LockHeldException,
    ProManagementError,
    ProNotAttachedError,
    attach_pro,
    detach_pro,
    get_pro_status,
)

if not IS_SNAP and not IS_CORE:
    from uaclient.exceptions import (
        AttachInvalidTokenError,
        ConnectivityError,
        ContractAPIError,
        LockHeldError,
        UbuntuProError,
    )


@dataclass
class FakeIsAttached:
    is_attached: bool


class TestUAClientWrapper(TestCase):
    mock_status_value = {
        "attached": True,
        "contract": {"id": "fake_contract_id"},
        "expires": "fake_expiration_date",
        "services": [
            {
                "available": "yes",
                "entitled": "yes",
                "name": "anbox-cloud",
                "status": "disabled",
            },
            {
                "available": "yes",
                "entitled": "yes",
                "name": "landscape",
                "status": "disabled",
            },
        ],
    }

    @mock.patch("landscape.client.uaclient.status")
    @mock.patch("landscape.client.uaclient.UAConfig")
    def test_get_pro_status(self, mock_uaconfig, mock_status):
        mock_uaconfig.return_value = None
        mock_status.return_value = self.mock_status_value

        pro_status = get_pro_status()

        self.assertEqual(self.mock_status_value, pro_status)

    def test_get_pro_status_no_uaclient(self):
        with mock.patch("landscape.client.uaclient.uaclient", None):
            get_pro_status()

    @mock.patch("landscape.client.uaclient.UAConfig")
    def test_get_pro_status_general_exception(self, mock_uaconfig):
        mock_uaconfig.side_effect = Exception
        result = get_pro_status()
        self.assertEqual({}, result)

    @mock.patch("landscape.client.uaclient.FullTokenAttachOptions")
    @mock.patch("landscape.client.uaclient.full_token_attach")
    def test_attach_pro_normal(self, mock_attach, mock_options):
        mock_options.return_value = None
        mock_attach.return_value = None

        self.assertIsNone(attach_pro("fake-token"))

    @mock.patch("landscape.client.uaclient.FullTokenAttachOptions")
    def test_attach_pro_ubuntu_pro_error(self, mock_options):
        mock_options.side_effect = UbuntuProError

        with self.assertRaises(ProManagementError):
            attach_pro("fake-token")

    def test_attach_pro_no_uaclient(self):
        with mock.patch("landscape.client.uaclient.uaclient", None):
            with self.assertRaises(ProManagementError):
                attach_pro("fake-token")

    @mock.patch("landscape.client.uaclient.FullTokenAttachOptions")
    def test_attach_pro_connectivity_error(self, mock_options):
        mock_options.side_effect = ConnectivityError(cause="cause", url="url")

        with self.assertRaises(ConnectivityException):
            attach_pro("fake-token")

    @mock.patch("landscape.client.uaclient.FullTokenAttachOptions")
    def test_attach_pro_contract_api_error(self, mock_options):
        mock_options.side_effect = ContractAPIError(url="url", code="code", body="body")

        with self.assertRaises(ContractAPIException):
            attach_pro("fake-token")

    @mock.patch("landscape.client.uaclient.FullTokenAttachOptions")
    def test_attach_pro_lock_held_error(self, mock_options):
        mock_options.side_effect = LockHeldError(
            lock_request="request", lock_holder=None, pid=1
        )

        with self.assertRaises(LockHeldException):
            attach_pro("fake-token")

    @mock.patch("landscape.client.uaclient.FullTokenAttachOptions")
    def test_attach_invalid_token_error(self, mock_options):
        mock_options.side_effect = AttachInvalidTokenError

        with self.assertRaises(InvalidTokenException):
            attach_pro("fake-token")

    @mock.patch("landscape.client.uaclient.detach")
    @mock.patch("landscape.client.uaclient.is_attached")
    def test_detach_token(self, mock_is_attached, mock_detach):
        mock_is_attached.return_value = FakeIsAttached(is_attached=True)
        mock_detach.return_value = None

        self.assertIsNone(detach_pro())

    @mock.patch("landscape.client.uaclient.detach")
    @mock.patch("landscape.client.uaclient.is_attached")
    def test_detach_token_ubuntu_pro_error(self, mock_is_attached, mock_detach):
        mock_is_attached.return_value = FakeIsAttached(is_attached=True)
        mock_detach.side_effect = UbuntuProError

        with self.assertRaises(ProManagementError):
            detach_pro()

    def test_detach_pro_no_uaclient(self):
        with mock.patch("landscape.client.uaclient.uaclient", None):
            with self.assertRaises(ProManagementError):
                detach_pro()

    def test_detach_not_attached(self):
        with mock.patch("landscape.client.uaclient.is_attached") as mock_is_attached:
            mock_is_attached.return_value = FakeIsAttached(is_attached=False)
            with self.assertRaises(ProNotAttachedError):
                detach_pro()
