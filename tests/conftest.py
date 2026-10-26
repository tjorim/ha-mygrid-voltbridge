"""VoltBridge fixtures mock the independent client library, not HTTP or UDP."""

from collections.abc import Callable, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mygrid_voltbridge import P1Broadcast
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mygrid_voltbridge.const import DOMAIN

from .support import SERIAL, make_data, make_device_info, make_status, make_telegram


@pytest.fixture
def vb_client() -> Generator[AsyncMock]:
    with (
        patch(
            "custom_components.mygrid_voltbridge.coordinator.VoltBridgeClient"
        ) as coordinator_cls,
        patch(
            "custom_components.mygrid_voltbridge.config_flow.VoltBridgeClient",
            coordinator_cls,
        ),
    ):
        instance = AsyncMock()
        instance.async_get_p1_data.return_value = make_data()
        instance.async_get_telegram.return_value = make_telegram()
        instance.async_get_status.return_value = make_status()
        instance.async_get_device_info.return_value = make_device_info()
        coordinator_cls.return_value = instance
        yield instance


@pytest.fixture
def vb_listener() -> Generator[Callable[[], Callable[[P1Broadcast], None]]]:
    """Patch ``async_listen``; the returned getter yields the registered callback."""
    transport = MagicMock()
    with patch(
        "custom_components.mygrid_voltbridge.coordinator.async_listen",
        new_callable=AsyncMock,
        return_value=transport,
    ) as listen:
        listen.transport = transport
        yield lambda: listen.call_args.args[0]


@pytest.fixture
def vb_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="MyGrid VoltBridge",
        unique_id=SERIAL,
        data={"device": "voltbridge", "host": "192.168.0.45"},
    )


@pytest.fixture
def vb_setup_entry() -> Generator[None]:
    """Skip real setup when a flow creates an entry."""
    with patch(
        "custom_components.mygrid_voltbridge.async_setup_entry", return_value=True
    ):
        yield


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Enable the custom integration in the test runtime."""
