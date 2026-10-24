from ipaddress import ip_address
from unittest.mock import AsyncMock

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mygrid_voltbridge.const import DOMAIN
from custom_components.mygrid_voltbridge.vendor.mygrid_voltbridge import (
    VoltBridgeConnectionError,
    VoltBridgeNoDataError,
)

from .flows import start_voltbridge
from .support import SERIAL, make_data

PROPERTIES = {
    "model": "Voltbridge P1 Meter",
    "manufacturer": "MyGrid",
    "device_id": "907069D02D80",
    "api_path": "/api/p1data",
}


def discovery(properties: dict[str, str] = PROPERTIES) -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ip_address("192.168.0.45"),
        ip_addresses=[ip_address("192.168.0.45")],
        port=80,
        hostname="voltbridge-D02D80.local.",
        type="_mygrid._tcp.local.",
        name="voltbridge-D02D80._mygrid._tcp.local.",
        properties=properties,
    )


async def test_user_flow(
    hass: HomeAssistant, vb_client: AsyncMock, vb_setup_entry: None
) -> None:
    result = await start_voltbridge(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": " 192.168.0.45 "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"device": "voltbridge", "host": "192.168.0.45"}
    assert result["result"].unique_id == SERIAL


async def test_user_flow_errors_then_recovers(
    hass: HomeAssistant, vb_client: AsyncMock, vb_setup_entry: None
) -> None:
    result = await start_voltbridge(hass)
    for error, key in (
        (VoltBridgeConnectionError("x"), "voltbridge_cannot_connect"),
        (VoltBridgeNoDataError("x"), "voltbridge_no_data"),
    ):
        vb_client.async_get_p1_data.side_effect = error
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "h"}
        )
        assert result["errors"] == {"base": key}
    vb_client.async_get_p1_data.side_effect = None
    vb_client.async_get_p1_data.return_value = make_data(meter_serial=None)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "h"}
    )
    assert result["errors"] == {"base": "voltbridge_no_data"}
    vb_client.async_get_p1_data.return_value = make_data()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "h"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_duplicate_updates_host(
    hass: HomeAssistant,
    vb_client: AsyncMock,
    vb_entry: MockConfigEntry,
    vb_setup_entry: None,
) -> None:
    vb_entry.add_to_hass(hass)
    result = await start_voltbridge(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "10.0.0.9"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert vb_entry.data["host"] == "10.0.0.9"


async def test_zeroconf_flow(
    hass: HomeAssistant, vb_client: AsyncMock, vb_setup_entry: None
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=discovery()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "device": "voltbridge",
        "host": "192.168.0.45",
        "mac": "90:70:69:d0:2d:80",
    }
    assert result["result"].unique_id == SERIAL


async def test_zeroconf_rejects_other_devices(
    hass: HomeAssistant, vb_client: AsyncMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery(
            {
                "model": "ModuleTwo",
                "manufacturer": "MyGrid",
                "device_id": "489D31B37974",
            }
        ),
    )
    assert result["reason"] == "not_voltbridge"


async def test_zeroconf_unreachable(hass: HomeAssistant, vb_client: AsyncMock) -> None:
    vb_client.async_get_p1_data.side_effect = VoltBridgeNoDataError("x")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=discovery()
    )
    assert result["reason"] == "voltbridge_no_data"


async def test_zeroconf_known_device_updates_host(
    hass: HomeAssistant,
    vb_client: AsyncMock,
    vb_entry: MockConfigEntry,
    vb_setup_entry: None,
) -> None:
    vb_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(vb_entry, data={"host": "10.0.0.9"})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=discovery()
    )
    assert result["reason"] == "already_configured"
    assert vb_entry.data["host"] == "192.168.0.45"


async def test_reconfigure(
    hass: HomeAssistant,
    vb_client: AsyncMock,
    vb_entry: MockConfigEntry,
    vb_setup_entry: None,
) -> None:
    vb_entry.add_to_hass(hass)
    result = await vb_entry.start_reconfigure_flow(hass)
    vb_client.async_get_p1_data.side_effect = VoltBridgeConnectionError("x")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "h"}
    )
    assert result["errors"] == {"base": "voltbridge_cannot_connect"}
    vb_client.async_get_p1_data.side_effect = None
    vb_client.async_get_p1_data.return_value = make_data(meter_serial="OTHER")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "h"}
    )
    assert result["reason"] == "wrong_device"

    result = await vb_entry.start_reconfigure_flow(hass)
    vb_client.async_get_p1_data.return_value = make_data()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "10.0.0.7"}
    )
    assert result["reason"] == "reconfigure_successful"
    assert vb_entry.data["host"] == "10.0.0.7"


async def test_options(
    hass: HomeAssistant, vb_client: AsyncMock, vb_entry: MockConfigEntry, vb_listener
) -> None:  # type: ignore[no-untyped-def]
    vb_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(vb_entry.entry_id)
    result = await hass.config_entries.options.async_init(vb_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"poll_interval": 60}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert vb_entry.options["poll_interval"] == 60


DHCP = DhcpServiceInfo(
    ip="192.168.0.99", hostname="voltbridge-d02d80", macaddress="907069d02d80"
)


async def test_dhcp_updates_known_device(
    hass: HomeAssistant,
    vb_client: AsyncMock,
    vb_entry: MockConfigEntry,
    vb_setup_entry: None,
) -> None:
    vb_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DHCP
    )
    assert result["reason"] == "already_configured"
    assert vb_entry.data["host"] == "192.168.0.99"
    assert vb_entry.data["mac"] == "90:70:69:d0:2d:80"


async def test_dhcp_unreachable(hass: HomeAssistant, vb_client: AsyncMock) -> None:
    vb_client.async_get_p1_data.side_effect = VoltBridgeConnectionError("x")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DHCP
    )
    assert result["reason"] == "voltbridge_cannot_connect"
