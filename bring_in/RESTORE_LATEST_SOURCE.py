"""Restore MIA_SOURCE_CURRENT.txt using Python stdlib only, never overwrite.

The TXT is inert source data, not shell/Python instructions. SHA-256 verifies
integrity, not publisher authenticity: obtain both files from the trusted repo.
"""
import argparse
import base64
from hashlib import sha256
import io
import json
from pathlib import Path,PurePosixPath
import re
import tempfile
import zipfile

FORMAT='mia-source-zip-v2'


def safe_path(name):
    path=PurePosixPath(name)
    if not name or '\\' in name or ':' in name or path.is_absolute() or any(p in ('..','.') for p in name.split('/')):
        raise ValueError('안전하지 않은 소스 경로: '+name)
    if any(not p for p in name.split('/')):raise ValueError('빈 소스 경로')
    return path


def restore_source(txt,destination=None,*,verify_only=False):
    txt=Path(txt).resolve()
    if txt.stat().st_size>30*1024*1024:raise ValueError('TXT 크기 제한 초과')
    lines=txt.read_text(encoding='utf-8').splitlines()
    if len(lines)!=2:raise ValueError('단일 TXT 형식 불일치; 예전 PART/ONEFILE 파일과 섞지 마세요.')
    try:
        header=json.loads(lines[0]);archive=base64.b64decode(lines[1],validate=True)
    except (ValueError,TypeError) as exc:raise ValueError('TXT 데이터 손상') from exc
    if header.get('format')!=FORMAT or not re.fullmatch('[0-9a-f]{40}',header.get('source_commit','')):
        raise ValueError('소스 버전/커밋 형식 불일치')
    if sha256(archive).hexdigest()!=header.get('archive_sha256'):raise ValueError('ZIP SHA-256 불일치')
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        info=z.infolist()
        if len(info)>1500 or sum(i.file_size for i in info)>80*1024*1024:raise ValueError('복원 소스 크기 제한 초과')
        names=[i.filename for i in info]
        if len(names)!=len(set(names)) or len(names)!=len({n.casefold() for n in names}):raise ValueError('중복 소스 경로')
        for item in info:
            safe_path(item.filename)
            if item.is_dir() or (item.external_attr>>16)&0o170000==0o120000:raise ValueError('디렉터리/링크 항목 금지')
        manifest_raw=z.read('SOURCE_MANIFEST.json')
        if sha256(manifest_raw).hexdigest()!=header.get('manifest_sha256'):raise ValueError('목록 SHA-256 불일치')
        manifest=json.loads(manifest_raw)
        if manifest.get('source_commit')!=header['source_commit'] or set(names)!=set(manifest['files'])|{'SOURCE_MANIFEST.json'}:
            raise ValueError('커밋/파일 목록 불일치')
        files={name:z.read(name) for name in manifest['files']}
        if any(sha256(data).hexdigest()!=manifest['files'][name] for name,data in files.items()):raise ValueError('개별 소스 SHA-256 불일치')
    if verify_only:return manifest
    if destination is None:
        destination=txt.parent/'MIA_Collector_Update'
    destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError('기존 폴더를 덮어쓰지 않습니다: '+str(destination)+' / 기존 복원본을 확인하거나 --output으로 다른 새 폴더를 지정하세요.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.mia-source-',dir=destination.parent) as tmp:
        staged=Path(tmp)/'source';staged.mkdir()
        for name,data in files.items():
            path=staged/str(safe_path(name));path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        (staged/'SOURCE_MANIFEST.json').write_bytes(manifest_raw)
        if destination.exists():raise FileExistsError(str(destination))
        staged.rename(destination)
    print('복원 완료:',destination,'/ 소스',len(files),'개 / 커밋',manifest['source_commit'])
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='MIA 단일 TXT 무결성 확인/새 폴더 복원')
    parser.add_argument('txt',nargs='?',default=str(Path(__file__).with_name('MIA_SOURCE_CURRENT.txt')))
    parser.add_argument('--output');parser.add_argument('--verify-only',action='store_true')
    args=parser.parse_args()
    try:
        result=restore_source(args.txt,args.output,verify_only=args.verify_only)
        if args.verify_only:print('검증 성공:',result['source_commit'],len(result['files']),'files')
    except Exception as exc:
        parser.exit(2,'복원 중단: '+str(exc)+'\n')
