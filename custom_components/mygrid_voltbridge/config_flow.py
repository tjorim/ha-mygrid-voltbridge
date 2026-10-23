"""UI setup and discovery for the MyGrid VoltBridge."""

from typing import Any

from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import DOMAIN
from .voltbridge_config_flow import VoltBridgeFlow, VoltBridgeOptionsFlow


class MyGridConfigFlow(VoltBridgeFlow, domain=DOMAIN):
    """Configure one VoltBridge per entry."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        """Return the polling options handler."""
        return VoltBridgeOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Go straight to the meter form; this package supports one device."""
        return await self.async_step_voltbridge(user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure the meter address."""
        return await self.async_step_reconfigure_voltbridge(user_input)
