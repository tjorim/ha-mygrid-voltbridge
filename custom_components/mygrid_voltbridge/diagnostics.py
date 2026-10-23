"""Diagnostics with identifying fields redacted."""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import VoltBridgeConfigEntry

TO_REDACT = {CONF_HOST, "meter_serial"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VoltBridgeConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "data": async_redact_data(asdict(coordinator.data), TO_REDACT),
    }
