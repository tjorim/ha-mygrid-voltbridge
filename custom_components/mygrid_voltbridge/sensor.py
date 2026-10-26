"""Power, energy, phase, demand and gas sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from mygrid_voltbridge import TARIFF_NAMES, P1Data, P1Status, PhaseData, Telegram

from .coordinator import VoltBridgeConfigEntry, VoltBridgeCoordinator
from .entity import VoltBridgeEntity

PARALLEL_UPDATES = 0


BREAKER_STATES = {0: "open", 1: "closed", 2: "ready_to_reconnect"}
# DSMR 0-n:24.4.0; the codes are the standard's, checked only against a gas meter reporting 1 (open).
VALVE_STATES = {0: "closed", 1: "open", 2: "ready_to_reconnect"}

type Value = int | float | str | datetime | None
type Attributes = dict[str, Any]


def _history(telegram: Telegram) -> Attributes:
    """Return the monthly peak history."""
    return {
        "history": [
            {
                "month_end": peak.month_end.isoformat(),
                "peak_at": peak.peak_at.isoformat(),
                "power": peak.power,
            }
            for peak in telegram.monthly_peaks
        ]
    }


def _valve_state(kind: str) -> Callable[[Telegram], Value]:
    """Return the valve position of the M-Bus meter of this kind."""

    def value(telegram: Telegram) -> Value:
        channel = telegram.channel_of(kind)
        if channel is None or channel.valve_state is None:
            return None
        return VALVE_STATES.get(channel.valve_state)

    return value


def _last_reading(kind: str) -> Callable[[Telegram], Attributes]:
    """Return the time of the M-Bus meter's last reading, which updates only every minute or two."""

    def attributes(telegram: Telegram) -> Attributes:
        channel = telegram.channel_of(kind)
        if channel is None or channel.reading_at is None:
            return {}
        return {"last_reading": channel.reading_at.isoformat()}

    return attributes


@dataclass(frozen=True, kw_only=True)
class VoltBridgeSensorDescription(SensorEntityDescription):
    """Describe how to read one value from the merged snapshot."""

    value_fn: Callable[[P1Data], Value]
    # Only create the entity when the first snapshot contains a value.
    optional: bool = False
    # Extra state attributes read from the raw telegram.
    attributes_fn: Callable[[Telegram], Attributes] | None = None


def _power(
    key: str,
    value_fn: Callable[[P1Data], Value],
    *,
    optional: bool = False,
    attributes_fn: Callable[[Telegram], Attributes] | None = None,
) -> VoltBridgeSensorDescription:
    return VoltBridgeSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=value_fn,
        optional=optional,
        attributes_fn=attributes_fn,
    )


def _energy(
    key: str, value_fn: Callable[[P1Data], Value]
) -> VoltBridgeSensorDescription:
    return VoltBridgeSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=value_fn,
    )


SENSORS = (
    _power("net_power", lambda d: d.net_power),
    _power("import_power", lambda d: d.import_power),
    _power("export_power", lambda d: d.export_power),
    _energy("energy_import_t1", lambda d: d.energy_import_t1),
    _energy("energy_import_t2", lambda d: d.energy_import_t2),
    _energy("energy_export_t1", lambda d: d.energy_export_t1),
    _energy("energy_export_t2", lambda d: d.energy_export_t2),
    _power("avg_demand", lambda d: d.avg_demand, optional=True),
    _power(
        "peak_demand",
        lambda d: d.peak_demand,
        optional=True,
        attributes_fn=_history,
    ),
    VoltBridgeSensorDescription(
        key="peak_demand_at",
        translation_key="peak_demand_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.peak_demand_at,
        optional=True,
    ),
    VoltBridgeSensorDescription(
        key="tariff",
        translation_key="tariff",
        device_class=SensorDeviceClass.ENUM,
        options=list(TARIFF_NAMES.values()),
        value_fn=lambda d: d.tariff_name,
        optional=True,
    ),
    VoltBridgeSensorDescription(
        key="gas",
        translation_key="gas",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.gas,
        optional=True,
        attributes_fn=_last_reading("gas"),
    ),
)


@dataclass(frozen=True, kw_only=True)
class VoltBridgeTelegramDescription(SensorEntityDescription):
    """A value from the raw telegram; created only if the meter reports it."""

    value_fn: Callable[[Telegram], Value]
    attributes_fn: Callable[[Telegram], Attributes] | None = None


@dataclass(frozen=True, kw_only=True)
class VoltBridgeStatusDescription(SensorEntityDescription):
    """A health value of the device; created only if the meter reports it."""

    value_fn: Callable[[P1Status], Value]


STATUS_SENSORS = (
    VoltBridgeStatusDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.rssi,
    ),
    VoltBridgeStatusDescription(
        key="p1_error_rate",
        translation_key="p1_error_rate",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=lambda s: s.error_percent,
    ),
)

