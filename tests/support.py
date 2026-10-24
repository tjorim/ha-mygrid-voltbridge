"""Builders for VoltBridge readings; the fixtures mock the library, not HTTP or UDP."""

from datetime import UTC, datetime
from pathlib import Path

from custom_components.mygrid_voltbridge.vendor.mygrid_voltbridge import (
    BroadcastStream,
    P1Broadcast,
    P1Data,
    PhaseData,
    parse_telegram,
)

SERIAL = "1SAG0000000000"
TELEGRAM_TEXT = (
    (Path(__file__).parent / "fixtures" / "voltbridge_telegram.txt")
    .read_bytes()
    .decode("latin-1")
)


def make_telegram():  # type: ignore[no-untyped-def]
    return parse_telegram(TELEGRAM_TEXT)


def make_data(**overrides: object) -> P1Data:
    values: dict[str, object] = {
        "meter_serial": SERIAL,
        "meter_version": "50217",
        "import_power": 261,
        "export_power": 0,
        "net_power": 261,
        "avg_import_1min": 261,
        "avg_export_1min": 0,
        "avg_demand": 199,
        "peak_demand": 2348,
        "peak_demand_at": datetime(2026, 10, 21, 18, 15, tzinfo=UTC),
        "tariff": 1,
        "energy_import_t1": 3673536,
        "energy_import_t2": 4432452,
        "energy_export_t1": 0,
        "energy_export_t2": 0,
        "gas": 440.448,
        "phases": {1: PhaseData(261, 0, 237.3, 1.7)},
    }
    values.update(overrides)
    return P1Data(**values)  # type: ignore[arg-type]


def make_broadcast(**overrides: object) -> P1Broadcast:
    data = make_data(
        gas=None, avg_import_1min=None, avg_export_1min=None, meter_version="50217"
    )
    for key, value in overrides.items():
        object.__setattr__(data, key, value)
    return P1Broadcast(
        stream=BroadcastStream.P1,
        timestamp=datetime(2026, 10, 23, 18, 51, 22, tzinfo=UTC),
        rssi=-79,
        country="BE",
        software_version="1.0",
        data=data,
    )
