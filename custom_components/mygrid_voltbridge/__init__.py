"""MyGrid VoltBridge P1 meter: local push over UDP with HTTP polling."""

from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .voltbridge_setup import (
    async_setup_voltbridge_entry as async_setup_entry,
)
from .voltbridge_setup import (
    async_unload_voltbridge_entry as async_unload_entry,
)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

__all__ = ["CONFIG_SCHEMA", "async_setup_entry", "async_unload_entry"]
