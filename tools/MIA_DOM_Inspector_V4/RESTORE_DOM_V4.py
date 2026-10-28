# -*- coding: utf-8 -*-
"""Restore the exact MIA DOM Inspector V4 extension files using Python stdlib.

Input is a sha256-verified base64 XZ tar archive, NOT executable input.
Does not access browsers, profiles, network, credentials, SQLite or Excel.
Never overwrites an existing destination.
"""
import argparse
import base64
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile


def safe_name(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or "\\" in name or ":" in name or
            any(part in ("", ".", "..") for part in name.split("/"))):
        raise ValueError("Unsafe member path: " + repr(name))
    return path


def restore(archive_path, destination, verify_only=False):
    archive_path = Path(archive_path).resolve()
    lines = archive_path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 2:
        raise ValueError("Archive must have exactly two lines")
    metadata = json.loads(lines[0])
    if metadata.get("format") != "mia-text-tarxz-v1" or metadata.get("project") != "dom":
        raise ValueError("Not a MIA DOM V4 source bundle")
    data = base64.b64decode(lines[1], validate=True)
    if len(data) != metadata["archive_bytes"] or sha256(data).hexdigest() != metadata["sha256"]:
        raise ValueError("Archive SHA-256/size mismatch: restoration refused")
    extracted = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as bundle:
        members = bundle.getmembers()
        if len(members) != metadata["files"] or len(members) > 100:
            raise ValueError("Unexpected file count")
        if sum(member.size for member in members) > 5 * 1024 * 1024:
            raise ValueError("Unpacked archive is too large")
        for member in members:
            safe_name(member.name)
            if not member.isfile() or member.name in extracted:
                raise ValueError("Non-regular or duplicate archive member")
            stream = bundle.extractfile(member)
            if stream is None:
                raise ValueError("Unreadable member: " + member.name)
            content = stream.read()
            if len(content) != member.size:
                raise ValueError("Archive member size mismatch")
            extracted[member.name] = content
    if "manifest.json" not in extracted or "multi_picker.js" not in extracted:
        raise ValueError("Required Chrome extension source files missing")
    manifest = json.loads(extracted["manifest.json"].decode("utf-8"))
    if manifest.get("manifest_version") != 3 or manifest.get("version") != "4.0.0":
        raise ValueError("Unexpected extension manifest")
    if verify_only:
        print("PASS:", len(extracted), "files verified; Chrome extension V4")
        return
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise FileExistsError("Destination already exists (will not overwrite): " + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".mia-dom-v4-", dir=destination.parent))
    try:
        for name, content in extracted.items():
            target = staging / str(safe_name(name))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print("Restored Chrome extension folder:", destination)
    print("Chrome -> chrome://extensions -> Developer mode -> Load unpacked -> select the folder above")


def main():
    parser = argparse.ArgumentParser(description="Verify/restore MIA DOM Inspector V4 source files")
    parser.add_argument("--archive", default=str(Path(__file__).with_name("MIA_DOM_ARCHIVE_V4.txt")))
    parser.add_argument("--output", default=str(Path(__file__).with_name("extension")))
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        restore(args.archive, args.output, args.verify_only)
    except Exception as exc:
        parser.exit(2, "RESTORE FAILED: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
