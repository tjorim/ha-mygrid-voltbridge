"""Common device identity and coordinator subscription."""

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_HARDWARE_VERSION, CONF_MAC, DOMAIN
from .coordinator import VoltBridgeCoordinator


class VoltBridgeEntity(CoordinatorEntity[VoltBridgeCoordinator]):
    """An entity attached to one VoltBridge, identified by its meter serial.

    The device is the adapter, so its serial number is the adapter's MAC; the
    meter serial stays in the identifier because it survives replacing the adapter.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: VoltBridgeCoordinator, key: str) -> None:
        """Initialize the VoltBridgeEntity."""
        super().__init__(coordinator)
        serial = coordinator.data.meter_serial
        self._attr_unique_id = f"{serial}_{key}"
        entry_data = coordinator.config_entry.data
        info = coordinator.device_info
        # The MAC from discovery wins; a manually added entry learns it from the status page.
        mac = entry_data.get(CONF_MAC) or (info.mac_address if info else None)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(serial))},
            connections={(CONNECTION_NETWORK_MAC, mac)} if mac else set(),
            configuration_url=f"http://{entry_data[CONF_HOST]}",
            name="MyGrid VoltBridge",
            manufacturer="MyGrid",
            model="VoltBridge P1 meter",
            serial_number=mac,
            sw_version=info.build_info if info else None,
            hw_version=entry_data.get(CONF_HARDWARE_VERSION),
        )
