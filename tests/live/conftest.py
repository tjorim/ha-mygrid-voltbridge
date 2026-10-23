"""Mark everything below ``live/`` as live, so ordinary runs deselect it.

Run with a reachable VoltBridge::

    VOLTBRIDGE_HOST=192.168.0.45 uv run pytest -m live
"""

import os

import pytest
from pytest_socket import socket_allow_hosts


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Add the ``live`` marker to every test in this directory."""
    for item in items:
        if "/live/" in item.nodeid:
            item.add_marker(pytest.mark.live)


@pytest.fixture(scope="session")
def voltbridge_host() -> str:
    """Return the device address, or skip when none is configured."""
    host = os.environ.get("VOLTBRIDGE_HOST")
    if host is None or host == "":
        pytest.skip("set VOLTBRIDGE_HOST to run the live smoke tests")
    return host


@pytest.fixture
def real_network(socket_enabled: None, voltbridge_host: str) -> None:
    """Let the test reach the device; the Home Assistant runtime blocks other hosts."""
    socket_allow_hosts([voltbridge_host, "127.0.0.1", "::1"], allow_unix_socket=True)
