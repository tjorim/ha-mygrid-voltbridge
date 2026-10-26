"""Common device identity and coordinator subscription."""

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_HARDWARE_VERSION, CONF_MAC, DOMAIN
from .coordinator import VoltBridgeCoordinator, mbus_identifier


def adapter_device_info(coordinator: VoltBridgeCoordinator) -> DeviceInfo:
    """Describe the adapter, whose identifier is the electricity meter's serial.

    The device's serial number is the adapter's MAC; the meter serial stays in
    the identifier because it survives replacing the adapter.
    """
    entry_data = coordinator.config_entry.data
    info = coordinator.device_info
    # The MAC from discovery wins; a manually added entry learns it from the status page.
    mac = entry_data.get(CONF_MAC) or (info.mac_address if info else None)
    return DeviceInfo(
        identifiers={(DOMAIN, str(coordinator.data.meter_serial))},
        connections={(CONNECTION_NETWORK_MAC, mac)} if mac else set(),
        configuration_url=f"http://{entry_data[CONF_HOST]}",
        name="MyGrid VoltBridge",
        manufacturer="MyGrid",
        model="VoltBridge P1 meter",
        serial_number=mac,
        sw_version=info.build_info if info else None,
        hw_version=entry_data.get(CONF_HARDWARE_VERSION),
    )


class VoltBridgeEntity(CoordinatorEntity[VoltBridgeCoordinator]):
    """An entity attached to one VoltBridge, identified by its meter serial.

    Gas and water entities (``mbus_kind``) sit on the device of their own M-Bus
    meter, linked to the adapter. Their unique ID stays the same as when they
    were on the adapter, so history and statistics are unaffected.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VoltBridgeCoordinator,
        key: str,
        mbus_kind: str | None = None,
    ) -> None:
        """Initialize the VoltBridgeEntity."""
        super().__init__(coordinator)
        serial = coordinator.data.meter_serial
        self._attr_unique_id = f"{serial}_{key}"
        channel = (
            coordinator.telegram.channel_of(mbus_kind)
            if mbus_kind and coordinator.telegram
            else None
        )
        if channel is None or coordinator.adapter_device_id is None:
            # Without a telegram the meter is unknown: stay on the adapter, and move
            # when the coordinator reloads the entry once the telegram shows it.
            self._attr_device_info = adapter_device_info(coordinator)
            return
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mbus_identifier(serial, channel))},
            translation_key=f"{mbus_kind}_meter",
            # The manufacturer is not in the telegram, and the model is only the kind.
            model=f"M-Bus {mbus_kind} meter",
            serial_number=channel.equipment_id,
            via_device_id=coordinator.adapter_device_id,
        )
