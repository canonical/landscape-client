import pytest

from .. import uaclient


@pytest.mark.integration
def test_get_pro_status():
    result = uaclient.get_pro_status()

    assert "contract" in result
