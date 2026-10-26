import asyncio
from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from mygrid_voltbridge import (
    TARIFF_NAMES,
    PhaseData,
    UpdateSource,
    VoltBridgeConnectionError,
    VoltBridgeNoDataError,
    VoltBridgeUnsupportedError,
)
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.mygrid_voltbridge.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .support import (
    SERIAL,
    make_data,
    make_device_info,
    make_status,
    make_telegram,
)


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
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    assert state(hass, "net_power") == "261"
    assert state(hass, "export_power") == "0"
    assert state(hass, "energy_import_t1") == "3673.536"
    assert state(hass, "energy_export_t2") == "0.0"
    assert state(hass, "energy_import") == "8105.988"
    assert state(hass, "energy_export") == "0.0"
    assert state(hass, "avg_import_1min") == "261"
    assert state(hass, "avg_export_1min") == "0"
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
    hass, vb_client, vb_entry, vb_stream
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
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    vb_client.async_get_p1_data.return_value = make_data(
        tariff=2,
        phases={1: PhaseData(1, 0, 230.0, 1.0), 2: PhaseData(2, 0, 231.0, 2.0)},
    )
    await setup(hass, vb_entry)
    assert state(hass, "tariff") == "night"
    assert state(hass, "voltage_l2") == "231.0"


