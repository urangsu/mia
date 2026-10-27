#!/usr/bin/env python3
"""Offline restore from SUPT-style MIA source TXT parts. No Git/network access."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile

PATTERNS = {'collector': 'MIA_COLLECTOR_PART_*.txt', 'dom': 'MIA_DOM_PART_*.txt'}
REQUIRED = {
    'collector': ('FastmarketsCollector_v3_7.py', 'FastmarketsCollector_v3_4.py',
                  'AGENTS.md', 'requirements-desktop.txt'),
    'dom': ('manifest.json', 'multi_picker.js', 'scan_core.js', 'popup.html', 'popup.js'),
}

def git_blob_sha1(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode('ascii')+b'\0'+raw).hexdigest()

def safe_path(name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError(f'위험 경로: {name!r}')
    p = PurePosixPath(name)
    if p.is_absolute() or str(p) != name or any(x in ('', '.', '..') for x in name.split('/')):
        raise ValueError(f'위험 경로: {name!r}')
    return p

def restore(project, source, output_root, verify_only):
    part_files = sorted(source.glob(PATTERNS[project]))
    if not part_files:
        raise FileNotFoundError(f'{project}: 필수 TXT 파트가 없습니다 ({PATTERNS[project]})')
    records, headers, total = {}, [], 0
    for part_file in part_files:
        with part_file.open('r', encoding='utf-8-sig') as f:
            h = json.loads(f.readline())
            if h.get('format') != 'mia-text-bringin-v1' or h.get('project') != project:
                raise ValueError(f'{part_file.name}: TXT 형식 불일치')
            headers.append(h)
            count = 0
            for lineno, line in enumerate(f, start=2):
                if not line.strip():
                    continue
                if len(line) > 24_000_000:
                    raise ValueError(f'{part_file.name}:{lineno}: 지나치게 긴 행')
                rec = json.loads(line)
                path = str(safe_path(rec['path']))
                if path in records:
                    raise ValueError(f'중복 파일: {path}')
                raw = base64.b64decode(rec['base64'], validate=True)
                if len(raw) != rec['size'] or len(raw) > 12_000_000:
                    raise ValueError(f'파일 크기 불일치: {path}')
                if git_blob_sha1(raw) != rec['blob_sha1']:
                    raise ValueError(f'파일 해시 불일치: {path}')
                total += len(raw)
                if len(records) >= 2000 or total > 120_000_000:
                    raise ValueError('허용된 번들 크기를 초과했습니다')
                records[path] = raw
                count += 1
            if count != h['part_file_count']:
                raise ValueError(f'{part_file.name}: 파트 내 파일 수 불일치')
    first = headers[0]
    for h in headers:
        for key in ('bundle_id', 'parts', 'files', 'source_commit', 'project'):
            if h.get(key) != first.get(key):
                raise ValueError('서로 다른 버전의 TXT가 섞였습니다')
    if len(headers) != first['parts'] or sorted(h['part'] for h in headers) != list(range(1,first['parts']+1)):
        raise ValueError(f'파트 누락/중복: 실제 {len(headers)}개, 필요 {first["parts"]}개')
    if len(records) != first['files']:
        raise ValueError(f'복원 파일 수 불일치: {len(records)}/{first["files"]}')
    for required in REQUIRED[project]:
        if required not in records:
            raise ValueError(f'{project}: 필수 파일 누락 {required}')
    if project == 'dom':
        meta = json.loads(records['manifest.json'])
        if meta.get('manifest_version') != 3 or not str(meta.get('version', '')).startswith('4.'):
            raise ValueError('DOM V4 확장 매니페스트가 아닙니다')
    print(f'[무결성 PASS] {project}: {len(records)}개 파일 / {total:,} bytes')
    if verify_only:
        return
    output_root.mkdir(parents=True, exist_ok=True)
    version = first['source_commit'][:12] if project == 'collector' else first['bundle_id'][:12]
    target = output_root / (('MIA_Collector_' if project == 'collector' else 'MIA_DOM_V4_') + version)
    if target.exists():
        print(f'[기존 설치 유지] {target}')
        return
    staging = Path(tempfile.mkdtemp(dir=output_root, prefix='.mia-staging-'))
    try:
        for name, raw in records.items():
            p = staging.joinpath(*PurePosixPath(name).parts)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
        (staging/'_MIA_BUNDLE_INFO.txt').write_text(
            'project='+project+'\nbundle_id='+first['bundle_id']+
            '\nsource_commit='+first['source_commit']+
            '\nno data, credentials, or browser profiles imported\n', encoding='utf-8')
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(f'[복원 완료] {target}')
    if project == 'dom':
        print('Chrome: chrome://extensions -> 개발자 모드 -> 압축해제된 확장 프로그램 로드')
    else:
        print('Collector: 승인된 Python 환경에서 requirements-desktop.txt 확인 후 실행')
        
def main():
    ap = argparse.ArgumentParser(description='오프라인 TXT 소스 복원: 수집 데이터/기존 앱 변경 없음')
    ap.add_argument('--project', choices=('collector','dom','both'), default='both')
    ap.add_argument('--input-dir', type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument('--output-root', type=Path,
        default=Path(os.environ.get('LOCALAPPDATA') or Path.home())/'MIA_Text_Restored')
    ap.add_argument('--verify-only', action='store_true')
    a = ap.parse_args()
    try:
        for project in (('collector','dom') if a.project=='both' else (a.project,)):
            restore(project,a.input_dir,a.output_root,a.verify_only)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'[복원 중단] {exc}', file=sys.stderr)
        return 2
    print('[완료] 인터넷/Git/Chrome/ECM/원본 SQLite/Excel에 접근하지 않았습니다.')
    return 0

if __name__=='__main__':
    sys.exit(main())
