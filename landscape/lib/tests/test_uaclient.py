from unittest import TestCase, mock

from landscape.lib.uaclient import AttachProError, attach_pro, get_pro_status

from landscape.client import IS_CORE
from landscape.client import IS_SNAP

if not IS_SNAP and not IS_CORE:
    from uaclient.exceptions import (
        ConnectivityError,
        ContractAPIError,
        LockHeldError,
        UbuntuProError,
    )


class TestUAClientWrapper(TestCase):

    mock_status_value = {
        "attached": True,
        "contract": {
            "id": "fake_contract_id"
        },
        "expires": "fake_expiration_date",
        "services": [
            {
                "available": "yes",
                "entitled": "yes",
                "name": "anbox-cloud",
                "status": "disabled"
            },
            {
                "available": "yes",
                "entitled": "yes",
                "name": "landscape",
                "status": "disabled"
            }
        ]
    }

    @mock.patch("landscape.lib.uaclient.status")
    @mock.patch("landscape.lib.uaclient.UAConfig")
    def test_get_pro_status(self, mock_uaconfig, mock_status):
        mock_uaconfig.return_value = None
        mock_status.return_value = self.mock_status_value

        pro_status = get_pro_status()

        self.assertEqual(self.mock_status_value, pro_status)

    @mock.patch("landscape.lib.uaclient.UAConfig")
    def test_get_pro_status_name_error(self, mock_uaconfig):
        mock_uaconfig.side_effect = NameError
        result = get_pro_status()
        self.assertEqual({}, result)

    @mock.patch("landscape.lib.uaclient.UAConfig")
    def test_get_pro_status_general_exception(self, mock_uaconfig):
        mock_uaconfig.side_effect = Exception
        result = get_pro_status()
        self.assertEqual({}, result)

    @mock.patch("landscape.lib.uaclient.FullTokenAttachOptions")
    @mock.patch("landscape.lib.uaclient.full_token_attach")
    async def test_attach_pro_normal(self, mock_attach, mock_options):
        mock_options.return_value = None
        mock_attach.return_value = None
        
        await self.assertIsNone(attach_pro("fake-token"))

    @mock.patch("landscape.lib.uaclient.FullTokenAttachOptions")
    async def test_attach_pro_name_error(self, mock_options):
        mock_options.side_effect = NameError

        with self.assertRaises(AttachProError):
            await attach_pro("fake-token")

    @mock.patch("landscape.lib.uaclient.FullTokenAttachOptions")
    async def test_attach_pro_ubuntu_pro_error(self, mock_options):
        mock_options.side_effect = UbuntuProError

        with self.assertRaises(AttachProError):
            await attach_pro("fake-token")

    @mock.patch("landscape.lib.uaclient.FullTokenAttachOptions")
    async def test_attach_pro_connectivity_error(self, mock_options):
        mock_options.side_effect = ConnectivityError

        with self.assertRaises(AttachProError):
            await attach_pro("fake-token")

    @mock.patch("landscape.lib.uaclient.FullTokenAttachOptions")
    async def test_attach_pro_contract_api_error(self, mock_options):
        mock_options.side_effect = ContractAPIError

        with self.assertRaises(AttachProError):
            await attach_pro("fake-token")

    @mock.patch("landscape.lib.uaclient.FullTokenAttachOptions")
    async def test_attach_pro_lock_held_error(self, mock_options):
        mock_options.side_effect = LockHeldError

        with self.assertRaises(LockHeldException):
            await attach_pro("fake-token")
