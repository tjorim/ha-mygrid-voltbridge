# ha-mygrid-voltbridge

Home Assistant custom integration for the **MyGrid VoltBridge** P1 meter adapter. It talks to the device on your LAN only (no cloud, no MQTT broker needed) using the [`mygrid-voltbridge`](https://github.com/tjorim/mygrid-voltbridge) library.

- **Push first:** live power, voltage and current arrive by the device's UDP broadcast about once a second.
- **Polling fallback:** the HTTP snapshot (energy totals, gas, demand) is read every 30 s by default (5–600 s in the integration options). It is also the only source if UDP broadcasts do not reach Home Assistant, for example across VLANs or in a container without host networking.
- **Discovery:** the device is found automatically through mDNS (`_mygrid._tcp`), or enter its address manually.

The device API is reverse-engineered and unofficial. It was checked against one single-phase meter on firmware build 15.6; see the library's [API notes](https://github.com/tjorim/mygrid-voltbridge/blob/main/docs/api.md).

## Supported devices

The MyGrid VoltBridge P1 meter adapter (hardware `P1Wifi-rev1`, firmware `voltbridge` build 15.6). The MyGrid ModuleTwo battery is a different device and is not supported here; see [ha-mygrid](https://github.com/tjorim/ha-mygrid).

## Installation

1. HACS → three-dot menu → *Custom repositories* → add `https://github.com/tjorim/ha-mygrid-voltbridge` as an *Integration*, then download it.
2. Restart Home Assistant. The first start installs the library from GitHub, so Home Assistant needs internet access once.
3. The VoltBridge is discovered automatically (**Settings → Devices & services**). Otherwise choose **Add integration → MyGrid VoltBridge** and enter its address.

Connect the P1 cable before adding the device: entities are created from the first snapshot, and setup waits until the meter has delivered a telegram.

## Configuration

- **Host** (setup and *Reconfigure*): IP address or hostname. A changed address is picked up automatically through mDNS or DHCP discovery; a reconfigure to a different meter is refused.
- **Polling interval** (*Configure*, default 30 s, 5-600 s): how often the HTTP snapshot is read.

## How data arrives

Live power, voltage and current come from the device's UDP broadcast (port 49491, about once a second). The HTTP snapshot and the raw DSMR telegram, which carry gas, water, the breaker and the peak history, are polled. A quiet UDP stream never delays the poll. If broadcasts do not reach Home Assistant (VLANs, containers without host networking), everything still works at the polling interval, and the log says "polling only" when the UDP port could not be opened.

## Supported functions

| Entity | Notes |
| --- | --- |
| Net / import / export power | W; positive net power is import |
| Energy imported / exported (day, night) | `total_increasing`, suitable for the Energy dashboard |
| Voltage and current per phase | One set for each phase the meter reports (L1 verified) |
| Import / export power per phase | Disabled by default |
| Current average demand, peak demand, peak demand time | Quarter-hour average and the month's peak (capacity tariff). The peak sensor carries the monthly peak history as the `history` attribute |
| Water | m³ from a water meter on the meter's M-Bus, read from the raw telegram |
| Breaker | Diagnostic: open / closed / ready to reconnect |
| Limiter and fuse threshold | Diagnostic, disabled by default; created only when the meter has real limits (999.9 kW / 999 A mean none) |
| Tariff | `day` / `night` |
| Gas | m³; only if a gas meter is connected. Polled; not part of the UDP broadcast |

There are no actions, buttons or controls. The device has no authentication and the integration never writes to it.

## Examples

- **Energy dashboard:** add *Energy imported (day/night)* as grid consumption and *Energy exported (day/night)* as return to grid, and *Gas* as the gas source.
- **Solar-surplus automation:** trigger when *Net power* stays below `-500` W for five minutes, then start the washing machine. Net power is the sum of all phases, negative while exporting.
- **Capacity tariff (Belgium):** alert when *Current average demand* (the running quarter-hour average, DSMR `1-0:1.4.0`) climbs towards the month's *Peak demand*.

## Known limitations

- The API is reverse-engineered and unofficial; firmware changes can break it.
- Export power/energy and phases L2/L3 are decoded by pattern, not verified against hardware (the test meter is single-phase with no export).
- Gas and water meters report every few minutes to an hour, so those sensors change at that pace.
- Entities appear only for what the meter reports when the entry is set up. Reload the entry after connecting a gas or water meter or adding a phase.
- Only one meter per config entry; add the integration again for a second VoltBridge.
- Not published on PyPI or the HACS default list; no brand artwork is bundled.

## Troubleshooting

- *Cannot reach the VoltBridge:* open `http://<address>/` in a browser from the Home Assistant host. The page must load.
- *No P1 telegram yet / repair "VoltBridge receives no P1 data":* check the P1 cable and that the meter's P1 port is enabled. The repair clears itself.
- *Values only update every 30 s:* UDP broadcasts are not arriving. Check VLAN and firewall rules for UDP 49491, or use host networking.
- *Wrong or missing gas:* reload the integration after the gas meter has reported once.
- Download **diagnostics** from the device page when reporting a problem; the host and meter serial are redacted.

## Removal

Delete the integration entry under **Settings → Devices & services**; this removes its device, entities and any repair issue. Optionally uninstall it in HACS afterwards.

## Quality scale

[`quality_scale.yaml`](custom_components/mygrid_voltbridge/quality_scale.yaml) is a self-assessment modelled on the HomeWizard integration. Two Bronze items are still open (brand artwork and publishing the library on PyPI), so no tier is claimed.

## Development

```sh
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

The tests mock the library, which has its own tests. They have not been run against a live Home Assistant instance with a real device.
