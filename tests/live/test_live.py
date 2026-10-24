"""Run the real integration inside the Home Assistant test runtime against a real device.

Nothing is mocked: the config flow reads the meter, the entry sets up, UDP push
and HTTP polling are real. The assertions only check structure and liveness.
"""

import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from tests.flows import start_voltbridge


async def test_real_voltbridge_end_to_end(
    hass: HomeAssistant, real_network: None, voltbridge_host: str
) -> None:
    result = await start_voltbridge(hass, {"host": voltbridge_host})
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    entry = result["result"]
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    # Entity names come from translations, which the test runtime does not load,
    # so find the sensors by their stable unique ids ("<serial>_<key>").
    states = {
        item.unique_id.split("_", 1)[1]: hass.states.get(item.entity_id)
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
        if not item.disabled
    }
    assert states, "no entities were created"
    net = states["net_power"]
    assert net is not None
    float(net.state)  # numeric
    imported = states["energy_import_t1"]
    assert imported is not None
    assert float(imported.state) > 0

    # UDP push: the state is reported again within a few seconds, long before the
    # 30 s poll could do it.
    first = net.last_reported
    await asyncio.sleep(3)
    latest = hass.states.get(net.entity_id)
    assert latest is not None
    assert latest.last_reported > first

    assert await hass.config_entries.async_unload(entry.entry_id)
