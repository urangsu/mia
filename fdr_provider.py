"""Public, browser-free historical Close adapter. Never writes NAVER/FMB tables.

FDR HTTP runs in an owned child so cancellation/deadlines do not hang the GUI.
No adjusted-close substitution, credentials, KRX login, or invented KR10Y series.
"""
from contextlib import closing, redirect_stdout
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
from pathlib import Path
import io
import json
import re
import sqlite3
import subprocess
import sys
import time

from market_sessions import capture_time, expected_pair, session_finished


@dataclass(frozen=True)
class Instrument:
    code: str
    symbol: str
    label: str
    unit: str
    currency: str | None
    calendar: str
    kind: str
    source_url: str


def instruments(stock_codes=('005490',)):
    definitions=[('KOSPI','^KS11','KOSPI','points',None,'XKRX','index'),
        ('KOSDAQ','^KQ11','KOSDAQ','points',None,'XKRX','index'),
        ('SP500','^GSPC','S&P 500','points',None,'XNYS','index'),
        ('NASDAQ','^IXIC','NASDAQ Composite','points',None,'XNAS','index'),
        ('US10Y','^TNX','미국10년 CBOE 지수','%',None,'XNYS','yield_index'),
        ('GOLD','GC=F','금 연속선물','USD/troy oz','USD','CMES','continuous_future'),
        ('WTI','CL=F','WTI 연속선물','USD/bbl','USD','CMES','continuous_future')]
    result={code:Instrument(code,'YAHOO:'+symbol,label,unit,currency,cal,kind,
                           'https://finance.yahoo.com/quote/'+symbol+'/history/')
            for code,symbol,label,unit,currency,cal,kind in definitions}
    # Public FDR NAVER index histories were verified independently of the
    # authenticated KRX readers and the lagging Yahoo Korean-index candles.
    for code in ('KOSPI','KOSDAQ'):
        result[code]=Instrument(code,'NAVER:'+code,code,'points',None,'XKRX','index',
            'https://finance.naver.com/sise/sise_index.naver?code='+code)
    if isinstance(stock_codes,str):stock_codes=[s.strip() for s in stock_codes.split(',') if s.strip()]
    if len(stock_codes)>25:raise ValueError('FDR 관심종목은 최대 25개입니다.')
    for code in stock_codes:
        if not isinstance(code,str) or not re.fullmatch(r'\d{6}',code):
            raise ValueError('FDR 관심종목은 앞자리 0을 보존한 6자리 코드입니다.')
        result[code]=Instrument(code,'NAVER:'+code,'POSCO홀딩스' if code=='005490' else code,
            'KRW/share','KRW','XKRX','equity','https://finance.naver.com/item/sise_day.naver?code='+code)
    return result


def frame_records(frame):
    """FDR daily index labels are source market dates, not UTC instants."""
    if frame is None or 'Close' not in frame.columns:raise ValueError('FDR 응답에 Close 열이 없습니다.')
    records=[]
    for stamp,value in frame['Close'].items():
        try:
            number=Decimal(str(value))
            if not number.is_finite():continue
            if stamp.hour or stamp.minute or stamp.second:raise ValueError('일별 시장일이 아닌 FDR 시간 인덱스')
            records.append({'date':stamp.date().isoformat(),'close':str(number)})
        except (InvalidOperation,TypeError):continue
    return records


def normalize(spec,records,captured_at,*,rejected=None):
    captured=capture_time(captured_at);by_date={};conflicts=set();warnings=[]
    for record in records:
        try:
            day=record['date'];number=Decimal(str(record['close']))
            if not number.is_finite() or (spec.kind not in ('continuous_future','yield_index') and number<=0):
                raise ValueError('유효하지 않은 Close')
            if not session_finished(spec.calendar,day,captured):
                warnings.append(spec.code+' '+str(day)+': 미종료·당일·비거래일 제외');continue
            if day in by_date and Decimal(by_date[day])!=number:conflicts.add(day)
            by_date[day]=str(number)
        except (KeyError,ValueError,TypeError,InvalidOperation):
            warnings.append(spec.code+': 잘못된 날짜/수치 제외')
    for day in conflicts:
        by_date.pop(day,None);warnings.append(spec.code+' '+day+': 동일일 Close 충돌 제외')
    if rejected is not None:rejected.update(conflicts)
    evidence=json.dumps({'provider':'FinanceDataReader','version':version('finance-datareader'),
        'field':'Close','source_symbol':spec.symbol,'kind':spec.kind,
        'close_verified':True,'calendar':spec.calendar,'calendar_version':version('exchange-calendars'),
        'publication_grace_minutes':20,'not_official_settlement':spec.kind=='continuous_future'},ensure_ascii=False,sort_keys=True)
    return [dict(instrument_id=spec.code,market_date=day,value=value,unit=spec.unit,currency=spec.currency,
        calendar=spec.calendar,kind=spec.kind,label=spec.label,source_symbol=spec.symbol,source_url=spec.source_url,
        captured_at=captured.isoformat(),raw_json=evidence,status='final',provider='FinanceDataReader')
        for day,value in sorted(by_date.items())],warnings


