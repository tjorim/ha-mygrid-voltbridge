"""Shared constants for MyGrid."""

DOMAIN = "mygrid_voltbridge"

# One config entry per device; entries without a device type are ModuleTwo.
CONF_DEVICE = "device"
DEVICE_MODULETWO = "moduletwo"
DEVICE_VOLTBRIDGE = "voltbridge"

CONF_POLL_INTERVAL = "poll_interval"
CONF_MAC = "mac"
CONF_HARDWARE_VERSION = "hardware_version"

# ModuleTwo battery (Modbus TCP)
DEFAULT_PORT = 502
DEFAULT_POLL_INTERVAL = 5
MIN_POLL_INTERVAL = 2
MAX_POLL_INTERVAL = 300

# VoltBridge P1 meter (HTTP snapshot polling alongside UDP push)
VOLTBRIDGE_DEFAULT_POLL_INTERVAL = 30
VOLTBRIDGE_MIN_POLL_INTERVAL = 5
VOLTBRIDGE_MAX_POLL_INTERVAL = 600
