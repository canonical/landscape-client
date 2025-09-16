from ... import uaclient


def test_get_pro_status():
    result = uaclient.get_pro_status()

    assert "contract" in result
