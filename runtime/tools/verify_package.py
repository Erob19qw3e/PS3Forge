#!/usr/bin/env python3
"""Check a PSL1GHT staging directory and PKG headers; not a signature/hardware test."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_sfo(path):
    raw = Path(path).read_bytes()
    if len(raw) < 20:
        raise ValueError("PARAM.SFO header is truncated.")
    magic, version, keys, values, count = struct.unpack_from("<4s4I", raw)
    if magic != b"\x00PSF" or count > 4096:
        raise ValueError("Invalid PARAM.SFO header.")
    if not 20 + 16 * count <= keys <= values <= len(raw):
        raise ValueError("Invalid PARAM.SFO table offsets.")
    fields = {}
    for i in range(count):
        ko, fmt, size, capacity, vo = struct.unpack_from("<HHIII", raw, 20 + i * 16)
        start = keys + ko
        end = raw.find(b"\0", start, values) if keys <= start < values else -1
        if end < 0 or size > capacity or vo + size > len(raw) - values:
            raise ValueError("Invalid PARAM.SFO entry bounds.")
        key = raw[start:end].decode("utf-8")
        if not key or key in fields:
            raise ValueError("Invalid or duplicate PARAM.SFO key.")
        data = raw[values + vo:values + vo + size]
        fields[key] = data.rstrip(b"\0").decode("utf-8") if fmt == 0x0204 else data.hex()
    return fields


def verify(project, appid=None, app_version=None, title=None, pkg=None, stage=None):
    project = Path(project).resolve()
    stage = Path(stage) if stage else Path("build/pkg")
    if not stage.is_absolute():
        stage = project / stage
    fields = read_sfo(stage / "PARAM.SFO")
    for key, expected in (("TITLE_ID", appid), ("APP_VER", app_version), ("TITLE", title)):
        if key not in fields:
            raise ValueError(f"Missing metadata: {key}")
        if expected is not None and fields[key] != expected:
            raise ValueError(f"{key} mismatch: {fields[key]!r} != {expected!r}")
    with (stage / "USRDIR/EBOOT.BIN").open("rb") as stream:
        if stream.read(4) != b"SCE\0":
            raise ValueError("EBOOT.BIN has no SCE header.")
    resource_root = project / "pkgfiles"
    if not resource_root.is_dir():
        raise ValueError("Missing pkgfiles directory.")
    checked = 0
    for source in sorted(resource_root.rglob("*")):
        if source.is_file():
            destination = stage / source.relative_to(resource_root)
            if not destination.is_file() or digest(source) != digest(destination):
                raise ValueError(f"Staged resource mismatch: {source.relative_to(resource_root)}")
            checked += 1
    with (stage / "ICON0.PNG").open("rb") as stream:
        png = stream.read(24)
    if len(png) != 24 or png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
        raise ValueError("ICON0.PNG has no valid PNG/IHDR header.")
    icon_size = struct.unpack_from(">II", png, 16)
    if not all(icon_size):
        raise ValueError("Invalid icon dimensions.")
    if pkg is None:
        choices = [project / f"{project.name}.gnpdrm.pkg", project / f"{project.name}.pkg"]
        package = next((path for path in choices if path.is_file()), None)
        if package is None:
            raise FileNotFoundError("No PKG found; use --pkg for a custom target.")
    else:
        package = Path(pkg)
        if not package.is_absolute():
            package = project / package
    with package.open("rb") as stream:
        if stream.read(4) != b"\x7fPKG":
            raise ValueError("Invalid PKG magic.")
    return {
        "package": str(package), "bytes": package.stat().st_size,
        "sha256": digest(package), "title_id": fields["TITLE_ID"],
        "app_version": fields["APP_VER"], "title": fields["TITLE"],
        "staged_resources_checked": checked, "icon_dimensions": list(icon_size),
        "checks": "staging, metadata and headers only; not signature or hardware verification"
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--appid")
    parser.add_argument("--app-version")
    parser.add_argument("--title")
    parser.add_argument("--pkg", type=Path)
    parser.add_argument("--stage", type=Path)
    args = parser.parse_args()
    try:
        report = verify(args.project, args.appid, args.app_version, args.title, args.pkg, args.stage)
    except (OSError, ValueError, UnicodeError, struct.error) as exc:
        parser.exit(2, f"Package check failed: {exc}\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
