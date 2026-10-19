"""Opt-in, local, read-only evidence. Does not export DB rows or authentication."""
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
import argparse,json,sqlite3,sys
import FastmarketsCollector_v3_4 as core

def inspect(folder):
    db=core.path_bundle(Path(folder))['db']
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'mode':'read-only',
            'platform':sys.platform,'db_exists':db.exists(),
            'excluded':['cookies','passwords','tokens','profiles','browser URLs','database row values']}
    if not db.exists():return result
    with closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)) as cx:
        result['integrity']=cx.execute('PRAGMA integrity_check').fetchone()[0]
        result['tables']={}
        for name, in cx.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            # Identifier quote; schema names may contain arbitrary characters.
            quoted='"'+name.replace('"','""')+'"'
            result['tables'][name]={'count':cx.execute('SELECT COUNT(*) FROM '+quoted).fetchone()[0],
                'columns':[r[1] for r in cx.execute('PRAGMA table_info('+quoted+')')]}
        known=result['tables']
        if 'v37_stages' in known:
            result['recent_stages']=[dict(stage=r[0],status=r[1],seconds=r[2]) for r in cx.execute(
                'SELECT stage,status,elapsed_seconds FROM v37_stages ORDER BY rowid DESC LIMIT 30')]
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--data-dir');p.add_argument('--output',type=Path)
    a=p.parse_args();result=inspect(a.data_dir or core.config_load()['data_dir'])
    body=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with core.atomic_text(a.output) as fp:fp.write(body+'\n')
    print(body)

if __name__=='__main__':main()
