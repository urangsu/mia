"""Synthetic CPU/storage benchmark. Does not measure or contact Fastmarkets/ECM."""
import argparse
import importlib.util
import json
import platform
import statistics
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from contextlib import closing
import sqlite3

ROOT=Path(__file__).parent


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod


def fixture(count):
    rows=[]
    for i in range(count):
        cells=[{'colId':'date','text':(date(2026,10,16)-timedelta(days=i)).isoformat()}]
        for j in range(20):
            cells.append({'colId':f'MB-BMS-{j:04d}-mid','text':f'{70+j}.50'})
        rows.append({'index':i,'cells':cells})
    return {'widgets':[{'title':'Black Mass Payable','headers':[],
        'directCodes':[f'MB-BMS-{j:04d}' for j in range(20)],'mode':'Actual','unit':'% payable',
        'grids':[{'index':0,'rows':rows}]}]}


def benchmark(mod,count):
    snapshot=fixture(count);times=[]
    for _ in range(3):
        start=time.perf_counter()
        rows,inventory,warnings=mod.read_snapshot(snapshot,0,now=date(2026,10,16))
        times.append(time.perf_counter()-start)
    with tempfile.TemporaryDirectory() as t:
        folder=Path(t);diag={'widget_count':1,'found_symbols':sorted({p.symbol for p in rows}),'warnings':warnings}
        start=time.perf_counter();mod.save_sqlite(mod.path_bundle(folder)['db'],rows,inventory,diag)
        sqlite_seconds=time.perf_counter()-start
        start=time.perf_counter();mod.export_files(folder);csv_seconds=time.perf_counter()-start
        xlsx_seconds=None
        if hasattr(mod,'export_workbook'):
            start=time.perf_counter();mod.export_workbook(folder,today=date(2026,10,16))
            xlsx_seconds=time.perf_counter()-start
        with closing(sqlite3.connect(mod.path_bundle(folder)['db'])) as cx:
            integrity=cx.execute('PRAGMA integrity_check').fetchone()[0]
    return {'rows':len(rows),'parse_median_seconds':round(statistics.median(times),4),
            'sqlite_seconds':round(sqlite_seconds,4),'csv_seconds':round(csv_seconds,4),
            'xlsx_seconds':round(xlsx_seconds,4) if xlsx_seconds else None,'db_integrity':integrity}


def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path);p.add_argument('--dates',type=int,default=250)
    p.add_argument('--output',type=Path);args=p.parse_args()
    report={'python':platform.python_version(),'platform':platform.system(),'synthetic':True,
            'scenario':f'{args.dates} dates x 20 synthetic symbols','v3.3':benchmark(load(ROOT/'FastmarketsCollector_v3_4.py','bench33'),args.dates)}
    if args.baseline:report['v3.2']=benchmark(load(args.baseline,'bench32'),args.dates)
    output=json.dumps(report,ensure_ascii=False,indent=2);print(output)
    if args.output:
        from FastmarketsCollector_v3_4 import atomic_text
        with atomic_text(args.output) as fp:fp.write(output+'\n')

if __name__=='__main__':main()