def has_expected_pair(spec,rows,captured_at):
    available={r['market_date'] for r in rows if r.get('value') is not None}
    return set(expected_pair(spec.calendar,captured_at))<=available


def fetch_history(spec,start,end,cancelled,timeout):
    command=[sys.executable,str(Path(__file__).resolve()),'--fetch',spec.code,start,end]
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    deadline=time.monotonic()+timeout
    try:
        while True:
            if cancelled():raise InterruptedError('FDR 수집 중단')
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError(spec.code+': FDR 조회 시간 초과')
            try:
                stdout,stderr=process.communicate(timeout=min(.2,remaining));break
            except subprocess.TimeoutExpired:continue
        if process.returncode:raise RuntimeError(spec.code+': FDR 작업자 실패 '+stderr[-180:])
        response=json.loads(stdout)
        if response.get('error'):raise RuntimeError(response['error'])
        if not isinstance(response.get('rows'),list):raise ValueError('FDR 응답 형식 불일치')
        return response['rows']
    finally:
        if process.poll() is None:process.kill()
        process.communicate()


def initialize_schema(cx):
    cx.execute('''CREATE TABLE IF NOT EXISTS fdr_observations(
        instrument_id TEXT,market_date TEXT,source_symbol TEXT,value TEXT,unit TEXT,currency TEXT,
        calendar TEXT,kind TEXT,label TEXT,source_url TEXT,captured_at TEXT,raw_json TEXT,
        PRIMARY KEY(instrument_id,market_date,source_symbol))''')
    cx.execute('''CREATE TABLE IF NOT EXISTS fdr_price_revisions(
        id INTEGER PRIMARY KEY,instrument_id TEXT,market_date TEXT,source_symbol TEXT,
        revised_at TEXT,old_json TEXT,new_json TEXT)''')
    cx.execute('''CREATE TABLE IF NOT EXISTS fdr_targets(
        instrument_id TEXT PRIMARY KEY,spec_json TEXT,captured_at TEXT,status TEXT,error TEXT)''')
    cx.execute('''CREATE TABLE IF NOT EXISTS fdr_quarantine(
        instrument_id TEXT,market_date TEXT,source_symbol TEXT,active INTEGER,reason TEXT,
        captured_at TEXT,raw_json TEXT,PRIMARY KEY(instrument_id,market_date,source_symbol))''')


