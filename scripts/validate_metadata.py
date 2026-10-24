"""Validate the HACS package metadata and its dependency pins."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/mygrid_voltbridge"


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
    assert manifest["requirements"] == ["mygrid-voltbridge==0.4.0"]
    assert manifest["requirements"][0] in project["dependency-groups"]["dev"]
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
