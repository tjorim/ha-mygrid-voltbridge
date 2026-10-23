"""Re-export this device's fixtures and enable the custom integration."""

import pytest

from .voltbridge_fixtures import vb_client, vb_entry, vb_listener, vb_setup_entry  # noqa: F401


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Enable the generated custom integration in the test runtime."""
