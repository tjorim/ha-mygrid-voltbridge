"""MyGrid VoltBridge P1 meter: local push over UDP with HTTP polling."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import VoltBridgeConfigEntry, VoltBridgeCoordinator
from .entity import adapter_device_info
from .helpers import async_reload_entry

VOLTBRIDGE_PLATFORMS = [Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: VoltBridgeConfigEntry) -> bool:
    """Read one real snapshot before creating entities, then start push and poll."""
    coordinator = entry.runtime_data = VoltBridgeCoordinator(hass, entry)
    await coordinator.async_start()
    # The M-Bus meters point at the adapter, so it has to exist before the entities.
    coordinator.adapter_device_id = (
        dr.async_get(hass)
        .async_get_or_create(
            config_entry_id=entry.entry_id, **adapter_device_info(coordinator)
        )
        .id
    )
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, VOLTBRIDGE_PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VoltBridgeConfigEntry) -> bool:
    """Unload entities; the coordinator stops its push and poll on unload."""
    return await hass.config_entries.async_unload_platforms(entry, VOLTBRIDGE_PLATFORMS)


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
