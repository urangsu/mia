#!/usr/bin/env python3
"""Restore the reviewed MIA source from one JSONL text bundle, offline.

Usage: py restore_mia_text_bundle.py [MIA_TEXT_BUNDLE.txt] --out mia-v3.7-hotfix1
Only validates and writes files. Does not install dependencies or run the app.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath

EXPECTED_BUNDLE_SHA256 = 'da5662f073e83a458188bae15820d6c19330aa0b8fa3fa001bf6263849eb311f'
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


def read_bundle(path):
    text = read_text(path)
    header, separator, payload = text.partition('---\n')
    if not separator or not header.startswith('MIA_TEXT_BUNDLE\n'):
        raise ValueError('Invalid MIA bundle header')
    meta = dict(line.split(': ', 1) for line in header.splitlines()[1:] if ': ' in line)
    if meta.get('format') != 'mia_text_bundle_v1':
        raise ValueError('Unsupported MIA bundle format')
    if payload.endswith('\n'):
        payload = payload[:-1]
    # The expected hash lives in this restorer, independently of the text file.
    actual = sha(payload.encode('utf-8'))
    if actual != EXPECTED_BUNDLE_SHA256 or meta.get('bundle_sha256') != actual:
        raise ValueError('MIA bundle checksum mismatch; save the complete Raw text as UTF-8')
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


def restore(bundle, output):
    metadata, files = records(read_bundle(bundle))
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
    parser = argparse.ArgumentParser(description='Restore MIA v3.7 hotfix1 from one text bundle (offline)')
    parser.add_argument('bundle', nargs='?', type=Path,
                        default=Path(__file__).resolve().parent/'MIA_TEXT_BUNDLE.txt')
    parser.add_argument('--out', type=Path, default=Path('mia-v3.7-hotfix1'))
    args = parser.parse_args()
    try:
        restore(args.bundle, args.out)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('ERROR: '+str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
