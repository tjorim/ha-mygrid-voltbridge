"""Start the config flow the way a user does; this package has no device menu."""

from homeassistant.config_entries import SOURCE_USER

from custom_components.mygrid_voltbridge.const import DOMAIN


async def start_voltbridge(hass, data=None):
    """Open the config flow and optionally submit its form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    if data is not None:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    return result
