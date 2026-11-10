# Community-testing releases

The integration is published at https://github.com/tjorim/ha-mygrid-voltbridge and can be installed through a HACS custom repository. Catalog listing is a separate submission. There is no official Home Assistant quality rating.

## Prepare a release

1. Publish any device-library changes to PyPI first. Keep the exact library pin in `manifest.json` and the `dev` dependency group in `pyproject.toml` aligned, then update `uv.lock`.
2. Set the same integration version in `manifest.json` and `pyproject.toml`. Update versioned installation examples in README.
3. Run every development check listed in README. CI runs those checks plus hassfest and HACS validation.
4. Build the manual-install ZIP with `uv run python scripts/build_release.py`. Test installation and setup in a clean configuration on the minimum supported Home Assistant version. Test HACS custom-repository installation, updates and removal separately.
5. Record physical test results and remaining limitations in the release notes. Automated tests do not establish physical acceptance. Keep reboot and power commands explicit during testing.
6. Create a GitHub release with a tag exactly matching the manifest version, such as `0.1.0`, and attach `dist/mygrid-voltbridge-0.1.0.zip`. The release workflow checks the tag and rebuilds the ZIP before attaching it. Local build commands never publish a release.

## Before catalog submission

- Keep the community icon in `custom_components/mygrid_voltbridge/brand/` consistent with the [brand requirements](https://contributors.home-assistant.io/core/integrations/brands/). It originates from `custom-mygrid/assets/icon.svg` (Apache-2.0) and is not a manufacturer logo. HACS validates brands without an exemption.
- Confirm ongoing maintainership by the listed code owner.
- Confirm both HACS and hassfest pass without exemptions required by the catalog.
- Follow the [catalog submission guide](https://contributors.home-assistant.io/marketplace/guides/catalog/); custom-repository installation alone does not add the integration to the catalog.

A future core submission is a separate effort. Never install two implementations of the same domain in one Home Assistant instance.