async def test_stream_updates_reach_the_entities(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    vb_stream.push(
        make_data(
            import_power=900,
            net_power=900,
            gas=441.0,
            phases={1: PhaseData(900, 0, 236.0, 3.9)},
        )
    )
    await hass.async_block_till_done()
    assert state(hass, "net_power") == "900"
    assert state(hass, "voltage_l1") == "236.0"
    assert state(hass, "gas") == "441.0"
    assert vb_client.async_get_p1_data.await_count == 1  # the stream does the rest


async def test_stream_follows_the_configured_interval(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    vb_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(vb_entry, options={"poll_interval": 60})
    assert await hass.config_entries.async_setup(vb_entry.entry_id)
    await hass.async_block_till_done()
    assert [(c["poll_interval"], c["offline_after"]) for c in vb_stream.calls] == [
        (60.0, 30)
    ]


async def test_telegram_and_status_poll_beside_the_stream(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    vb_client.async_get_status.return_value = make_status(rssi=-61)
    for _ in range(3):  # a 1 Hz stream must not starve the poll
        vb_stream.push(make_data())
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
        await hass.async_block_till_done()
    assert state(hass, "wifi_signal") == "-79"
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert state(hass, "wifi_signal") == "-61"


async def test_offline_stream_marks_unavailable_then_recovers(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    vb_stream.fail(VoltBridgeConnectionError("down"))
    await hass.async_block_till_done()
    assert state(hass, "net_power") == STATE_UNAVAILABLE
    await asyncio.sleep(0.01)  # background tasks are not awaited by block_till_done
    assert len(vb_stream.calls) == 2  # followed again after the pause
    assert vb_stream.calls[0]["initial"] is vb_entry.runtime_data.data
    assert vb_stream.calls[1]["initial"] is None  # stale after an outage
    vb_stream.push(make_data(net_power=300))
    await asyncio.sleep(0.01)
    await hass.async_block_till_done()
    assert state(hass, "net_power") == "300"


@pytest.mark.parametrize(
    "error", [VoltBridgeConnectionError("x"), VoltBridgeNoDataError("x")]
)
async def test_setup_retries_when_unreachable(
    hass, vb_client, vb_entry, vb_stream, error
) -> None:  # type: ignore[no-untyped-def]
    vb_client.async_get_p1_data.side_effect = error
    vb_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(vb_entry.entry_id)
    assert vb_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_closes_the_stream(hass, vb_client, vb_entry, vb_stream) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    assert vb_stream.closed == 0
    assert await hass.config_entries.async_unload(vb_entry.entry_id)
    await hass.async_block_till_done()
    assert vb_entry.state is ConfigEntryState.NOT_LOADED
    assert vb_stream.closed == 1
    assert vb_client.async_get_p1_data.await_count == 1


async def test_diagnostics_redacts_identifiers(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    result = await async_get_config_entry_diagnostics(hass, vb_entry)
    assert result["entry"]["host"] == "**REDACTED**"
    assert result["data"]["meter_serial"] == "**REDACTED**"
    assert result["data"]["import_power"] == 261
    assert {c["kind"] for c in result["telegram"]["channels"]} == {"gas", "water"}
    assert "objects" not in result["telegram"]
    assert "equipment" not in str(result["telegram"])


async def test_device_registry_and_disabled_defaults(
    hass, vb_client, vb_entry, vb_stream
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


async def test_device_carries_adapter_identity(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    """Firmware and MAC come from the status page; hardware from discovery."""
    vb_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        vb_entry,
        data={**vb_entry.data, "hardware_version": "P1Wifi-rev1"},
    )
    assert await hass.config_entries.async_setup(vb_entry.entry_id)
    await hass.async_block_till_done()
    device = dr.async_get(hass).async_get_device_by_identifier(
        ("mygrid_voltbridge", SERIAL), vb_entry.entry_id
    )
    assert device.sw_version == "app:build-15.6, idf:v6.0.1, date:202609272035"
    assert device.hw_version == "P1Wifi-rev1"
    assert device.serial_number == "90:70:69:d0:2d:80"
    assert (dr.CONNECTION_NETWORK_MAC, "90:70:69:d0:2d:80") in device.connections
    vb_client.async_get_device_info.assert_awaited_once()


async def test_firmware_update_reaches_device_without_reload(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    registry = dr.async_get(hass)
    device = registry.async_get_device_by_identifier(
        ("mygrid_voltbridge", SERIAL), vb_entry.entry_id
    )
    assert device.sw_version == "app:build-15.6, idf:v6.0.1, date:202609272035"
    vb_client.async_get_device_info.return_value = make_device_info(
        build_info="app:build-15.7"
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=1, seconds=1))
    await hass.async_block_till_done()
    assert registry.async_get(device.id).sw_version == "app:build-15.7"
    # A failed read keeps what is known.
    vb_client.async_get_device_info.side_effect = VoltBridgeConnectionError("down")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=2, seconds=2))
    await hass.async_block_till_done()
    assert registry.async_get(device.id).sw_version == "app:build-15.7"


async def test_device_without_status_page(hass, vb_client, vb_entry, vb_stream) -> None:  # type: ignore[no-untyped-def]
    """Setup survives a failing status page; the meter serial still identifies."""
    vb_client.async_get_device_info.side_effect = VoltBridgeConnectionError("down")
    await setup(hass, vb_entry)
    assert vb_entry.state is ConfigEntryState.LOADED
    device = dr.async_get(hass).async_get_device_by_identifier(
        ("mygrid_voltbridge", SERIAL), vb_entry.entry_id
    )
    assert device.sw_version is None
    assert device.serial_number is None
    assert not device.connections


async def test_discovered_mac_wins_over_status_page(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    vb_client.async_get_device_info.return_value = make_device_info(
        mac_address="aa:bb:cc:dd:ee:ff"
    )
    vb_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        vb_entry, data={**vb_entry.data, "mac": "90:70:69:d0:2d:80"}
    )
    assert await hass.config_entries.async_setup(vb_entry.entry_id)
    await hass.async_block_till_done()
    device = dr.async_get(hass).async_get_device_by_identifier(
        ("mygrid_voltbridge", SERIAL), vb_entry.entry_id
    )
    assert device.serial_number == "90:70:69:d0:2d:80"


async def test_meter_identity_sensors(hass, vb_client, vb_entry, vb_stream) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    telegram = make_telegram()
    assert state(hass, "meter_model") == telegram.meter_model
    assert state(hass, "dsmr_version") == telegram.dsmr_version
    assert telegram.meter_model
    assert telegram.dsmr_version


async def test_repair_issue_while_no_p1_data(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    issues = ir.async_get(hass)
    issue_id = f"no_p1_data_{vb_entry.entry_id}"
    assert issues.async_get_issue("mygrid_voltbridge", issue_id) is None
    vb_stream.fail(VoltBridgeNoDataError("none"))
    await hass.async_block_till_done()
    assert issues.async_get_issue("mygrid_voltbridge", issue_id) is not None
    assert state(hass, "net_power") == STATE_UNAVAILABLE
    vb_stream.push(make_data())
    await hass.async_block_till_done()
    assert issues.async_get_issue("mygrid_voltbridge", issue_id) is None
    assert state(hass, "net_power") == "261"


async def test_telegram_sensors(hass, vb_client, vb_entry, vb_stream) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    assert state(hass, "water") == "33.692"
    assert state(hass, "breaker") == "closed"
    assert state(hass, "gas_valve") == "open"
    registry = er.async_get(hass)
    assert (  # the fixture's water meter reports no valve
        registry.async_get_entity_id(
            "sensor", "mygrid_voltbridge", f"{SERIAL}_water_valve"
        )
        is None
    )
    for key, last_reading in (
        ("water", "2026-10-23T19:15:30+00:00"),
        ("gas", "2026-10-23T19:14:09+00:00"),
    ):
        entity_id = registry.async_get_entity_id(
            "sensor", "mygrid_voltbridge", f"{SERIAL}_{key}"
        )
        assert hass.states.get(entity_id).attributes["last_reading"] == last_reading
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


async def test_tariff_options_follow_the_library(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "mygrid_voltbridge", f"{SERIAL}_tariff"
    )
    assert hass.states.get(entity_id).attributes["options"] == list(
        TARIFF_NAMES.values()
    )


async def test_phases_missing_from_the_snapshot_come_from_the_telegram(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    telegram = make_telegram()
    object.__setattr__(
        telegram,
        "phases",
        {1: PhaseData(1, 0, 1.0, 1.0), 2: PhaseData(2, 0, 231.0, 2.5)},
    )
    vb_client.async_get_telegram.return_value = telegram
    await setup(hass, vb_entry)
    assert state(hass, "voltage_l2") == "231.0"
    assert state(hass, "current_l2") == "2.5"
    assert (
        state(hass, "voltage_l1") == "237.3"
    )  # the snapshot wins where it has a phase


async def test_real_limits_create_disabled_diagnostics(
    hass, vb_client, vb_entry, vb_stream
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
    hass, vb_client, vb_entry, vb_stream
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
    hass, vb_client, vb_entry, vb_stream
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


async def test_status_sensors(hass, vb_client, vb_entry, vb_stream) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    assert state(hass, "wifi_signal") == "-79"
    assert state(hass, "p1_error_rate") == "1.0"


async def test_stream_keeps_the_signal_strength_fresh(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    vb_stream.push(make_data(), rssi=-61)
    await hass.async_block_till_done()
    assert state(hass, "wifi_signal") == "-61"
    assert state(hass, "p1_error_rate") == "1.0"  # unchanged until the next poll
    vb_stream.push(
        make_data(net_power=5), UpdateSource.P1DATA
    )  # no signal in an HTTP read
    await hass.async_block_till_done()
    assert state(hass, "wifi_signal") == "-61"


async def test_status_failures_keep_the_last_reading(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    coordinator = vb_entry.runtime_data
    vb_client.async_get_status.side_effect = VoltBridgeConnectionError("flaky")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert state(hass, "net_power") == "261"
    assert coordinator.status is not None
    vb_client.async_get_status.side_effect = VoltBridgeUnsupportedError("404")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=62))
    await hass.async_block_till_done()
    assert coordinator.status is None
    assert state(hass, "wifi_signal") == "unknown"


async def test_no_status_support_skips_those_sensors(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    vb_client.async_get_status.side_effect = VoltBridgeUnsupportedError("404")
    await setup(hass, vb_entry)
    registry = er.async_get(hass)
    for key in ("wifi_signal", "p1_error_rate"):
        assert (
            registry.async_get_entity_id(
                "sensor", "mygrid_voltbridge", f"{SERIAL}_{key}"
            )
            is None
        )
    assert state(hass, "net_power") == "261"


async def test_status_without_values_creates_no_sensors(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    vb_client.async_get_status.return_value = make_status(rssi=None, error_percent=None)
    await setup(hass, vb_entry)
    registry = er.async_get(hass)
    for key in ("wifi_signal", "p1_error_rate"):
        assert (
            registry.async_get_entity_id(
                "sensor", "mygrid_voltbridge", f"{SERIAL}_{key}"
            )
            is None
        )


def reboot_entity(hass: HomeAssistant) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "button", "mygrid_voltbridge", f"{SERIAL}_reboot"
    )
    assert entity_id
    return entity_id


async def test_reboot_button_is_opt_in_and_reboots_once(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    registry = er.async_get(hass)
    entity_id = reboot_entity(hass)
    assert registry.async_get(entity_id).disabled_by is not None  # disabled by default
    registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(vb_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )
    vb_client.async_reboot.assert_awaited_once()
    assert (
        state(hass, "net_power") == STATE_UNAVAILABLE
    )  # until the device answers again


async def test_reboot_failure_is_a_translated_error(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    registry = er.async_get(hass)
    entity_id = reboot_entity(hass)
    registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(vb_entry.entry_id)
    await hass.async_block_till_done()
    vb_client.async_reboot.side_effect = VoltBridgeConnectionError("down")
    with pytest.raises(HomeAssistantError) as raised:
        await hass.services.async_call(
            "button", "press", {"entity_id": entity_id}, blocking=True
        )
    assert raised.value.translation_key == "voltbridge_command_failed"
    assert (
        state(hass, "net_power") == "261"
    )  # a failed command does not take the meter offline


async def test_heap_sensors_are_disabled_diagnostics_refreshed_hourly(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    vb_client.async_get_device_info.return_value = make_device_info(
        free_heap=38000, min_free_heap=768
    )
    await setup(hass, vb_entry)
    registry = er.async_get(hass)
    for key in ("free_heap", "min_free_heap"):
        entity_id = registry.async_get_entity_id(
            "sensor", "mygrid_voltbridge", f"{SERIAL}_{key}"
        )
        assert registry.async_get(entity_id).disabled_by is not None
        registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(vb_entry.entry_id)
    await hass.async_block_till_done()
    assert state(hass, "free_heap") == "38000"
    assert state(hass, "min_free_heap") == "768"
    vb_client.async_get_device_info.return_value = make_device_info(
        free_heap=37000, min_free_heap=512
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=1, seconds=1))
    await hass.async_block_till_done()
    assert state(hass, "free_heap") == "37000"
    assert state(hass, "min_free_heap") == "512"


async def test_no_heap_readings_creates_no_heap_sensors(
    hass, vb_client, vb_entry, vb_stream
) -> None:  # type: ignore[no-untyped-def]
    await setup(hass, vb_entry)
    registry = er.async_get(hass)
    for key in ("free_heap", "min_free_heap"):
        assert (
            registry.async_get_entity_id(
                "sensor", "mygrid_voltbridge", f"{SERIAL}_{key}"
            )
            is None
        )
