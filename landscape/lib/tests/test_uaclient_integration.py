"""
Integration tests for uaclient (Ubuntu Pro) interaction.

These are not run when unit tests are run. They are ignored by the unit
testrunner, twisted.trial, because they are pytest tests.
"""
import pytest

from .. import uaclient


@pytest.mark.integration
def test_get_pro_status():
    result = uaclient.get_pro_status()

    assert "contract" in result
