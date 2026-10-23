"""Fixtures mock the independent client library, not HTTP or UDP."""

from collections.abc import Callable, Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mygrid_voltbridge import (
    BroadcastStream,
    P1Broadcast,
    P1Data,
    PhaseData,
    parse_telegram,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mygrid_voltbridge.const import DOMAIN

SERIAL = "1SAG0000000000"
TELEGRAM_TEXT = (
    (Path(__file__).parent / "fixtures" / "telegram.txt").read_bytes().decode("latin-1")
)


def make_telegram():  # type: ignore[no-untyped-def]
    return parse_telegram(TELEGRAM_TEXT)


def make_data(**overrides: object) -> P1Data:
    values: dict[str, object] = {
        "meter_serial": SERIAL,
        "meter_version": "50217",
        "import_power": 261,
        "export_power": 0,
        "net_power": 261,
        "avg_import_1min": 261,
        "avg_export_1min": 0,
        "avg_demand": 199,
        "peak_demand": 2348,
        "peak_demand_at": datetime(2026, 10, 21, 18, 15, tzinfo=UTC),
        "tariff": 1,
        "energy_import_t1": 3673536,
        "energy_import_t2": 4432452,
        "energy_export_t1": 0,
        "energy_export_t2": 0,
        "gas": 440.448,
        "phases": {1: PhaseData(261, 0, 237.3, 1.7)},
    }
    values.update(overrides)
    return P1Data(**values)  # type: ignore[arg-type]


def make_broadcast(**overrides: object) -> P1Broadcast:
    data = make_data(
        gas=None, avg_import_1min=None, avg_export_1min=None, meter_version="50217"
    )
    for key, value in overrides.items():
        object.__setattr__(data, key, value)
    return P1Broadcast(
        stream=BroadcastStream.P1,
        timestamp=datetime(2026, 10, 23, 18, 51, 22, tzinfo=UTC),
        rssi=-79,
        country="BE",
        software_version="1.0",
        data=data,
    )


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations: None) -> None:
    """Enable the custom integration in the test runtime."""


@pytest.fixture
def client() -> Generator[AsyncMock]:
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
        coordinator_cls.return_value = instance
        yield instance


@pytest.fixture
def listener() -> Generator[Callable[[], Callable[[P1Broadcast], None]]]:
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
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="MyGrid VoltBridge",
        unique_id=SERIAL,
        data={"host": "192.168.0.45"},
    )


@pytest.fixture
def setup_entry() -> Generator[None]:
    """Skip real setup when a flow creates an entry."""
    with patch(
        "custom_components.mygrid_voltbridge.async_setup_entry", return_value=True
    ):
        yield
