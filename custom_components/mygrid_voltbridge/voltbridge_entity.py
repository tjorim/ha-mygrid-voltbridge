"""Common device identity and coordinator subscription."""

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MAC, DOMAIN
from .voltbridge_coordinator import VoltBridgeCoordinator


class VoltBridgeEntity(CoordinatorEntity[VoltBridgeCoordinator]):
    """An entity attached to one VoltBridge, identified by its meter serial."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VoltBridgeCoordinator, key: str) -> None:
        super().__init__(coordinator)
        serial = coordinator.data.meter_serial
        self._attr_unique_id = f"{serial}_{key}"
        entry_data = coordinator.config_entry.data
        mac = entry_data.get(CONF_MAC)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(serial))},
            connections={(CONNECTION_NETWORK_MAC, mac)} if mac else set(),
            configuration_url=f"http://{entry_data[CONF_HOST]}",
            name="MyGrid VoltBridge",
            manufacturer="MyGrid",
            model="VoltBridge P1 meter",
            serial_number=serial,
        )
