"""Push-first coordinator: the library's live stream for power, polling for the rest."""

import asyncio
import dataclasses
import logging
from collections.abc import Mapping
from contextlib import aclosing
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from mygrid_voltbridge import (
    DeviceInfo,
    LiveUpdate,
    P1Data,
    P1Status,
    PhaseData,
    Telegram,
    VoltBridgeClient,
    VoltBridgeError,
    VoltBridgeNoDataError,
    VoltBridgeUnsupportedError,
    async_stream,
)

from .const import CONF_POLL_INTERVAL, DOMAIN, VOLTBRIDGE_DEFAULT_POLL_INTERVAL

LOGGER = logging.getLogger(__name__)
# The status page is larger than the JSON replies and changes only with a firmware update.
DEVICE_INFO_INTERVAL = timedelta(hours=1)
# How long the stream may hear nothing from the device before it is unavailable.
OFFLINE_AFTER = 30
# Pause before following the device again after it went offline.
RESTART_DELAY = 5
type VoltBridgeConfigEntry = ConfigEntry[VoltBridgeCoordinator]


class VoltBridgeCoordinator(DataUpdateCoordinator[P1Data]):
    """Follow the meter through the library's merged UDP/HTTP stream.

    The stream pushes ~1 Hz UDP telegrams, reads ``/api/power`` while they are
    lost or cannot start, and refreshes the snapshot (gas, totals) in between.
    The raw telegram and the status are polled beside it on the same interval.
    The coordinator has no ``update_interval`` of its own.
    """

    config_entry: VoltBridgeConfigEntry

    def __init__(self, hass: HomeAssistant, entry: VoltBridgeConfigEntry) -> None:
        """Initialize the VoltBridgeCoordinator."""
        super().__init__(hass, LOGGER, config_entry=entry, name=DOMAIN)
        self.client = VoltBridgeClient(
            entry.data[CONF_HOST], async_get_clientsession(hass)
        )
        self._poll_interval = timedelta(
            seconds=entry.options.get(
                CONF_POLL_INTERVAL, VOLTBRIDGE_DEFAULT_POLL_INTERVAL
            )
        )
        self._no_data_issue = False
        self.telegram: Telegram | None = None
        self.status: P1Status | None = None
        self.device_info: DeviceInfo | None = None

    @property
    def phases(self) -> Mapping[int, PhaseData]:
        """Return the per-phase values: the live snapshot, else the last telegram.

        The snapshot keys for L2 and L3 are a guess at the firmware's naming, so
        a phase the snapshot lacks is read from the telegram's standard DSMR
        codes instead. Those values are as old as the last poll.
        """
        phases = dict(self.telegram.phases) if self.telegram is not None else {}
        phases.update(self.data.phases)
        return phases

    async def _async_update_data(self) -> P1Data:
        """Read the first snapshot; the stream takes over from there."""
        try:
            data = await self.client.async_get_p1_data()
        except VoltBridgeNoDataError as err:
            self._set_no_data_issue(active=True)
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="voltbridge_no_data"
            ) from err
        except VoltBridgeError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="voltbridge_communication_error",
            ) from err
        self._set_no_data_issue(active=False)
        await self._async_update_telegram()
        await self._async_update_status()
        return data

    def _set_no_data_issue(self, *, active: bool) -> None:
        """Show a repair while the meter sends no P1 data; only touch it on change."""
        if active == self._no_data_issue:
            return
        self._no_data_issue = active
        issue_id = f"no_p1_data_{self.config_entry.entry_id}"
        if active:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="no_p1_data",
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

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

    async def _async_update_status(self) -> None:
        """Read the Wi-Fi signal and P1 packet statistics.

        Optional like the telegram: older firmware may lack the detail, and a
        failure here keeps the last good reading instead of failing the update.
        """
        try:
            self.status = await self.client.async_get_status()
        except VoltBridgeUnsupportedError:
            self.status = None
        except VoltBridgeError as err:
            LOGGER.debug("Status unavailable, keeping the previous one: %s", err)

    async def _async_read_device_info(self) -> None:
        """Read the adapter's firmware and MAC from its status page.

        Optional: without them the device is still identified by the meter
        serial, and a failed read keeps the previous values.
        """
        try:
            info = await self.client.async_get_device_info()
        except VoltBridgeError as err:
            LOGGER.debug("Device info unavailable, keeping the previous one: %s", err)
            return
        self.device_info = info

    async def _async_refresh_device_info(self, _now: object) -> None:
        """Pick up a new firmware build without a reload."""
        await self._async_read_device_info()
        registry = dr.async_get(self.hass)
        device = registry.async_get_device_by_identifier(
            (DOMAIN, str(self.data.meter_serial)), self.config_entry.entry_id
        )
        if (
            device is not None
            and self.device_info is not None
            and device.sw_version != self.device_info.build_info
        ):
            registry.async_update_device(
                device.id, sw_version=self.device_info.build_info
            )

    async def async_start(self) -> None:
        """Take the first snapshot, then follow the meter and poll the details."""
        await self.async_config_entry_first_refresh()
        await self._async_read_device_info()
        self.config_entry.async_on_unload(
            async_track_time_interval(
                self.hass, self._async_poll_details, self._poll_interval
            )
        )
        self.config_entry.async_on_unload(
            async_track_time_interval(
                self.hass, self._async_refresh_device_info, DEVICE_INFO_INTERVAL
            )
        )
        self.config_entry.async_create_background_task(
            self.hass, self._async_follow_stream(), f"{DOMAIN} live stream"
        )

    async def _async_poll_details(self, _now: object) -> None:
        """Refresh what the stream does not carry: telegram and status."""
        await self._async_update_telegram()
        await self._async_update_status()
        self.async_update_listeners()

    async def _async_follow_stream(self) -> None:
        """Keep a stream open for as long as the entry is loaded.

        The stream ends when the device has been silent for ``OFFLINE_AFTER``
        seconds, or fails its first read. The entities turn unavailable and the
        stream is started again, so the device is picked up once it is back.
        """
        initial: P1Data | None = self.data  # just read; a restart needs a fresh one
        while True:
            try:
                async with aclosing(
                    async_stream(
                        self.client,
                        initial=initial,
                        poll_interval=self._poll_interval.total_seconds(),
                        offline_after=OFFLINE_AFTER,
                    )
                ) as stream:
                    async for update in stream:
                        self._handle_update(update)
            except VoltBridgeError as err:
                self._handle_offline(err)
            initial = None
            await asyncio.sleep(RESTART_DELAY)

    def _handle_update(self, update: LiveUpdate) -> None:
        self._set_no_data_issue(active=False)
        # The broadcasts carry the signal strength: keep it fresh between polls.
        if update.rssi is not None and self.status is not None:
            self.status = dataclasses.replace(self.status, rssi=update.rssi)
        self.async_set_updated_data(update.data)

    def _handle_offline(self, err: VoltBridgeError) -> None:
        LOGGER.debug("Lost the VoltBridge: %s", err)
        no_data = isinstance(err, VoltBridgeNoDataError)
        self._set_no_data_issue(active=no_data)
        self.async_set_update_error(
            UpdateFailed(
                translation_domain=DOMAIN,
                translation_key=(
                    "voltbridge_no_data"
                    if no_data
                    else "voltbridge_communication_error"
                ),
            )
        )
