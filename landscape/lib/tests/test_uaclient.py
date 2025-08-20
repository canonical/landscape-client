from unittest import TestCase, mock

from landscape.lib.uaclient import get_pro_status, attach_pro, detach_pro


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
