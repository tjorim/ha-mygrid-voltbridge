"""Power, energy, phase, demand and gas sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .vendor.mygrid_voltbridge import P1Data, PhaseData, Telegram
from .voltbridge_coordinator import VoltBridgeConfigEntry, VoltBridgeCoordinator
from .voltbridge_entity import VoltBridgeEntity

TARIFFS = {1: "day", 2: "night"}
BREAKER_STATES = {0: "open", 1: "closed", 2: "ready_to_reconnect"}
# The meter reports 999.9 kW / 999 A when no limiter or fuse supervision is set.
NO_LIMIT_W = 999_900
NO_LIMIT_A = 999

type Value = int | float | str | datetime | None


@dataclass(frozen=True, kw_only=True)
class VoltBridgeSensorDescription(SensorEntityDescription):
    """Describe how to read one value from the merged snapshot."""

    value_fn: Callable[[P1Data], Value]
    # Only create the entity when the first snapshot contains a value.
    optional: bool = False


def _power(
    key: str, value_fn: Callable[[P1Data], Value], *, optional: bool = False
) -> VoltBridgeSensorDescription:
    return VoltBridgeSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=value_fn,
        optional=optional,
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
    _power("peak_demand", lambda d: d.peak_demand, optional=True),
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
        options=list(TARIFFS.values()),
        value_fn=lambda d: TARIFFS.get(d.tariff) if d.tariff is not None else None,
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
    ),
)


@dataclass(frozen=True, kw_only=True)
class VoltBridgeTelegramDescription(SensorEntityDescription):
    """A value from the raw telegram; created only if the meter reports it."""

    value_fn: Callable[[Telegram], Value]


TELEGRAM_SENSORS = (
    VoltBridgeTelegramDescription(
        key="water",
        translation_key="water",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda t: c.reading if (c := t.channel_of("water")) else None,
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
        key="limiter_threshold",
        translation_key="limiter_threshold",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda t: (
            t.limiter_threshold
            if t.limiter_threshold is not None and t.limiter_threshold < NO_LIMIT_W
            else None
        ),
    ),
    VoltBridgeTelegramDescription(
        key="fuse_threshold",
        translation_key="fuse_threshold",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda t: (
            t.fuse_threshold
            if t.fuse_threshold is not None and t.fuse_threshold < NO_LIMIT_A
            else None
        ),
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
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Value:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, list[dict[str, str | int]]] | None:
        """Attach the monthly peak history to the peak demand sensor."""
        telegram = self.coordinator.telegram
        if self.entity_description.key != "peak_demand" or telegram is None:
            return None
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


class VoltBridgeTelegramSensor(VoltBridgeEntity, SensorEntity):
    """A value read from the raw telegram."""

    entity_description: VoltBridgeTelegramDescription

    def __init__(
        self,
        coordinator: VoltBridgeCoordinator,
        description: VoltBridgeTelegramDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Value:
        telegram = self.coordinator.telegram
        return None if telegram is None else self.entity_description.value_fn(telegram)


class VoltBridgePhaseSensor(VoltBridgeEntity, SensorEntity):
    """A value for one phase; unknown if the meter stops reporting that phase."""

    entity_description: VoltBridgePhaseDescription

    def __init__(
        self,
        coordinator: VoltBridgeCoordinator,
        description: VoltBridgePhaseDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | float | None:
        phase = self.coordinator.data.phases.get(self.entity_description.phase)
        return None if phase is None else self.entity_description.value_fn(phase)
