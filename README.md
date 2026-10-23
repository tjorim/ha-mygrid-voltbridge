# MyGrid VoltBridge for Home Assistant

Home Assistant custom integration for the **MyGrid VoltBridge** P1 meter adapter. It talks to the device on your LAN only (no cloud, no MQTT broker needed): live values by the device's UDP broadcast and the rest over its local HTTP API.

Requires **Home Assistant 2026.10.2 or newer** (Python 3.14.2+). The package includes a generated, licensed copy of the independent [`mygrid-voltbridge`](https://github.com/tjorim/mygrid-voltbridge) library, so no PyPI install is needed. This is a community integration; it has **not** received an official Home Assistant quality rating (see [quality tracking](custom_components/mygrid_voltbridge/quality_scale.yaml)). The device API is reverse-engineered and unofficial, and was checked against one single-phase meter on firmware build 15.6.

> The MyGrid **ModuleTwo** battery has its own repository, [ha-mygrid-modbus](https://github.com/tjorim/ha-mygrid-modbus): HACS allows one integration per repository, so the two devices are separate integrations here. A combined integration for Home Assistant core is developed in [ha-mygrid-core](https://github.com/tjorim/ha-mygrid-core).

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
| Breaker | Diagnostic: open / closed / ready to reconnect |
| Limiter and fuse threshold | Diagnostic, disabled by default; created only when the meter has real limits (999.9 kW / 999 A mean none) |

There are no actions, buttons or controls: the integration never writes to the device, which has no authentication, so keep it on your trusted LAN.

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

This is a generated community-testing package. HACS allows one integration per repository, so each MyGrid device has its own HACS repository, both generated from the same umbrella source in `ha-mygrid-core`:

| Repository | Role |
| --- | --- |
| `mygrid-voltbridge` | Standalone client library: HTTP API, DSMR telegram, UDP decoder, live smoke tests |
| `ha-mygrid-core` | Canonical umbrella integration (domain `mygrid`) shaped for Home Assistant core, plus the generator for the HACS packages |
| `ha-mygrid-voltbridge` | This HACS package: domain `mygrid_voltbridge`, generated adapter code and the byte-for-byte vendored library |
| `ha-mygrid-modbus` | The matching HACS package for the ModuleTwo battery |

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

The vendored files are under `custom_components/mygrid_voltbridge/vendor/mygrid_voltbridge`, with the license and an `origin.json` recording version, source commits and per-file SHA-256 hashes. Do not edit generated files here: change the library in `mygrid-voltbridge` or the integration in `ha-mygrid-core`, then run `uv run python scripts/sync_hacs.py` (and `--check`) in `ha-mygrid-core`. Entries of this package do not migrate to the core integration later; add the device again there. Manufacturer-approved brand art is still pending, so HACS's brand check is exempted. The earlier prototype of this repository used the same domain, so its config entries keep working.