def export_csv(db_path,path):
    import csv
    from FastmarketsCollector_v3_4 import atomic_text
    with closing(sqlite3.connect(db_path)) as cx:
        cx.row_factory=sqlite3.Row
        names={r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'fdr_observations' not in names:return None
        rows=cx.execute('''SELECT o.*,COALESCE(q.active,0) AS quarantined FROM fdr_observations o
            LEFT JOIN fdr_quarantine q USING(instrument_id,market_date,source_symbol)
            ORDER BY o.market_date,o.instrument_id,o.source_symbol''').fetchall()
    columns=('instrument_id','market_date','source_symbol','value','unit','currency','calendar','kind','source_url','captured_at','quarantined')
    buffer=io.StringIO(newline='');writer=csv.writer(buffer,lineterminator='\n')
    writer.writerow(columns);writer.writerows([r[k] for k in columns] for r in rows)
    content=buffer.getvalue();path=Path(path)
    if not path.exists() or path.read_text(encoding='utf-8-sig')!=content:
        with atomic_text(path,encoding='utf-8-sig',newline='') as stream:stream.write(content)
    return str(path)


def collect_and_save(db_path,cancelled,logger=print,*,stock_codes=('005490',),timeout=20,
                     force=False,captured_at=None,fetcher=None):
    from dataclasses import asdict
    started=time.monotonic();captured=capture_time(captured_at);specs=instruments(stock_codes)
    if not 1<=float(timeout)<=120:raise ValueError('FDR 시간 제한은 1~120초입니다.')
    fetcher=fetcher or fetch_history
    result=dict(status='partial',saved=0,cached=[],missing=[],warnings=[],instruments={},elapsed=0)
    with closing(sqlite3.connect(db_path,timeout=30)) as cx:
        with cx:initialize_schema(cx)
        for code,spec in specs.items():
            if cancelled():result['status']='cancelled';break
            blocked={r[0] for r in cx.execute('SELECT market_date FROM fdr_quarantine WHERE instrument_id=? AND source_symbol=? AND active=1',(code,spec.symbol))}
            existing=[dict(instrument_id=code,market_date=r[0],value=r[1]) for r in cx.execute(
                'SELECT market_date,value FROM fdr_observations WHERE instrument_id=? AND source_symbol=?',(code,spec.symbol)) if r[0] not in blocked]
            prior=cx.execute('SELECT captured_at,status FROM fdr_targets WHERE instrument_id=?',(code,)).fetchone()
            if not force and prior and prior[0][:10]==captured.date().isoformat() and prior[1]=='complete' and has_expected_pair(spec,existing,captured):
                result['cached'].append(code);result['instruments'][code]={'status':'cached'};continue
            error='';status='partial'
            try:
                raw=fetcher(spec,(captured.date()-timedelta(days=45)).isoformat(),captured.date().isoformat(),cancelled,float(timeout))
                if cancelled():result['status']='cancelled';break
                rejected=set()
                rows,warnings=normalize(spec,raw,captured,rejected=rejected)
                result['warnings'].extend(warnings)
                expected=expected_pair(spec.calendar,captured)
                status='complete' if has_expected_pair(spec,rows,captured) else 'partial'
                if status!='complete':
                    error=f'{code}: missing_history; 기대 거래일 {expected[0]}, {expected[1]} Close 필요'
                    result['warnings'].append(error)
                with cx:
                    for day in rejected:
                        incoming=json.dumps([r for r in raw if r.get('date')==day],sort_keys=True)
                        previous=cx.execute('SELECT active,raw_json FROM fdr_quarantine WHERE instrument_id=? AND market_date=? AND source_symbol=?',(code,day,spec.symbol)).fetchone()
                        if not previous or previous!=(1,incoming):
                            cx.execute('INSERT INTO fdr_price_revisions(instrument_id,market_date,source_symbol,revised_at,old_json,new_json) VALUES(?,?,?,?,?,?)',
                                (code,day,spec.symbol,captured.isoformat(),json.dumps(previous),json.dumps({'quarantine':incoming})))
                        cx.execute('INSERT OR REPLACE INTO fdr_quarantine VALUES(?,?,?,?,?,?,?)',
                            (code,day,spec.symbol,1,'동일일 Close 충돌',captured.isoformat(),incoming))
                    for row in rows:
                        cleared=cx.execute('UPDATE fdr_quarantine SET active=0 WHERE instrument_id=? AND market_date=? AND source_symbol=? AND active=1',
                            (code,row['market_date'],spec.symbol)).rowcount
                        if cleared:
                            cx.execute('INSERT INTO fdr_price_revisions(instrument_id,market_date,source_symbol,revised_at,old_json,new_json) VALUES(?,?,?,?,?,?)',
                                (code,row['market_date'],spec.symbol,captured.isoformat(),json.dumps({'quarantine':True}),json.dumps({'quarantine':False,'value':row['value']})))
                        old=cx.execute('SELECT value,unit,currency,raw_json FROM fdr_observations WHERE instrument_id=? AND market_date=? AND source_symbol=?',
                            (code,row['market_date'],spec.symbol)).fetchone()
                        if old and (Decimal(old[0]),old[1],old[2])==(Decimal(row['value']),row['unit'],row['currency']):continue
                        if old:cx.execute('INSERT INTO fdr_price_revisions(instrument_id,market_date,source_symbol,revised_at,old_json,new_json) VALUES(?,?,?,?,?,?)',
                            (code,row['market_date'],spec.symbol,captured.isoformat(),json.dumps(list(old)),json.dumps(row,ensure_ascii=False)))
                        columns=('instrument_id','market_date','source_symbol','value','unit','currency','calendar','kind','label','source_url','captured_at','raw_json')
                        cx.execute('INSERT OR REPLACE INTO fdr_observations VALUES('+','.join('?' for _ in columns)+')',tuple(row[k] for k in columns));result['saved']+=1
                result['instruments'][code]={'status':status,'rows':len(rows),'expected_dates':expected,'source':spec.symbol}
            except InterruptedError:
                result['status']='cancelled';break
            except Exception as exc:
                status='failed';error=f'{code}: {type(exc).__name__}: {str(exc)[:180]}'
                result['warnings'].append(error);result['instruments'][code]={'status':status,'error':error}
            with cx:cx.execute('INSERT OR REPLACE INTO fdr_targets VALUES(?,?,?,?,?)',
                (code,json.dumps(asdict(spec),ensure_ascii=False),captured.isoformat(),status,error))
            if status!='complete':result['missing'].append(code)
            logger('[FDR] '+code+': '+status)
    if result['status']!='cancelled':
        result['warnings'].append('KR10Y: FDR 검증된 일별 지원 경로 없음; 한국10년은 미지원으로 유지')
        result['status']='partial'
    result['elapsed']=round(time.monotonic()-started,3)
    return result


def _worker(argv):
    code,start,end=argv
    specs=instruments([code] if re.fullmatch(r'\d{6}',code) else [])
    if code not in specs:raise ValueError('허용되지 않은 FDR 종목')
    # Bound every requests call without modifying the parent process/environment.
    import requests
    original=requests.sessions.Session.request
    def bounded(self,*args,**kwargs):
        kwargs.setdefault('timeout',(5,10))
        return original(self,*args,**kwargs)
    requests.sessions.Session.request=bounded
    import FinanceDataReader as fdr
    with redirect_stdout(io.StringIO()):frame=fdr.DataReader(specs[code].symbol,start,end)
    return {'rows':frame_records(frame)}


if __name__=='__main__':
    try:
        if len(sys.argv)!=5 or sys.argv[1]!='--fetch':raise ValueError('내부 FDR 작업자 명령 불일치')
        response=_worker(sys.argv[2:])
    except Exception as exc:response={'error':type(exc).__name__+': '+str(exc)[:220]}
    print(json.dumps(response,ensure_ascii=False,allow_nan=False))
