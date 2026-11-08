"""Validate the HACS package metadata and its dependency pins."""

import json
import tomllib
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/mygrid_voltbridge"


def validate_library_pin(requirements: list[str], dev: list[str]) -> None:
    """Require one exact library version shared by runtime and tests."""
    if len(requirements) != 1:
        msg = "Expected one runtime library requirement"
        raise ValueError(msg)
    requirement = Requirement(requirements[0])
    pins = list(requirement.specifier)
    if (
        requirement.name != "mygrid-voltbridge"
        or requirement.url is not None
        or requirement.marker is not None
        or requirement.extras
        or len(pins) != 1
        or pins[0].operator != "=="
        or "*" in pins[0].version
    ):
        msg = "Expected an exact mygrid-voltbridge version"
        raise ValueError(msg)
    if requirements[0] not in dev:
        msg = "Runtime library pin must match the development dependency"
        raise ValueError(msg)


def main() -> None:
    """Validate the package metadata and library pin."""
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert list(manifest) == [
        "domain",
        "name",
        *sorted(set(manifest) - {"domain", "name"}),
    ]
    assert manifest["domain"] == "mygrid_voltbridge"
    assert manifest["version"] == project["project"]["version"] == "0.1.0"
    validate_library_pin(manifest["requirements"], project["dependency-groups"]["dev"])
    assert "dependencies" not in manifest
    assert manifest["dhcp"] == [{"registered_devices": True}]
    assert manifest["zeroconf"] == [
        {"type": "_mygrid._tcp.local.", "properties": {"model": "voltbridge*"}}
    ]
    assert manifest["config_flow"]
    assert manifest["iot_class"] == "local_push"
    assert "quality_scale" not in manifest
    assert json.loads((COMPONENT / "strings.json").read_text()) == json.loads(
        (COMPONENT / "translations/en.json").read_text()
    )
    print("HACS metadata and library pin validated.")


if __name__ == "__main__":
    main()
