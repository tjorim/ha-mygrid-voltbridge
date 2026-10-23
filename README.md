# ha-mygrid-voltbridge

Home Assistant custom integration for the **MyGrid VoltBridge** P1 meter adapter. It talks to the device on your LAN only (no cloud, no MQTT broker needed) using the [`mygrid-voltbridge`](https://github.com/tjorim/mygrid-voltbridge) library.

- **Push first:** live power, voltage and current arrive by the device's UDP broadcast about once a second.
- **Polling fallback:** the HTTP snapshot (energy totals, gas, demand) is read every 30 s by default (5–600 s in the integration options). It is also the only source if UDP broadcasts do not reach Home Assistant, for example across VLANs or in a container without host networking.
- **Discovery:** the device is found automatically through mDNS (`_mygrid._tcp`), or enter its address manually.

The device API is reverse-engineered and unofficial. It was checked against one single-phase meter on firmware build 15.6; see the library's [API notes](https://github.com/tjorim/mygrid-voltbridge/blob/main/docs/api.md).

## Installation

HACS → Custom repositories → add `https://github.com/tjorim/ha-mygrid-voltbridge` as an *Integration*, install, restart Home Assistant, then **Settings → Devices & services → Add integration → MyGrid VoltBridge**. The integration installs its library from GitHub at first start, so Home Assistant needs internet access once.

## Entities

| Entity | Notes |
| --- | --- |
| Net / import / export power | W; positive net power is import |
| Energy imported / exported (day, night) | `total_increasing`, suitable for the Energy dashboard |
| Voltage, current, import/export power per phase | One set for each phase the meter reports (L1 verified) |
| Average demand, peak demand, peak demand time | Created if the meter reports them |
| Tariff | `day` / `night` |
| Gas | m³; only if a gas meter is connected. Read by polling; it is not part of the UDP broadcast |

Entities are created from the first snapshot, so connect the P1 cable before adding the integration. Each device is identified by its P1 meter serial, so an IP change is handled automatically when mDNS discovery sees it again, or via **Reconfigure**.

## Not verified

Export power/energy and phases L2/L3 are decoded by pattern, not against real hardware, because the test meter is single-phase with no export. The meaning of "average demand" is taken from the field name. Please open an issue with a diagnostics download (host and serial are redacted) if values look wrong.

## Development

```sh
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

The tests mock the library, which has its own tests. They have not been run against a live Home Assistant instance with a real device.