TELEGRAM_SENSORS = (
    VoltBridgeTelegramDescription(
        key="water",
        translation_key="water",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda t: c.reading if (c := t.water) else None,
        attributes_fn=_last_reading("water"),
    ),
    *(
        VoltBridgeTelegramDescription(
            key=f"{kind}_valve",
            translation_key=f"{kind}_valve",
            device_class=SensorDeviceClass.ENUM,
            options=list(VALVE_STATES.values()),
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=_valve_state(kind),
        )
        for kind in ("gas", "water")
    ),
    VoltBridgeTelegramDescription(
        key="breaker",
        translation_key="breaker",
        device_class=SensorDeviceClass.ENUM,
        options=list(BREAKER_STATES.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda t: (
            BREAKER_STATES.get(t.breaker_state) if t.breaker_state is not None else None
        ),
    ),
    VoltBridgeTelegramDescription(
        key="meter_model",
        translation_key="meter_model",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda t: t.meter_model,
    ),
    VoltBridgeTelegramDescription(
        key="dsmr_version",
        translation_key="dsmr_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda t: t.dsmr_version,
    ),
    VoltBridgeTelegramDescription(
        key="limiter_threshold",
        translation_key="limiter_threshold",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda t: t.limiter_threshold,
    ),
    VoltBridgeTelegramDescription(
        key="fuse_threshold",
        translation_key="fuse_threshold",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda t: t.fuse_threshold,
    ),
)


@dataclass(frozen=True, kw_only=True)
class VoltBridgePhaseDescription(SensorEntityDescription):
    """One per-phase value; ``phase`` is 1-3."""

    phase: int
    value_fn: Callable[[PhaseData], int | float | None]


def _phase_descriptions(phase: int) -> tuple[VoltBridgePhaseDescription, ...]:
    suffix = f"_l{phase}"
    return (
        VoltBridgePhaseDescription(
            key=f"voltage{suffix}",
            translation_key="phase_voltage",
            translation_placeholders={"phase": f"L{phase}"},
            phase=phase,
            device_class=SensorDeviceClass.VOLTAGE,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda p: p.voltage,
        ),
        VoltBridgePhaseDescription(
            key=f"current{suffix}",
            translation_key="phase_current",
            translation_placeholders={"phase": f"L{phase}"},
            phase=phase,
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda p: p.current,
        ),
        VoltBridgePhaseDescription(
            key=f"import_power{suffix}",
            translation_key="phase_import_power",
            entity_registry_enabled_default=False,
            translation_placeholders={"phase": f"L{phase}"},
            phase=phase,
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda p: p.import_power,
        ),
        VoltBridgePhaseDescription(
            key=f"export_power{suffix}",
            translation_key="phase_export_power",
            entity_registry_enabled_default=False,
            translation_placeholders={"phase": f"L{phase}"},
            phase=phase,
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda p: p.export_power,
        ),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoltBridgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create entities for what this meter reports in its first snapshot."""
    coordinator = entry.runtime_data
    data = coordinator.data
    entities: list[SensorEntity] = [
        VoltBridgeSensor(coordinator, description)
        for description in SENSORS
        if not description.optional or description.value_fn(data) is not None
    ]
    if (status := coordinator.status) is not None:
        entities.extend(
            VoltBridgeStatusSensor(coordinator, description)
            for description in STATUS_SENSORS
            if description.value_fn(status) is not None
        )
    if (telegram := coordinator.telegram) is not None:
        entities.extend(
            VoltBridgeTelegramSensor(coordinator, description)
            for description in TELEGRAM_SENSORS
            if description.value_fn(telegram) is not None
        )
    for phase in sorted(data.phases):
        entities.extend(
            VoltBridgePhaseSensor(coordinator, description)
            for description in _phase_descriptions(phase)
        )
    async_add_entities(entities)


class VoltBridgeSensor(VoltBridgeEntity, SensorEntity):
    """A value from the merged P1 snapshot."""

    entity_description: VoltBridgeSensorDescription

    def __init__(
        self,
        coordinator: VoltBridgeCoordinator,
        description: VoltBridgeSensorDescription,
    ) -> None:
        """Initialize the VoltBridgeSensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Value:
        """Return the value read from the merged snapshot."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> Attributes | None:
        """Attach what the raw telegram adds: peak history, time of the last gas reading."""
        telegram = self.coordinator.telegram
        attributes_fn = self.entity_description.attributes_fn
        if attributes_fn is None or telegram is None:
            return None
        return attributes_fn(telegram)


class VoltBridgeTelegramSensor(VoltBridgeEntity, SensorEntity):
    """A value read from the raw telegram."""

    entity_description: VoltBridgeTelegramDescription

    def __init__(
        self,
        coordinator: VoltBridgeCoordinator,
        description: VoltBridgeTelegramDescription,
    ) -> None:
        """Initialize the VoltBridgeTelegramSensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Value:
        """Return the value read from the raw telegram, if there is one."""
        telegram = self.coordinator.telegram
        return None if telegram is None else self.entity_description.value_fn(telegram)

    @property
    def extra_state_attributes(self) -> Attributes | None:
        """Attach the time of the last reading to the M-Bus meters."""
        telegram = self.coordinator.telegram
        attributes_fn = self.entity_description.attributes_fn
        if attributes_fn is None or telegram is None:
            return None
        return attributes_fn(telegram)


class VoltBridgeStatusSensor(VoltBridgeEntity, SensorEntity):
    """A health value: Wi-Fi signal, or the share of failed P1 telegrams."""

    entity_description: VoltBridgeStatusDescription

    def __init__(
        self,
        coordinator: VoltBridgeCoordinator,
        description: VoltBridgeStatusDescription,
    ) -> None:
        """Initialize the VoltBridgeStatusSensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Value:
        """Return the value from the device status, if there is one."""
        status = self.coordinator.status
        return None if status is None else self.entity_description.value_fn(status)


class VoltBridgePhaseSensor(VoltBridgeEntity, SensorEntity):
    """A value for one phase; unknown if the meter stops reporting that phase."""

    entity_description: VoltBridgePhaseDescription

    def __init__(
        self,
        coordinator: VoltBridgeCoordinator,
        description: VoltBridgePhaseDescription,
    ) -> None:
        """Initialize the VoltBridgePhaseSensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | float | None:
        """Return the value of this phase, unknown if the meter dropped it."""
        phase = self.coordinator.data.phases.get(self.entity_description.phase)
        return None if phase is None else self.entity_description.value_fn(phase)
