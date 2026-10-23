"""Diagnostics with identifying fields redacted."""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .vendor.mygrid_voltbridge import Telegram
from .voltbridge_coordinator import VoltBridgeConfigEntry

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
        "telegram": _telegram(coordinator.telegram),
    }


def _telegram(telegram: Telegram | None) -> dict[str, Any] | None:
    """Summarise the telegram without meter or equipment identifiers."""
    if telegram is None:
        return None
    return {
        "crc_valid": telegram.crc_valid,
        "breaker_state": telegram.breaker_state,
        "limiter_threshold": telegram.limiter_threshold,
        "fuse_threshold": telegram.fuse_threshold,
        "channels": [
            {
                "kind": c.kind,
                "reading": c.reading,
                "unit": c.unit,
                "valve_state": c.valve_state,
            }
            for c in telegram.channels.values()
        ],
        "monthly_peak_count": len(telegram.monthly_peaks),
        "obis_codes": sorted(telegram.objects),
    }
