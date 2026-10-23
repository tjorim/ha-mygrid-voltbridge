"""UI setup, mDNS discovery, reconfiguration and polling options."""

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
    CONF_MAC,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)
from .coordinator import VoltBridgeConfigEntry

HOST_SCHEMA = vol.Schema(
    {vol.Required(CONF_HOST): vol.All(str, vol.Strip, vol.Length(min=1))}
)


class VoltBridgeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Identify each meter by its P1 meter serial, which survives IP changes."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._mac: str | None = None
        self._title = "MyGrid VoltBridge"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: VoltBridgeConfigEntry) -> OptionsFlow:
        return VoltBridgeOptionsFlow()

    async def _serial(self, host: str) -> tuple[str | None, str | None]:
        """Return ``(serial, error)`` after one real read."""
        client = VoltBridgeClient(host, async_get_clientsession(self.hass))
        try:
            data = await client.async_get_p1_data()
        except VoltBridgeNoDataError:
            return None, "no_data"
        except VoltBridgeError:
            return None, "cannot_connect"
        if not data.meter_serial:
            return None, "no_data"
        return data.meter_serial, None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = HOST_SCHEMA(user_input)[CONF_HOST]
            serial, error = await self._serial(host)
            if serial is None:
                errors["base"] = error or "cannot_connect"
            else:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=self._title, data={CONF_HOST: host}
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(HOST_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        try:
            info = VoltBridgeInfo.from_properties(
                cast(
                    Mapping[str | bytes, str | bytes | None], discovery_info.properties
                )
            )
        except VoltBridgeError:
            return self.async_abort(reason="not_voltbridge")
        self.context["title_placeholders"] = {
            "name": discovery_info.hostname.removesuffix(".local.")
        }
        return await self._async_discovered(
            str(discovery_info.ip_address), info.mac_address
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Follow a known device to a new address."""
        mac = ":".join(
            discovery_info.macaddress[i : i + 2] for i in range(0, 12, 2)
        ).lower()
        return await self._async_discovered(discovery_info.ip, mac)

    async def _async_discovered(self, host: str, mac: str) -> ConfigFlowResult:
        serial, error = await self._serial(host)
        if serial is None:
            return self.async_abort(reason=error or "cannot_connect")
        await self.async_set_unique_id(serial)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_MAC: mac})
        self._host, self._mac = host, mac
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._host is not None
        if user_input is not None:
            data = {CONF_HOST: self._host}
            if self._mac:
                data[CONF_MAC] = self._mac
            return self.async_create_entry(title=self._title, data=data)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm", description_placeholders={"host": self._host}
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = HOST_SCHEMA(user_input)[CONF_HOST]
            serial, error = await self._serial(host)
            if serial is None:
                errors["base"] = error or "cannot_connect"
            elif serial != entry.unique_id:
                return self.async_abort(reason="wrong_device")
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host}
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                HOST_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )


class VoltBridgeOptionsFlow(OptionsFlow):
    """How often the HTTP snapshot (gas, totals) is refreshed alongside UDP push."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL),
                    )
                }
            ),
        )
