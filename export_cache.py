"""Skip a verified unchanged export only when both source facts and file bytes match."""
import hashlib,json,os,tempfile
from pathlib import Path

def digest_sheets(sheets):
    return hashlib.sha256(json.dumps(sheets,ensure_ascii=False,sort_keys=True,default=str,
        separators=(',',':')).encode('utf8')).hexdigest()

def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as fp:
        for b in iter(lambda:fp.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def state_path(path):return Path(str(path)+'.fm37-state.json')

def unchanged(path,sheets):
    try:
        state=json.loads(state_path(path).read_text('utf8'))
        return state.get('version')==37 and state.get('data_sha256')==digest_sheets(sheets) and state.get('file_sha256')==file_hash(path)
    except (OSError,ValueError,TypeError):return False

def record(path,sheets):
    path=Path(path);target=state_path(path)
    state={'version':37,'data_sha256':digest_sheets(sheets),'file_sha256':file_hash(path)}
    fd,name=tempfile.mkstemp(prefix=target.name,dir=target.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf8') as fp:
            json.dump(state,fp);fp.flush();os.fsync(fp.fileno())
        os.replace(name,target)
    finally:Path(name).unlink(missing_ok=True)
