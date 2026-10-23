"""Build a deterministic manual-install ZIP of the standalone HACS package."""

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    component = ROOT / "custom_components/mygrid_voltbridge"
    version = json.loads((component / "manifest.json").read_text())["version"]
    output = ROOT / "dist" / f"mygrid-voltbridge-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(component.rglob("*")):
            if (
                not path.is_file()
                or "__pycache__" in path.parts
                or path.suffix == ".pyc"
            ):
                continue
            info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix())
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
        for name in ["LICENSE", "README.md"]:
            archive.writestr(zipfile.ZipInfo(name), (ROOT / name).read_bytes())
    print(output)


if __name__ == "__main__":
    main()
