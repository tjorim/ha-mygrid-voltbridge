"""Push-first coordinator: UDP broadcasts for live values, HTTP polling for the rest."""

import dataclasses
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_POLL_INTERVAL, DOMAIN, VOLTBRIDGE_DEFAULT_POLL_INTERVAL
from .vendor.mygrid_voltbridge import (
    BroadcastStream,
    P1Broadcast,
    P1Data,
    Telegram,
    VoltBridgeClient,
    VoltBridgeError,
    VoltBridgeNoDataError,
    VoltBridgeUnsupportedError,
    async_listen,
)

LOGGER = logging.getLogger(__name__)
type VoltBridgeConfigEntry = ConfigEntry[VoltBridgeCoordinator]


class VoltBridgeCoordinator(DataUpdateCoordinator[P1Data]):
    """Merge ~1 Hz UDP telegrams into the periodically polled HTTP snapshot.

    The coordinator has no ``update_interval``: every push would otherwise
    reset the poll timer and starve the HTTP read that carries gas and totals.
    """

    config_entry: VoltBridgeConfigEntry

    def __init__(self, hass: HomeAssistant, entry: VoltBridgeConfigEntry) -> None:
        super().__init__(hass, LOGGER, config_entry=entry, name=DOMAIN)
        self.client = VoltBridgeClient(
            entry.data[CONF_HOST], async_get_clientsession(hass)
        )
        self._poll_interval = timedelta(
            seconds=entry.options.get(
                CONF_POLL_INTERVAL, VOLTBRIDGE_DEFAULT_POLL_INTERVAL
            )
        )
        self._cancel_poll: CALLBACK_TYPE | None = None
        self.telegram: Telegram | None = None

    async def _async_update_data(self) -> P1Data:
        issue_id = f"no_p1_data_{self.config_entry.entry_id}"
        try:
            data = await self.client.async_get_p1_data()
        except VoltBridgeNoDataError as err:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="no_p1_data",
            )
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="voltbridge_no_data"
            ) from err
        except VoltBridgeError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="voltbridge_communication_error",
            ) from err
        ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        await self._async_update_telegram()
        return data

    async def _async_update_telegram(self) -> None:
        """Read the raw telegram for water, breaker and peak history.

        Optional: older firmware may lack the endpoint, and a failure here must
        not make the main snapshot unavailable, so the last good one is kept.
        """
        try:
            self.telegram = await self.client.async_get_telegram()
        except VoltBridgeUnsupportedError:
            self.telegram = None
        except VoltBridgeError as err:
            LOGGER.debug("Telegram unavailable, keeping the previous one: %s", err)

    async def async_start(self) -> None:
        """Take the first snapshot, then start push and poll."""
        await self.async_config_entry_first_refresh()
        self._cancel_poll = async_track_time_interval(
            self.hass, self._async_poll, self._poll_interval
        )
        self.config_entry.async_on_unload(self._stop)
        try:
            transport = await async_listen(self._handle_broadcast)
        except OSError as err:
            LOGGER.warning("UDP push unavailable, polling only: %s", err)
        else:
            self.config_entry.async_on_unload(transport.close)

    @callback
    def _stop(self) -> None:
        if self._cancel_poll is not None:
            self._cancel_poll()
            self._cancel_poll = None

    async def _async_poll(self, _now: object) -> None:
        await self.async_refresh()

    @callback
    def _handle_broadcast(self, broadcast: P1Broadcast) -> None:
        """Overlay a live telegram from this meter onto the cached snapshot."""
        if broadcast.stream is not BroadcastStream.P1 or self.data is None:
            return
        if broadcast.data.meter_serial != self.data.meter_serial:
            return
        live = {
            field.name: value
            for field in dataclasses.fields(P1Data)
            if (value := getattr(broadcast.data, field.name)) is not None
            and field.name not in ("meter_version", "phases")
        }
        # Rebuild phases wholesale so L2/L3 appear and disappear with the meter.
        self.async_set_updated_data(
            dataclasses.replace(self.data, **live, phases=broadcast.data.phases)
        )
