from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.mygrid_voltbridge.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.mygrid_voltbridge.vendor.mygrid_voltbridge import (
    BroadcastStream,
    PhaseData,
    VoltBridgeConnectionError,
    VoltBridgeNoDataError,
    VoltBridgeUnsupportedError,
)

from .voltbridge_support import SERIAL, make_broadcast, make_data, make_telegram


def state(hass: HomeAssistant, key: str) -> str | None:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "mygrid_voltbridge", f"{SERIAL}_{key}"
    )
    assert entity_id, key
    found = hass.states.get(entity_id)
    return None if found is None else found.state


async def setup(hass: HomeAssistant, vb_entry: MockConfigEntry) -> None:
    vb_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(vb_entry.entry_id)
    await hass.async_block_till_done()


async def test_entities_from_first_snapshot(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
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
    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id(
            "sensor", "mygrid_voltbridge", f"{SERIAL}_voltage_l2"
        )
        is None
    )


async def test_optional_sensors_skipped_when_unreported(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    vb_client.async_get_p1_data.return_value = make_data(
        gas=None, tariff=None, avg_demand=None, peak_demand=None, peak_demand_at=None
    )
    await setup(hass, vb_entry)
    registry = er.async_get(hass)
    for key in ("gas", "tariff", "avg_demand", "peak_demand", "peak_demand_at"):
        assert (
            registry.async_get_entity_id(
                "sensor", "mygrid_voltbridge", f"{SERIAL}_{key}"
            )
            is None
        )


async def test_night_tariff_and_second_phase(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    vb_client.async_get_p1_data.return_value = make_data(
        tariff=2,
        phases={1: PhaseData(1, 0, 230.0, 1.0), 2: PhaseData(2, 0, 231.0, 2.0)},
    )
    await setup(hass, vb_entry)
    assert state(hass, "tariff") == "night"
    assert state(hass, "voltage_l2") == "231.0"


async def test_push_updates_live_values_but_keeps_gas(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    vb_listener()(
        make_broadcast(
            import_power=900, net_power=900, phases={1: PhaseData(900, 0, 236.0, 3.9)}
        )
    )
    await hass.async_block_till_done()
    assert state(hass, "net_power") == "900"
    assert state(hass, "voltage_l1") == "236.0"
    assert state(hass, "gas") == "440.448"
    assert vb_client.async_get_p1_data.await_count == 1


async def test_push_from_other_meter_or_stream_ignored(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    vb_listener()(make_broadcast(meter_serial="SOMEONE-ELSE", net_power=5))
    aggregated = make_broadcast(net_power=6)
    object.__setattr__(aggregated, "stream", BroadcastStream.AGGREGATED)
    vb_listener()(aggregated)
    await hass.async_block_till_done()
    assert state(hass, "net_power") == "261"


async def test_push_before_first_refresh_is_ignored(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    coordinator = vb_entry.runtime_data
    coordinator.data = None
    coordinator._handle_broadcast(make_broadcast())  # no snapshot to merge into


async def test_polling_continues_despite_push(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    vb_client.async_get_p1_data.return_value = make_data(gas=441.0)
    for _ in range(3):  # a 1 Hz stream must not starve the poll
        vb_listener()(make_broadcast())
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
        await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert state(hass, "gas") == "441.0"


async def test_poll_failure_marks_unavailable_then_recovers(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    vb_client.async_get_p1_data.side_effect = VoltBridgeConnectionError("down")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert state(hass, "net_power") == STATE_UNAVAILABLE
    vb_client.async_get_p1_data.side_effect = None
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=62))
    await hass.async_block_till_done()
    assert state(hass, "net_power") == "261"


@pytest.mark.parametrize(
    "error", [VoltBridgeConnectionError("x"), VoltBridgeNoDataError("x")]
)
async def test_setup_retries_when_unreachable(
    hass, vb_client, vb_entry, vb_listener, error
) -> None:  # type: ignore[no-untyped-def]
    vb_client.async_get_p1_data.side_effect = error
    vb_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(vb_entry.entry_id)
    assert vb_entry.state is ConfigEntryState.SETUP_RETRY


async def test_polling_only_when_udp_unavailable(
    hass, vb_client, vb_entry, caplog
) -> None:  # type: ignore[no-untyped-def]
    from unittest.mock import patch

    with patch(
        "custom_components.mygrid_voltbridge.voltbridge_coordinator.async_listen",
        new_callable=AsyncMock,
        side_effect=OSError("in use"),
    ):
        await setup(hass, vb_entry)
    assert vb_entry.state is ConfigEntryState.LOADED
    assert "polling only" in caplog.text


async def test_unload_stops_push_and_poll(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    assert await hass.config_entries.async_unload(vb_entry.entry_id)
    assert vb_entry.state is ConfigEntryState.NOT_LOADED
    assert vb_client.async_get_p1_data.await_count == 1


async def test_diagnostics_redacts_identifiers(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    result = await async_get_config_entry_diagnostics(hass, vb_entry)
    assert result["entry"]["host"] == "**REDACTED**"
    assert result["data"]["meter_serial"] == "**REDACTED**"
    assert result["data"]["import_power"] == 261
    assert {c["kind"] for c in result["telegram"]["channels"]} == {"gas", "water"}
    assert "objects" not in result["telegram"] and "equipment" not in str(
        result["telegram"]
    )


async def test_device_registry_and_disabled_defaults(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    vb_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        vb_entry,
        data={
            "device": "voltbridge",
            "host": "192.168.0.45",
            "mac": "90:70:69:d0:2d:80",
        },
    )
    assert await hass.config_entries.async_setup(vb_entry.entry_id)
    await hass.async_block_till_done()
    device = dr.async_get(hass).async_get_device_by_identifier(
        ("mygrid_voltbridge", SERIAL), vb_entry.entry_id
    )
    assert device is not None
    assert device.configuration_url == "http://192.168.0.45"
    assert (dr.CONNECTION_NETWORK_MAC, "90:70:69:d0:2d:80") in device.connections
    registry = er.async_get(hass)
    for key, disabled in (
        ("import_power_l1", True),
        ("export_power_l1", True),
        ("voltage_l1", False),
        ("net_power", False),
    ):
        entity_id = registry.async_get_entity_id(
            "sensor", "mygrid_voltbridge", f"{SERIAL}_{key}"
        )
        assert (registry.async_get(entity_id).disabled_by is not None) is disabled, key


async def test_repair_issue_while_no_p1_data(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    issues = ir.async_get(hass)
    issue_id = f"no_p1_data_{vb_entry.entry_id}"
    assert issues.async_get_issue("mygrid_voltbridge", issue_id) is None
    vb_client.async_get_p1_data.side_effect = VoltBridgeNoDataError("none")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert issues.async_get_issue("mygrid_voltbridge", issue_id) is not None
    vb_client.async_get_p1_data.side_effect = None
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=62))
    await hass.async_block_till_done()
    assert issues.async_get_issue("mygrid_voltbridge", issue_id) is None


async def test_telegram_sensors(hass, vb_client, vb_entry, vb_listener) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    assert state(hass, "water") == "33.692"
    assert state(hass, "breaker") == "closed"
    registry = er.async_get(hass)
    for key in (
        "limiter_threshold",
        "fuse_threshold",
    ):  # 999.9 kW / 999 A mean "no limit"
        assert (
            registry.async_get_entity_id(
                "sensor", "mygrid_voltbridge", f"{SERIAL}_{key}"
            )
            is None
        )
    entity_id = registry.async_get_entity_id(
        "sensor", "mygrid_voltbridge", f"{SERIAL}_peak_demand"
    )
    history = hass.states.get(entity_id).attributes["history"]
    assert [item["power"] for item in history] == [2780, 3576, 2811]
    assert history[0]["peak_at"] == "2026-07-19T14:15:00+00:00"


async def test_real_limits_create_disabled_diagnostics(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    telegram = make_telegram()
    object.__setattr__(telegram, "limiter_threshold", 5750)
    object.__setattr__(telegram, "fuse_threshold", 25)
    vb_client.async_get_telegram.return_value = telegram
    await setup(hass, vb_entry)
    registry = er.async_get(hass)
    for key in ("limiter_threshold", "fuse_threshold"):
        entity_id = registry.async_get_entity_id(
            "sensor", "mygrid_voltbridge", f"{SERIAL}_{key}"
        )
        assert registry.async_get(entity_id).disabled_by is not None


async def test_telegram_failures_never_break_the_snapshot(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    coordinator = vb_entry.runtime_data
    vb_client.async_get_telegram.side_effect = VoltBridgeConnectionError("flaky")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert state(hass, "net_power") == "261"  # snapshot still available
    assert coordinator.telegram is not None  # last good telegram kept
    assert state(hass, "water") == "33.692"
    vb_client.async_get_telegram.side_effect = VoltBridgeUnsupportedError("404")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=62))
    await hass.async_block_till_done()
    assert coordinator.telegram is None
    assert state(hass, "water") == "unknown"


async def test_no_telegram_support_skips_those_sensors(
    hass, vb_client, vb_entry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    vb_client.async_get_telegram.side_effect = VoltBridgeUnsupportedError("404")
    await setup(hass, vb_entry)
    registry = er.async_get(hass)
    for key in ("water", "breaker"):
        assert (
            registry.async_get_entity_id(
                "sensor", "mygrid_voltbridge", f"{SERIAL}_{key}"
            )
            is None
        )
    assert state(hass, "net_power") == "261"
