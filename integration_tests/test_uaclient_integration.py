"""
Integration tests for uaclient (Ubuntu Pro) interaction.

These are not run when unit tests are run. They are ignored by the unit
testrunner, twisted.trial, because they are pytest tests.
"""
import os

import pytest

from landscape.lib import uaclient


@pytest.mark.integration
def test_attach_status_detach_pro():
    """
    Attaches a pro token, checks the status, detaches it, then checks the
    status again.
    """
    token = os.environ.get("TEST_PRO_TOKEN")

    assert token is not None

    uaclient.attach_pro(token)

    pro_status = uaclient.get_pro_status()

    assert "contract" in pro_status
    contract = pro_status["contract"]

    assert "products" in contract
    products = contract["products"]

    assert "free" in products

    uaclient.detach_pro()

    pro_status = uaclient.get_pro_status()

    assert "contract" in pro_status
    contract = pro_status["contract"]

    assert "products" in contract
    products = contract["products"]

    assert products == []
