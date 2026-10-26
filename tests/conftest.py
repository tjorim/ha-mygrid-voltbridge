"""VoltBridge fixtures mock the independent client library, not HTTP or UDP."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from mygrid_voltbridge import LiveUpdate, P1Data, UpdateSource
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mygrid_voltbridge.const import DOMAIN

from .support import SERIAL, make_data, make_device_info, make_status, make_telegram


@pytest.fixture
def vb_client() -> Generator[AsyncMock]:
    with (
        patch(
            "custom_components.mygrid_voltbridge.coordinator.VoltBridgeClient"
        ) as coordinator_cls,
        patch(
            "custom_components.mygrid_voltbridge.config_flow.VoltBridgeClient",
            coordinator_cls,
        ),
    ):
        instance = AsyncMock()
        instance.async_get_p1_data.return_value = make_data()
        instance.async_get_telegram.return_value = make_telegram()
        instance.async_get_status.return_value = make_status()
        instance.async_get_device_info.return_value = make_device_info()
        coordinator_cls.return_value = instance
        yield instance


class FakeStream:
    """Stand-in for ``async_stream``: yields what a test pushes, or raises what it fails with."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[LiveUpdate | Exception] = asyncio.Queue()
        self.calls: list[dict[str, object]] = []
        self.closed = 0

    def __call__(self, client: object, **kwargs: object) -> AsyncGenerator[LiveUpdate]:
        self.calls.append(kwargs)
        return self._run()

    async def _run(self) -> AsyncGenerator[LiveUpdate]:
        try:
            while True:
                item = await self.queue.get()
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            self.closed += 1

    def push(
        self,
        data: P1Data,
        source: UpdateSource = UpdateSource.UDP,
        rssi: int | None = None,
    ) -> None:
        now = datetime.now(UTC)
        self.queue.put_nowait(LiveUpdate(data, source, now, now, rssi))

    def fail(self, error: Exception) -> None:
        self.queue.put_nowait(error)


@pytest.fixture
def vb_stream() -> Generator[FakeStream]:
    """Patch ``async_stream``; the restart pause is skipped."""
    stream = FakeStream()
    with (
        patch("custom_components.mygrid_voltbridge.coordinator.async_stream", stream),
        patch("custom_components.mygrid_voltbridge.coordinator.RESTART_DELAY", 0),
    ):
        yield stream


@pytest.fixture
def vb_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="MyGrid VoltBridge",
        unique_id=SERIAL,
        data={"device": "voltbridge", "host": "192.168.0.45"},
    )


@pytest.fixture
def vb_setup_entry() -> Generator[None]:
    """Skip real setup when a flow creates an entry."""
    with patch(
        "custom_components.mygrid_voltbridge.async_setup_entry", return_value=True
    ):
        yield


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Enable the custom integration in the test runtime."""
