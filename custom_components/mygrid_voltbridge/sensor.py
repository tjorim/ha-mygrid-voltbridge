"""Power, energy, phase, demand, gas and water sensors."""

from .voltbridge_sensor import async_setup_entry

PARALLEL_UPDATES = 0

__all__ = ["PARALLEL_UPDATES", "async_setup_entry"]
