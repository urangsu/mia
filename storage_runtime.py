"""Additive v3.7 schema and resumable run ledger. SQLite remains authoritative."""
from __future__ import annotations
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import json,sqlite3,uuid

VERSION=37

def migrate_database(db):
    db=Path(db);db.parent.mkdir(parents=True,exist_ok=True)
    existed=db.exists() and db.stat().st_size>0
    with closing(sqlite3.connect(db,timeout=30)) as cx:
        has=cx.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone()
        if has and cx.execute('SELECT 1 FROM schema_version WHERE version=?',(VERSION,)).fetchone():
            return {'changed':False,'backup':None,'version':VERSION}
        backup=None
        if existed:
            folder=db.parent/'backups';folder.mkdir(exist_ok=True)
            backup=folder/(db.name+'.before_v37.'+uuid.uuid4().hex[:12]+'.sqlite3')
            with closing(sqlite3.connect(backup)) as dest:cx.backup(dest)
            with closing(sqlite3.connect(backup)) as check:
                if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                    raise RuntimeError('마이그레이션 전 DB 백업 검증 실패')
        with cx:
            cx.execute('BEGIN IMMEDIATE')
            cx.execute('CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL)')
            cx.execute('CREATE TABLE IF NOT EXISTS v37_runs(run_id TEXT PRIMARY KEY,started_at TEXT,finished_at TEXT,status TEXT,settings_json TEXT)')
            cx.execute('''CREATE TABLE IF NOT EXISTS v37_stages(run_id TEXT,stage TEXT,status TEXT,
                elapsed_seconds REAL,result_json TEXT,PRIMARY KEY(run_id,stage))''')
            cx.execute('''CREATE TABLE IF NOT EXISTS instrument_registry(series_key TEXT PRIMARY KEY,source TEXT,
                code TEXT,unit TEXT,mode TEXT,description TEXT,updated_at TEXT)''')
            cx.execute('''CREATE TABLE IF NOT EXISTS source_checkpoints(workspace_id TEXT,symbol TEXT,
                last_assessment_date TEXT,last_verified_at TEXT,PRIMARY KEY(workspace_id,symbol))''')
            cx.execute('INSERT OR IGNORE INTO schema_version VALUES(?,?)',(VERSION,now()))
    return {'changed':True,'backup':str(backup) if backup else None,'version':VERSION}

def now():return datetime.now(timezone.utc).isoformat()

def start_run(db,settings=None):
    migrate_database(db);run_id=uuid.uuid4().hex
    # Only operational nonsecret settings. Never persist login fields.
    settings={k:v for k,v in (settings or {}).items() if k in {'lookback_days','workspace_url','data_dir','workbook_path','naver_enabled'}}
    with closing(sqlite3.connect(db,timeout=30)) as cx,cx:
        cx.execute('INSERT INTO v37_runs VALUES(?,?,?,?,?)',(run_id,now(),None,'running',json.dumps(settings,ensure_ascii=False)))
    return run_id

def save_stage(db,run_id,stage,status,seconds,result):
    with closing(sqlite3.connect(db,timeout=30)) as cx,cx:
        cx.execute('INSERT OR REPLACE INTO v37_stages VALUES(?,?,?,?,?)',
            (run_id,stage,status,seconds,json.dumps(result,ensure_ascii=False,default=str)))

def finish_run(db,run_id,status):
    with closing(sqlite3.connect(db,timeout=30)) as cx,cx:
        cx.execute('UPDATE v37_runs SET status=?,finished_at=? WHERE run_id=?',(status,now(),run_id))

def incremental_days(db,workspace_id,requested,repair_days=7):
    if requested==0:return 0
    try:
        from datetime import date
        with closing(sqlite3.connect(db)) as cx:
            rows=cx.execute('SELECT last_assessment_date FROM source_checkpoints WHERE workspace_id=?',(workspace_id,)).fetchall()
        if not rows:return requested
        oldest=min(date.fromisoformat(r[0]) for r in rows)
        return min(requested,max(repair_days,(date.today()-oldest).days+repair_days))
    except (sqlite3.Error,ValueError):return requested

def checkpoint_prices(cx,workspace_id,prices,inventory):
    # A checkpoint is advanceable only when every discovered code yielded a price
    # and virtualization reported no uncertainty. Missing codes trigger full repair.
    expected={c for w in inventory for c in w.get('codes',[])}
    actual={p.symbol for p in prices}
    if not expected or expected-actual or any(w.get('scroll_caps') for w in inventory):
        cx.execute('DELETE FROM source_checkpoints WHERE workspace_id=?',(workspace_id,));return
    for symbol in actual:
        latest=max(p.date for p in prices if p.symbol==symbol)
        cx.execute('''INSERT INTO source_checkpoints VALUES(?,?,?,?) ON CONFLICT(workspace_id,symbol)
            DO UPDATE SET last_assessment_date=MAX(last_assessment_date,excluded.last_assessment_date),
            last_verified_at=excluded.last_verified_at''',(workspace_id,symbol,latest,now()))
