"""Opt-in reboot of the VoltBridge."""

from homeassistant.components.button import ButtonEntity
from homeassistant.components.button.const import ButtonDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import DOMAIN
from .coordinator import VoltBridgeConfigEntry, VoltBridgeCoordinator
from .entity import VoltBridgeEntity
from .vendor.mygrid_voltbridge import VoltBridgeError

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoltBridgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Register a reboot button, disabled until the user enables it."""
    async_add_entities([VoltBridgeReboot(entry.runtime_data, "reboot")])


class VoltBridgeReboot(VoltBridgeEntity, ButtonEntity):
    """Send one reboot request; it is never retried."""

    _attr_translation_key = "reboot"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: VoltBridgeCoordinator, key: str) -> None:
        """Initialize the VoltBridgeReboot."""
        super().__init__(coordinator, key)

    async def async_press(self) -> None:
        """Reboot the VoltBridge and show it as unavailable until it answers again."""
        try:
            await self.coordinator.client.async_reboot()
        except VoltBridgeError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="voltbridge_command_failed"
            ) from err
        self.coordinator.async_set_update_error(
            UpdateFailed("VoltBridge reboot requested")
        )
