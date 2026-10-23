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

from mygrid_voltbridge import P1Data, PhaseData

from .coordinator import VoltBridgeConfigEntry, VoltBridgeCoordinator
from .entity import VoltBridgeEntity

PARALLEL_UPDATES = 0
TARIFFS = {1: "day", 2: "night"}

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
