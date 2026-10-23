"""Common device identity and coordinator subscription."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VoltBridgeCoordinator


class VoltBridgeEntity(CoordinatorEntity[VoltBridgeCoordinator]):
    """An entity attached to one VoltBridge, identified by its meter serial."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VoltBridgeCoordinator, key: str) -> None:
        super().__init__(coordinator)
        serial = coordinator.data.meter_serial
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(serial))},
            name="MyGrid VoltBridge",
            manufacturer="MyGrid",
            model="VoltBridge P1 meter",
            serial_number=serial,
        )
