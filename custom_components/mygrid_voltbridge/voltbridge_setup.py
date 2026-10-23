"""Entry setup and unload for a VoltBridge P1 meter."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .helpers import async_reload_entry
from .voltbridge_coordinator import VoltBridgeConfigEntry, VoltBridgeCoordinator

VOLTBRIDGE_PLATFORMS = [Platform.SENSOR]


async def async_setup_voltbridge_entry(
    hass: HomeAssistant, entry: VoltBridgeConfigEntry
) -> bool:
    """Read one real snapshot before creating entities, then start push and poll."""
    coordinator = entry.runtime_data = VoltBridgeCoordinator(hass, entry)
    await coordinator.async_start()
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, VOLTBRIDGE_PLATFORMS)
    return True


async def async_unload_voltbridge_entry(
    hass: HomeAssistant, entry: VoltBridgeConfigEntry
) -> bool:
    """Unload entities; the coordinator stops its push and poll on unload."""
    return await hass.config_entries.async_unload_platforms(entry, VOLTBRIDGE_PLATFORMS)
