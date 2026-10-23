"""Validate the standalone HACS package and its generated library provenance."""

import ast
import hashlib
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/mygrid_voltbridge"


def main() -> None:
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert list(manifest) == [
        "domain",
        "name",
        *sorted(set(manifest) - {"domain", "name"}),
    ]
    assert manifest["domain"] == "mygrid_voltbridge"
    assert manifest["version"] == project["project"]["version"] == "0.1.0"
    assert manifest["requirements"] == project["project"]["dependencies"] == []
    assert "dependencies" not in manifest
    assert manifest["dhcp"] == [{"registered_devices": True}]
    assert manifest["zeroconf"] == [
        {"type": "_mygrid._tcp.local.", "properties": {"model": "voltbridge*"}}
    ]
    assert manifest["config_flow"] and manifest["iot_class"] == "local_push"
    assert "quality_scale" not in manifest
    assert json.loads((COMPONENT / "strings.json").read_text()) == json.loads(
        (COMPONENT / "translations/en.json").read_text()
    )
    vendor = COMPONENT / "vendor"
    origin = json.loads((vendor / "origin.json").read_text())
    assert origin["version"] == "0.3.0"
    actual = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (vendor / "mygrid_voltbridge").iterdir()
        if path.suffix == ".py" or path.name == "py.typed"
    }
    assert actual == origin["sha256"], (
        "Vendored library differs from recorded source hashes"
    )
    adapter_files = (
        list(COMPONENT.glob("*.py"))
        + list(COMPONENT.glob("*.json"))
        + list(COMPONENT.glob("*.yaml"))
        + [COMPONENT / "translations/en.json"]
    )
    adapter = {
        str(path.relative_to(COMPONENT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in adapter_files
    }
    assert adapter == origin["adapter_sha256"], (
        "Generated adapter differs from canonical-source hashes"
    )
    assert (vendor / "LICENSE.mygrid-voltbridge").exists()
    for path in COMPONENT.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith(
                    (
                        "pymodbus",
                        "tmodbus",
                        "mygrid_voltbridge",
                        "modbus_connection.tmodbus",
                        "modbus_connection.pymodbus",
                    )
                ), path
    print(
        "HACS metadata, offline vendoring provenance, and namespace boundaries validated."
    )


if __name__ == "__main__":
    main()
