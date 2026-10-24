"""VoltBridge P1 meter: setup, discovery, reconfiguration and polling options."""

from collections.abc import Mapping
from typing import Any, cast

import probatio as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from mygrid_voltbridge import (
    VoltBridgeClient,
    VoltBridgeError,
    VoltBridgeInfo,
    VoltBridgeNoDataError,
)

from .const import (
    CONF_DEVICE,
    CONF_MAC,
    CONF_POLL_INTERVAL,
    DEVICE_VOLTBRIDGE,
    DOMAIN,
    VOLTBRIDGE_DEFAULT_POLL_INTERVAL,
    VOLTBRIDGE_MAX_POLL_INTERVAL,
    VOLTBRIDGE_MIN_POLL_INTERVAL,
)
from .helpers import interval_schema, normalize_host

VOLTBRIDGE_SCHEMA = vol.Schema({vol.Required(CONF_HOST): normalize_host})


class VoltBridgeFlow(ConfigFlow):
    """Steps that configure one VoltBridge, identified by its P1 meter serial."""

    _host: str | None = None
    _mac: str | None = None

    async def _voltbridge_serial(self, host: str) -> tuple[str | None, str | None]:
        """Return ``(serial, error)`` after one real read."""
        client = VoltBridgeClient(host, async_get_clientsession(self.hass))
        try:
            data = await client.async_get_p1_data()
        except VoltBridgeNoDataError:
            return None, "voltbridge_no_data"
        except VoltBridgeError:
            return None, "voltbridge_cannot_connect"
        if not data.meter_serial:
            return None, "voltbridge_no_data"
        return data.meter_serial, None

    async def async_step_voltbridge(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Identify the meter by its P1 serial, which survives IP changes."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = VOLTBRIDGE_SCHEMA(user_input)[CONF_HOST]
            serial, error = await self._voltbridge_serial(host)
            if serial is None:
                errors["base"] = error or "voltbridge_cannot_connect"
            else:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title="MyGrid VoltBridge",
                    data={CONF_DEVICE: DEVICE_VOLTBRIDGE, CONF_HOST: host},
                )
        return self.async_show_form(
            step_id="voltbridge",
            data_schema=self.add_suggested_values_to_schema(
                VOLTBRIDGE_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Offer a VoltBridge found through its ``_mygrid._tcp`` advertisement."""
        try:
            info = VoltBridgeInfo.from_properties(
                cast(
                    "Mapping[str | bytes, str | bytes | None]",
                    discovery_info.properties,
                )
            )
        except VoltBridgeError:
            return self.async_abort(reason="not_voltbridge")
        self.context["title_placeholders"] = {
            "name": discovery_info.hostname.removesuffix(".local.")
        }
        return await self._async_voltbridge_discovered(
            str(discovery_info.ip_address), info.mac_address
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Follow a known VoltBridge to a new address."""
        mac = ":".join(
            discovery_info.macaddress[i : i + 2] for i in range(0, 12, 2)
        ).lower()
        return await self._async_voltbridge_discovered(discovery_info.ip, mac)

    async def _async_voltbridge_discovered(
        self, host: str, mac: str
    ) -> ConfigFlowResult:
        serial, error = await self._voltbridge_serial(host)
        if serial is None:
            return self.async_abort(reason=error or "voltbridge_cannot_connect")
        await self.async_set_unique_id(serial)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_MAC: mac})
        self._host, self._mac = host, mac
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm setting up a discovered VoltBridge."""
        assert self._host is not None  # noqa: S101 - set by the discovery step
        if user_input is not None:
            data = {CONF_DEVICE: DEVICE_VOLTBRIDGE, CONF_HOST: self._host}
            if self._mac:
                data[CONF_MAC] = self._mac
            return self.async_create_entry(title="MyGrid VoltBridge", data=data)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm", description_placeholders={"host": self._host}
        )

    async def async_step_reconfigure_voltbridge(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address of an existing VoltBridge entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = VOLTBRIDGE_SCHEMA(user_input)[CONF_HOST]
            serial, error = await self._voltbridge_serial(host)
            if serial is None:
                errors["base"] = error or "voltbridge_cannot_connect"
            elif serial != entry.unique_id:
                return self.async_abort(reason="wrong_device")
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host}
                )
        return self.async_show_form(
            step_id="reconfigure_voltbridge",
            data_schema=self.add_suggested_values_to_schema(
                VOLTBRIDGE_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )


class VoltBridgeOptionsFlow(OptionsFlow):
    """Set how often the HTTP snapshot is refreshed alongside UDP push."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start at the VoltBridge-specific step so it has its own text."""
        return await self.async_step_voltbridge_init(user_input)

    async def async_step_voltbridge_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage polling frequency."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="voltbridge_init",
            data_schema=interval_schema(
                self.config_entry.options.get(
                    CONF_POLL_INTERVAL, VOLTBRIDGE_DEFAULT_POLL_INTERVAL
                ),
                VOLTBRIDGE_MIN_POLL_INTERVAL,
                VOLTBRIDGE_MAX_POLL_INTERVAL,
            ),
        )


class MyGridConfigFlow(VoltBridgeFlow, domain=DOMAIN):
    """Configure one VoltBridge per entry."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        """Return the polling options handler."""
        return VoltBridgeOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Go straight to the meter form; this package supports one device."""
        return await self.async_step_voltbridge(user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure the meter address."""
        return await self.async_step_reconfigure_voltbridge(user_input)
