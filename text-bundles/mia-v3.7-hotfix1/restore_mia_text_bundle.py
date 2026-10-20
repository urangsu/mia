#!/usr/bin/env python3
"""Restore the reviewed mia source from PGPT JSONL text parts, offline.

Usage: py restore_mia_text_bundle.py [PGPT_TEXT_PART_*.txt] --out mia-v3.7-hotfix1
Only validates and writes files. Does not install dependencies or run the app.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath

PART_RE = re.compile(r'PGPT_TEXT_PART_(\d+)\.txt', re.I)
HASH_RE = re.compile(r'[0-9a-f]{64}')
RELEASE = 'mia-v3.7-hotfix1-20261020'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_text(path):
    # Git checkout or editor CRLF/BOM conversion may change the envelope but
    # never the escaped original file contents inside JSON strings.
    return path.read_bytes().decode('utf-8-sig').replace('\r\n', '\n')


def safe_relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('Unsafe file path')
    if value.startswith('/') or any(p in ('', '.', '..') for p in value.split('/')):
        raise ValueError('Unsafe file path: '+value)
    for part in value.split('/'):
        if part.endswith((' ', '.')) or re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part, re.I):
            raise ValueError('Unsupported Windows file path: '+value)
    return PurePosixPath(value)


def read_parts(paths):
    if not paths:
        raise ValueError('No PGPT_TEXT_PART_*.txt found beside this script')
    found = {}
    count = None
    bundle_hash = None
    folder = paths[0].parent.resolve()
    manifest_path = folder/'PGPT_TEXT_PARTS.sha256.txt'
    if not manifest_path.is_file():
        raise ValueError('Missing PGPT_TEXT_PARTS.sha256.txt')
    manifest = {}
    for line in read_text(manifest_path).splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (PGPT_TEXT_PART_\d+\.txt)', line)
        if match:
            if match[2] in manifest:
                raise ValueError('Duplicate checksum entry')
            manifest[match[2]] = match[1]
    for path in paths:
        match = PART_RE.fullmatch(path.name)
        if not match or path.parent.resolve() != folder:
            raise ValueError('Parts must have numbered filenames in the same folder')
        text = read_text(path)
        if manifest.get(path.name) != sha(text.encode('utf-8')):
            raise ValueError('Part file checksum mismatch: '+path.name)
        header, separator, payload = text.partition('---\n')
        if not separator or not header.startswith('PGPT_TEXT_BRINGIN_PART\n'):
            raise ValueError('Invalid part header: '+path.name)
        meta = dict(line.split(': ', 1) for line in header.splitlines()[1:] if ': ' in line)
        if meta.get('format') != 'pgpt_text_bringin_v1':
            raise ValueError('Unsupported bundle format')
        part = re.fullmatch(r'([1-9]\d*)/([1-9]\d*)', meta.get('part', ''))
        if not part:
            raise ValueError('Invalid part index')
        index, total = map(int, part.groups())
        if index != int(match[1]) or index > total or index in found:
            raise ValueError('Wrong or duplicate part index: '+path.name)
        if count is None:
            count, bundle_hash = total, meta.get('bundle_sha256', '')
        if total != count or meta.get('bundle_sha256') != bundle_hash:
            raise ValueError('Mixed bundles or part counts')
        if payload.endswith('\n'):
            payload = payload[:-1]
        if meta.get('payload_sha256') != sha(payload.encode('utf-8')):
            raise ValueError('Payload checksum mismatch: '+path.name)
        found[index] = payload
    if set(found) != set(range(1, count+1)) or len(manifest) != count:
        raise ValueError('Missing or extra parts; all parts and the checksum file are required')
    if not HASH_RE.fullmatch(bundle_hash):
        raise ValueError('Invalid bundle checksum')
    payload = '\n'.join(found[i] for i in range(1, count+1))
    if sha(payload.encode('utf-8')) != bundle_hash:
        raise ValueError('Bundle checksum mismatch')
    return payload


def records(payload):
    rows = [json.loads(line) for line in payload.splitlines() if line.strip()]
    if any(not isinstance(row,dict) for row in rows):
        raise ValueError('Invalid bundle record')
    if not rows or rows[0].get('type') != 'meta' or rows[0].get('release') != RELEASE:
        raise ValueError('Wrong release metadata')
    metadata = rows[0]
    files = {}
    casefold_paths = set()
    for row in rows[1:]:
        if row.get('type') != 'file' or not isinstance(row.get('content'), str):
            raise ValueError('Invalid file record')
        relative = safe_relative(row.get('path'))
        key = str(relative).casefold()
        if key in casefold_paths:
            raise ValueError('Duplicate file path: '+str(relative))
        casefold_paths.add(key)
        content = row['content'].encode('utf-8')
        if row.get('size') != len(content) or row.get('sha256') != sha(content):
            raise ValueError('File content checksum mismatch: '+str(relative))
        files[relative] = content
    if metadata.get('file_count') != len(files):
        raise ValueError('File count mismatch')
    # Block a file whose parent is another file before writing anything.
    for relative in files:
        if any(str(parent).casefold() in casefold_paths for parent in relative.parents if str(parent) != '.'):
            raise ValueError('File/directory path collision')
    return metadata, files


def restore(paths, output):
    metadata, files = records(read_parts(paths))
    if output.is_symlink():
        raise ValueError('Output must not be a symbolic link')
    output = output.absolute()
    if output.exists():
        if output.is_dir() and all(not (output/str(rel)).is_symlink() and
                (output/str(rel)).is_file() and (output/str(rel)).read_bytes() == data
                for rel, data in files.items()):
            print('Already restored: all '+str(len(files))+' file contents match. No files changed.')
            return
        raise ValueError('Output already exists with different contents; choose a new --out folder')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.mia-restore-', dir=output.parent) as temp:
        stage = Path(temp)/'source'
        stage.mkdir()
        for relative, data in files.items():
            path = stage.joinpath(*relative.parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            if path.read_bytes() != data:
                raise ValueError('Restored file verification failed: '+str(relative))
        # Output must still be absent. No app data or existing files are replaced.
        if output.exists() or output.is_symlink():
            raise ValueError('Output appeared during restoration; nothing replaced')
        stage.rename(output)
    print('Verified and restored '+str(len(files))+' files to '+str(output))
    print('Source commit: '+metadata['source_commit'])
    print('Next: open '+str(output/'START_HERE_KO.txt'))


def main():
    parser = argparse.ArgumentParser(description='Restore mia v3.7 hotfix1 from text parts (offline)')
    parser.add_argument('parts', nargs='*')
    parser.add_argument('--out', type=Path, default=Path('mia-v3.7-hotfix1'))
    args = parser.parse_args()
    paths = []
    for pattern in args.parts:
        expanded = glob.glob(pattern) if any(c in pattern for c in '*?') else [pattern]
        if not expanded:
            parser.error('No files match: '+pattern)
        paths.extend(Path(p) for p in expanded)
    if not args.parts:
        paths = sorted(Path(__file__).resolve().parent.glob('PGPT_TEXT_PART_*.txt'))
    try:
        restore(paths, args.out)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('ERROR: '+str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
