from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from mygrid_voltbridge import (
    BroadcastStream,
    PhaseData,
    VoltBridgeConnectionError,
    VoltBridgeNoDataError,
)
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.mygrid_voltbridge.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import SERIAL, make_broadcast, make_data


def state(hass: HomeAssistant, key: str) -> str | None:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "mygrid_voltbridge", f"{SERIAL}_{key}"
    )
    assert entity_id, key
    found = hass.states.get(entity_id)
    return None if found is None else found.state


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_entities_from_first_snapshot(hass, client, entry, listener) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, entry)
    assert state(hass, "net_power") == "261"
    assert state(hass, "export_power") == "0"
    assert state(hass, "energy_import_t1") == "3673.536"
    assert state(hass, "energy_export_t2") == "0.0"
    assert state(hass, "gas") == "440.448"
    assert state(hass, "tariff") == "day"
    assert state(hass, "peak_demand") == "2348"
    assert state(hass, "peak_demand_at") == "2026-10-21T18:15:00+00:00"
    assert state(hass, "voltage_l1") == "237.3"
    assert state(hass, "current_l1") == "1.7"
    assert state(hass, "import_power_l1") == "261"
    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id(
            "sensor", "mygrid_voltbridge", f"{SERIAL}_voltage_l2"
        )
        is None
    )


async def test_optional_sensors_skipped_when_unreported(
    hass, client, entry, listener
) -> None:  # type: ignore[no-untyped-def]
    client.async_get_p1_data.return_value = make_data(
        gas=None, tariff=None, avg_demand=None, peak_demand=None, peak_demand_at=None
    )
    await setup(hass, entry)
    registry = er.async_get(hass)
    for key in ("gas", "tariff", "avg_demand", "peak_demand", "peak_demand_at"):
        assert (
            registry.async_get_entity_id(
                "sensor", "mygrid_voltbridge", f"{SERIAL}_{key}"
            )
            is None
        )


async def test_night_tariff_and_second_phase(hass, client, entry, listener) -> None:  # type: ignore[no-untyped-def]
    client.async_get_p1_data.return_value = make_data(
        tariff=2,
        phases={1: PhaseData(1, 0, 230.0, 1.0), 2: PhaseData(2, 0, 231.0, 2.0)},
    )
    await setup(hass, entry)
    assert state(hass, "tariff") == "night"
    assert state(hass, "voltage_l2") == "231.0"


async def test_push_updates_live_values_but_keeps_gas(
    hass, client, entry, listener
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, entry)
    listener()(
        make_broadcast(
            import_power=900, net_power=900, phases={1: PhaseData(900, 0, 236.0, 3.9)}
        )
    )
    await hass.async_block_till_done()
    assert state(hass, "net_power") == "900"
    assert state(hass, "voltage_l1") == "236.0"
    assert state(hass, "gas") == "440.448"
    assert client.async_get_p1_data.await_count == 1


async def test_push_from_other_meter_or_stream_ignored(
    hass, client, entry, listener
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, entry)
    listener()(make_broadcast(meter_serial="SOMEONE-ELSE", net_power=5))
    aggregated = make_broadcast(net_power=6)
    object.__setattr__(aggregated, "stream", BroadcastStream.AGGREGATED)
    listener()(aggregated)
    await hass.async_block_till_done()
    assert state(hass, "net_power") == "261"


async def test_push_before_first_refresh_is_ignored(
    hass, client, entry, listener
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, entry)
    coordinator = entry.runtime_data
    coordinator.data = None
    coordinator._handle_broadcast(make_broadcast())  # no snapshot to merge into


async def test_polling_continues_despite_push(hass, client, entry, listener) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, entry)
    client.async_get_p1_data.return_value = make_data(gas=441.0)
    for _ in range(3):  # a 1 Hz stream must not starve the poll
        listener()(make_broadcast())
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
        await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert state(hass, "gas") == "441.0"


async def test_poll_failure_marks_unavailable_then_recovers(
    hass, client, entry, listener
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, entry)
    client.async_get_p1_data.side_effect = VoltBridgeConnectionError("down")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert state(hass, "net_power") == STATE_UNAVAILABLE
    client.async_get_p1_data.side_effect = None
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=62))
    await hass.async_block_till_done()
    assert state(hass, "net_power") == "261"


@pytest.mark.parametrize(
    "error", [VoltBridgeConnectionError("x"), VoltBridgeNoDataError("x")]
)
async def test_setup_retries_when_unreachable(
    hass, client, entry, listener, error
) -> None:  # type: ignore[no-untyped-def]
    client.async_get_p1_data.side_effect = error
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_polling_only_when_udp_unavailable(hass, client, entry, caplog) -> None:  # type: ignore[no-untyped-def]
    from unittest.mock import patch

    with patch(
        "custom_components.mygrid_voltbridge.coordinator.async_listen",
        new_callable=AsyncMock,
        side_effect=OSError("in use"),
    ):
        await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert "polling only" in caplog.text


async def test_unload_stops_push_and_poll(hass, client, entry, listener) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert client.async_get_p1_data.await_count == 1


async def test_diagnostics_redacts_identifiers(hass, client, entry, listener) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, entry)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["entry"]["host"] == "**REDACTED**"
    assert result["data"]["meter_serial"] == "**REDACTED**"
    assert result["data"]["import_power"] == 261
