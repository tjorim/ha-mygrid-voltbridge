# MyGrid VoltBridge for Home Assistant

## Documentation

See the [MyGrid documentation hub](https://github.com/tjorim/custom-mygrid#readme)
for device setup guides, protocol references and repository links.

Home Assistant custom integration for the [**MyGrid VoltBridge**](https://moduletwo.mygrid.energy/nl/voltbridge) P1 meter adapter. It talks to the device on your LAN only (no cloud, no MQTT broker needed): live values by the device's UDP broadcast and the rest over its local HTTP API.

Requires **Home Assistant 2026.10.2 or newer** (Python 3.14.2+). The integration uses the independent [`mygrid-voltbridge`](https://github.com/tjorim/python-mygrid-voltbridge) library from PyPI, which Home Assistant installs automatically. This is a community integration; it has **not** received an official Home Assistant quality rating (see [quality tracking](custom_components/mygrid_voltbridge/quality_scale.yaml)). The device API is reverse-engineered and unofficial, and was checked against one single-phase meter on firmware build 15.6.

> The MyGrid **ModuleTwo** battery has its own repository, [ha-mygrid-modbus](https://github.com/tjorim/ha-mygrid-modbus): HACS allows one integration per repository, so the two devices are separate integrations here.

- **Push first:** live power, voltage and current arrive by UDP broadcast about once a second.
- **Polling:** the HTTP snapshot and the raw DSMR telegram (energy totals, gas, water, breaker, peak history) are read every 30 s by default (5-600 s under **Configure**). It is also the only source if UDP broadcasts do not reach Home Assistant, for example across VLANs or in a container without host networking.
- **Discovery:** found automatically through mDNS (`_mygrid._tcp`), followed to a new address through DHCP, or enter its address manually.

## Installation

1. HACS → three-dot menu → *Custom repositories* → add `https://github.com/tjorim/ha-mygrid-voltbridge` as an *Integration*, then download it. Alternatively copy `custom_components/mygrid_voltbridge` into your Home Assistant configuration directory (`dist/mygrid-voltbridge-0.1.0.zip` is built by `scripts/build_release.py`).
2. Restart Home Assistant.
3. The VoltBridge is discovered automatically (**Settings → Devices & services**). Otherwise choose **Add integration → MyGrid VoltBridge** and enter its address.

Connect the P1 cable before adding the device: entities are created from the first snapshot, and setup waits until the meter has delivered a telegram. Each meter is identified by its P1 serial, so an IP change is picked up automatically by discovery, or via **Reconfigure** (which refuses a different meter).

## Entities

| Entity | Notes |
| --- | --- |
| Net / import / export power | W; positive net power is import |
| Energy imported / exported (day, night) | `total_increasing`, suitable for the Energy dashboard |
| Voltage and current per phase | One set per phase the meter reports (L1 verified) |
| Import / export power per phase | Disabled by default |
| Current average demand, peak demand, peak demand time | Quarter-hour average and the month's peak (capacity tariff). The peak sensor carries the monthly peak history as the `history` attribute |
| Tariff | `day` / `night` |
| Gas, water | m³; only if those meters are connected to the meter's M-Bus. Read by polling; not part of the UDP broadcast |
| Meter model, DSMR version | Diagnostic: what the meter reports in its telegram header |
| Breaker | Diagnostic: open / closed / ready to reconnect |
| Wi-Fi signal | Diagnostic, dBm. Kept fresh by the UDP stream (a poor signal explains missed updates) |
| P1 packet error rate | Diagnostic, %: the share of P1 telegrams that failed their checksum. A rising value points at the P1 cable |
| Reboot | Button, disabled by default. Restarts the VoltBridge; the entities are unavailable until it answers again |
| Limiter and fuse threshold | Diagnostic, disabled by default; created only when the meter has real limits (999.9 kW / 999 A mean none) |

The device page shows the adapter's firmware build (read from its status page and refreshed hourly), its MAC address as serial number, and the hardware revision when the device was discovered over mDNS.

The only thing the integration ever sends to the device is the opt-in **Reboot** button (never retried). The device has no authentication, so keep it on your trusted LAN.

## Examples

- **Energy dashboard:** add *Energy imported (day/night)* as grid consumption, *Energy exported (day/night)* as return to grid, and *Gas* or *Water* as sources.
- **Solar-surplus automation:** trigger when *Net power* stays below `-500` W for five minutes, then start the washing machine. Net power is negative while exporting.
- **Capacity tariff (Belgium):** alert when *Current average demand* (the running quarter-hour average, DSMR `1-0:1.4.0`) climbs towards the month's *Peak demand*.

## Known limitations

- The API is reverse-engineered and unofficial; firmware changes can break it.
- Export power/energy and phases L2/L3 are decoded by pattern, not verified against hardware (the test meter is single-phase with no export).
- Gas and water meters report every few minutes to an hour, so those sensors change at that pace.
- Entities appear only for what the meter reports when the entry is set up. Reload the entry after connecting a gas or water meter or adding a phase.
- One meter per config entry; add the integration again for a second VoltBridge.

## Troubleshooting

- *Cannot reach the VoltBridge:* open `http://<address>/` in a browser from the Home Assistant host. The page must load.
- *No P1 telegram yet / repair "VoltBridge receives no P1 data":* check the P1 cable and that the meter's P1 port is enabled. The repair clears itself.
- *Values only update every 30 s:* UDP broadcasts are not arriving. Check VLAN and firewall rules for UDP 49491, or use host networking.
- Download **diagnostics** from the device page when reporting a problem; the host and meter serial are redacted.

## Removal

Delete the entry under **Settings → Devices & services**; this removes its device, entities and any repair issue. Optionally remove the HACS download and restart.

## Development

This is the community-testing integration for the VoltBridge. HACS allows one integration per repository, so each MyGrid device has its own HACS repository. This repository is the source of truth for its integration code and tests; the device library is a separate PyPI package.

| Repository | Role |
| --- | --- |
| `python-mygrid-voltbridge` | Standalone client library (PyPI package `mygrid-voltbridge`): HTTP API, DSMR telegram, UDP decoder, live smoke tests |
| `ha-mygrid-voltbridge` | This HACS integration: domain `mygrid_voltbridge`, depending on the PyPI library |
| `ha-mygrid-modbus` | The matching HACS integration for the ModuleTwo battery |
| `ha-mygrid-core` | Dormant umbrella integration (domain `mygrid`) kept for a possible Home Assistant core contribution; not used or maintained for the HACS packages |

A checkout of this repository is self-contained for tests and installation:

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run python scripts/validate_metadata.py
uv run python scripts/build_release.py
```

Change integration code and tests here. Change device or API behavior in `python-mygrid-voltbridge`, publish a release to PyPI, then bump the `mygrid-voltbridge==` pin in `custom_components/mygrid_voltbridge/manifest.json` and in the `dev` dependency group of `pyproject.toml` (run `uv lock`); `scripts/validate_metadata.py` fails if the two pins differ. Entries of this package do not migrate to a core integration later; add the device again there. Manufacturer-approved brand art is still pending, so HACS's brand check is exempted. The earlier prototype of this repository used the same domain, so its config entries keep working.

To try the integration in a real Home Assistant, run `scripts/develop`: it starts Home Assistant with the component importable from this checkout and a configuration in `config/` (ignored by git). The first start installs the default integrations' requirements and needs network access; then open http://localhost:8123.

A live end-to-end test runs the integration inside the Home Assistant test runtime against a real device: `VOLTBRIDGE_HOST=192.168.0.45 uv run pytest -m live --no-cov`. It is excluded from ordinary runs.
