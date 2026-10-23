"""Helpers shared by both device families."""

import ipaddress
from typing import Any

import probatio as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import CONF_DEVICE, CONF_POLL_INTERVAL, DEVICE_MODULETWO


def device_type(entry: ConfigEntry[Any]) -> str:
    """Return the device family of an entry; entries without one are ModuleTwo."""
    return str(entry.data.get(CONF_DEVICE, DEVICE_MODULETWO))


@callback
def normalize_host(value: str) -> str:
    """Normalize hostname spelling and equivalent IPv4/IPv6 literals."""
    host = value.strip().rstrip(".").lower()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        if (
            not host
            or any(char.isspace() for char in host)
            or any(char in host for char in "/:@[]")
        ):
            msg = "Enter a hostname or IP address"
            raise vol.Invalid(msg) from None
        return host


def interval_schema(current: int, minimum: int, maximum: int) -> vol.Schema:
    """Return the schema of the polling-interval option."""
    return vol.Schema(
        {
            vol.Required(CONF_POLL_INTERVAL, default=current): vol.All(
                vol.Coerce(int), vol.Range(min=minimum, max=maximum)
            )
        }
    )


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry[Any]) -> None:
    """Apply changed options through a clean reload."""
    await hass.config_entries.async_reload(entry.entry_id)
