"""Deterministic source-only ZIP/TXT from a Git commit, never live working data."""
import argparse
import base64
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import tarfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bring_in.RESTORE_LATEST_SOURCE import FORMAT,safe_path


def company_layout(files):
    """Keep a small user-facing root; preserve every source-relative path in app/."""
    visible = {
        'MIA_Collector.py': 'MIA_Collector.py',
        'RUN_GUI.cmd': 'RUN_GUI.cmd',
        'requirements.txt': 'requirements.txt',
        'requirements-desktop.txt': 'requirements-desktop.txt',
        'README_회사.txt': 'bring_in/MIA_COMPANY_SETUP_GUIDE_KO.txt',
    }
    missing = sorted(set(visible.values()) - set(files))
    if missing:
        raise ValueError('회사 배포 필수 파일 누락: ' + ', '.join(missing))
    for name in files:
        safe_path(name)
    layout = {'app/' + name: content for name, content in files.items()}
    layout.update({name: files[source] for name, source in visible.items()})
    archive=files.get('tools/MIA_DOM_Inspector_V4/MIA_DOM_ARCHIVE_V4.txt')
    if archive is not None:
        lines=archive.decode('utf-8').splitlines()
        if len(lines)!=2:raise ValueError('DOM source archive format')
        meta=json.loads(lines[0]);raw=base64.b64decode(lines[1],validate=True)
        if (meta.get('format')!='mia-text-tarxz-v1' or meta.get('project')!='dom'
            or len(raw)!=meta.get('archive_bytes') or sha256(raw).hexdigest()!=meta.get('sha256')):
            raise ValueError('DOM source archive integrity')
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:xz') as source:
            members=source.getmembers()
            if len(members)!=meta.get('files') or len(members)>100 or sum(m.size for m in members)>5*1024*1024:
                raise ValueError('DOM source archive bounds')
            seen=set()
            for member in members:
                safe_path(member.name)
                if not member.isfile() or member.name.casefold() in seen:raise ValueError('DOM unsafe member')
                seen.add(member.name.casefold())
                stream=source.extractfile(member)
                layout['DOM_확장/'+member.name]=stream.read()
        manifest=json.loads(layout.get('DOM_확장/manifest.json',b'{}'))
        if manifest.get('manifest_version')!=3 or manifest.get('version')!='4.0.0':raise ValueError('DOM manifest mismatch')
        if 'DOM_확장/multi_picker.js' not in layout:raise ValueError('DOM picker missing')
    return layout


def write_bundle(files,commit,output):
    for name in files:safe_path(name)
    if 'SOURCE_MANIFEST.json' in files:raise ValueError('예약된 manifest 경로')
    manifest=dict(format=FORMAT,source_commit=commit,files={n:sha256(v).hexdigest() for n,v in sorted(files.items())})
    raw=json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(dict(files,**{'SOURCE_MANIFEST.json':raw}).items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16;z.writestr(info,data)
    archive=buffer.getvalue();header=dict(format=FORMAT,source_commit=commit,
        archive_sha256=sha256(archive).hexdigest(),manifest_sha256=sha256(raw).hexdigest())
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    txt=output/'MIA_SOURCE_CURRENT.txt';bundle=output/'MIA_Collector.zip'
    bundle.write_bytes(archive)
    txt.write_text(json.dumps(header,sort_keys=True)+'\n'+base64.b64encode(archive).decode()+'\n',encoding='utf-8')
    return dict(txt=str(txt),zip=str(bundle),source_commit=commit,file_count=len(files),archive_sha256=header['archive_sha256'])


def build(repo,revision,output):
    repo=Path(repo)
    def git(*args):return subprocess.check_output(['git','-C',str(repo),*args])
    commit=git('rev-parse',revision+'^{commit}').decode().strip();files={}
    names=git('ls-tree','-r','--name-only','-z',commit).decode().split('\0')
    extensions={'.py','.md','.txt','.html','.js','.css','.json','.cmd','.sh','.toml','.yml','.yaml'}
    for name in filter(None,names):
        path=Path(name)
        if name.startswith('bring_in/') or name.startswith('.git/') or path.name.startswith('.env'):continue
        if path.suffix not in extensions and path.name!='.gitignore':continue
        files[name]=git('show',commit+':'+name)
    # Include only the new restoration helper, never the old nested bundles.
    helper='bring_in/RESTORE_LATEST_SOURCE.py';files[helper]=git('show',commit+':'+helper)
    launcher='bring_in/RESTORE_LATEST_SOURCE.cmd';files[launcher]=git('show',commit+':'+launcher)
    guide='bring_in/MIA_COMPANY_SETUP_GUIDE_KO.txt';files[guide]=git('show',commit+':'+guide)
    result=write_bundle(company_layout(files),commit,output)
    (Path(output)/'RESTORE_LATEST_SOURCE.py').write_bytes(files[helper])
    (Path(output)/'RESTORE_LATEST_SOURCE.cmd').write_bytes(files[launcher])
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repo',default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--revision',default='HEAD');parser.add_argument('--output-dir',required=True)
    args=parser.parse_args();print(json.dumps(build(args.repo,args.revision,args.output_dir),ensure_ascii=False,indent=2))
