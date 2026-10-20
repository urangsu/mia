# -*- coding: utf-8 -*-
"""Fastmarkets + ECM + SMBS 시세 수집기 v3.5 — Windows / Chrome 9444 / 일반 Edge.

실행: py FastmarketsCollector_v3_4.py
의존성 설치: py -m pip install "selenium>=4.25,<5" "keyring>=25,<27"
GUI는 외부 패키지 설치 전에도 실행됩니다. 실계정에서 검증되지 않은 DOM 구조는
진단 파일에 남기며, 읽지 못한 데이터를 추정하거나 채우지 않습니다.
"""
from __future__ import annotations

import argparse
import csv
from contextlib import contextmanager
import hashlib
import json
import os
import re
from urllib.request import build_opener, ProxyHandler
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
import tempfile
from contextlib import closing
from queue import Queue, Empty
from urllib.parse import urlparse

APP = "FastmarketsCollector"
WORKSPACE_ID = "moCxu7v7xQKU99uHbd6LRv"
WORKSPACE_URL = (f"https://dashboard.fastmarkets.com/w/{WORKSPACE_ID}/"
                 "%E1%84%8B%E1%85%B5%E1%86%AF%E1%84%8B%E1%85%B5%E1%86%AF-%E1%84%89%E1%85%B5%E1%84%89%E1%85%A6")

def verify_workspace_url(url):
    parsed=urlparse(str(url).strip())
    if parsed.scheme!='https' or parsed.hostname!='dashboard.fastmarkets.com' or parsed.port is not None:
        raise ValueError('Fastmarkets 대시보드 URL은 https://dashboard.fastmarkets.com 도메인만 허용합니다.')
    m=re.fullmatch(r'/w/([a-zA-Z0-9_-]{12,80})(?:/[^?#]*)?',parsed.path)
    if not m:raise ValueError('Fastmarkets 작업공간 URL 형식이 아닙니다.')
    if parsed.query or parsed.fragment:raise ValueError('인증정보/쿼리가 포함된 작업공간 URL은 사용할 수 없습니다.')
    return str(url).strip(),m.group(1)

_workspace_context=threading.local()

def current_workspace():
    frozen=getattr(_workspace_context,'identity',None)
    return frozen or verify_workspace_url(config_load()['workspace_url'])

@contextmanager
def workspace_scope(url=None):
    """Pin provenance for a worker even if another desktop edits config."""
    previous=getattr(_workspace_context,'identity',None)
    _workspace_context.identity=verify_workspace_url(url) if url else current_workspace()
    try:yield _workspace_context.identity
    finally:_workspace_context.identity=previous

AUTH_URL = "https://dashboard.fastmarkets.com/en/"
PORT = 9444  # Fastmarkets 전용. pp.py=9222, endp.py=9337 사용 유지.
APP_HOME = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local") / APP
DEFAULT_DATA = Path.home() / "Documents" / APP
# 별도의 Chrome 프로필: 구 버전(v3.1)의 ChromeProfile은 9222에서 실행 중일 수 있음.
CHROME_PROFILE = APP_HOME / "ChromeProfile_9444"
BROWSER_LOCK_PATH = APP_HOME / "browser_9444.lock"
DRIVER_DIAGNOSTIC_PATH = APP_HOME / "driver_connection_diagnostic.json"
DRIVER_OVERRIDE_ENV = "FASTMARKETS_CHROMEDRIVER"  # Only this app; never modifies the global PATH.
CONFIG_PATH = APP_HOME / "config.json"
KEY_SERVICE = "FastmarketsCollector:auth.fastmarkets.com"
IS_WINDOWS = os.name == "nt"
DATE_RE = re.compile(r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{4}\b")
CODE_RE = re.compile(r"MB-[A-Z0-9-]+", re.I)
COL_RE = re.compile(r"^(MB-[A-Z0-9-]+)-(low|mid|high|change|percentage-change)$", re.I)
RANGE_RE = re.compile(r"^\s*([+-]?[\d,]+(?:\.\d+)?)\s*(?:-|–|—|to)\s*([+-]?[\d,]+(?:\.\d+)?)\s*$", re.I)


def config_load() -> dict:
    defaults = {"data_dir": str(DEFAULT_DATA), "lookback_days": 31, "auto_time": "08:30", "workbook_path":"", "workspace_url":WORKSPACE_URL, "ecm_search":"금속 가격 현황", "ecm_title":"(리뉴얼)금속 가격 현황", "maximize_chrome":True}
    defaults['v37_auto_time']='08:30'
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            defaults.update({k: data[k] for k in defaults if k in data})
    except (OSError, ValueError, TypeError):
        pass
    return defaults


def config_save(data: dict):
    APP_HOME.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def path_bundle(folder: Path) -> dict[str, Path]:
    return {"db": folder / "fastmarkets_prices_v3.sqlite3",
            "csv": folder / "fastmarkets_prices_v3.csv",
            "master": folder / "fastmarkets_instruments.csv",
            "log": folder / "collector.log",
            "diag": folder / "last_diagnostic.json",
            "xlsx": folder / "fastmarkets_prices.xlsx"}


@contextmanager
def atomic_text(path, newline=None, encoding='utf-8'):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding=encoding, newline=newline) as fp:
            yield fp
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def latest_quotes(prices, today=None):
    today = today or date.today()
    latest = {}
    for p in prices:
        if p.price_mode not in {'Actual', 'Unspecified'} or p.period_label or p.date > today.isoformat():
            continue
        key = (p.symbol, p.unit, p.price_mode, p.view_key)
        if key not in latest or p.date > latest[key].date:
            latest[key] = p
    return [dict(asdict(p), freshness='当日' if p.date == today.isoformat() else '前日以前')
            for p in sorted(latest.values(), key=lambda p: (p.symbol, p.unit, p.view_key))]


def coverage_report(prices, inventory, previous_symbols=()):
    """Observed coverage; workspace inventory is not a fixed historical requirement."""
    discovered={c for w in inventory for c in w.get('codes',[])}
    captured={p.symbol for p in prices}
    missing=sorted(discovered-captured)
    previous_missing=sorted(set(previous_symbols)-discovered)
    limited=[{'widget':w.get('widget'),'caps':w.get('scroll_caps')} for w in inventory if w.get('scroll_caps')]
    return {'discovered':sorted(discovered),'captured':sorted(captured),
            'missing_prices':missing,'previous_missing':previous_missing,
            'missing_families':[],'required_missing':[], 'scroll_limitations':limited,
            'scope_complete':bool(discovered) and not missing and not limited,
            'complete':False, 'note':'현재 표시된 위젯/종목 범위 점검. 실제 고시 없는 종목과 DOM 수집 실패는 진단으로 구분.'}


def stored_symbols(folder,workspace_id=None):
    workspace_id=workspace_id or current_workspace()[1]
    db = path_bundle(folder)['db']
    if not db.exists(): return []
    with closing(sqlite3.connect(db)) as cx:
        # v3.7 creates its run ledger before the first FMB save. The database
        # can therefore exist legitimately without an instruments table yet.
        if not cx.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='instruments'").fetchone():
            return []
        return [r[0] for r in cx.execute('SELECT DISTINCT symbol FROM instruments WHERE workspace_id=?', (workspace_id,))]


def read_official_csv(path):
    """Explicit long-form columns only; unknown wide export schemas are rejected."""
    started = time.perf_counter()
    aliases = {'symbol':{'symbol','code','price code','instrument code'},
               'date':{'date','assessment_date','assessment date','price date'},
               'low':{'low','low price'}, 'mid':{'mid','mid price'}, 'high':{'high','high price'},
               'unit':{'unit','units'}, 'description':{'description','price description'},
               'price_mode':{'price_mode','price mode','mode'}, 'change_pct':{'change_pct','percentage change'},
               'period_label':{'period_label','period label'}}
    raw = Path(path).read_text(encoding='utf-8-sig')
    try: dialect = csv.Sniffer().sniff(raw[:8192], delimiters=',;\t')
    except csv.Error: dialect = csv.excel
    reader = csv.DictReader(raw.splitlines(), dialect=dialect)
    fields = {f.strip().lower():f for f in reader.fieldnames or []}
    mapping = {k:next((fields[a] for a in names if a in fields),None) for k,names in aliases.items()}
    if not all(mapping[k] for k in ('symbol','date','unit')) or not any(mapping[k] for k in ('low','mid','high')):
        raise ValueError('CSV 열 형식 미확인: symbol/code, date, unit, low/mid/high가 필요합니다. 원본은 변경하지 않았습니다.')
    rows = []; errors = []
    for line,r in enumerate(reader,2):
        def get(k): return (r.get(mapping[k]) or '').strip() if mapping.get(k) else ''
        code, rawdate = get('symbol').upper(), get('date')
        dt = normalize_date(rawdate) if '/' not in rawdate else None
        values = [normalize_number(get(k)) for k in ('low','mid','high')]
        if (not CODE_RE.fullmatch(code) or not dt or not get('unit') or not any(v is not None for v in values)
            or any(get(k) and normalize_number(get(k)) is None and get(k).lower() not in {'-','—','n/a','na'}
                   for k in ('low','mid','high'))):
            errors.append(line); continue
        if values[0] is not None and values[2] is not None and Decimal(values[0]) > Decimal(values[2]):
            errors.append(line); continue
        mode = classify_mode(get('price_mode'))
        rows.append(Price(code,dt,*values,normalize_number(get('change_pct')),get('unit'),get('description'),
                          'Official CSV',mode,'Official CSV','official-csv',get('period_label')))
    if errors or not rows:
        raise ValueError(f'CSV 검증 실패: 잘못된 행 {errors[:20]}, 유효 행 {len(rows)}. 전체 저장을 취소했습니다.')
    keys = [(p.symbol,p.date,p.unit,p.price_mode,p.period_label) for p in rows]
    if len(keys) != len(set(keys)):
        raise ValueError('CSV에 중복 종목/날짜/단위/모드 행이 있습니다. 구분 열을 확인하세요.')
    return rows, {'rows':len(rows),'seconds':round(time.perf_counter()-started,6), 'source':'Official CSV',
                  'warnings':['구분 열이 없는 값은 Unspecified입니다.'] if any(p.price_mode=='Unspecified' for p in rows) else []}


def compare_sources(official, dom):
    def index(rows):
        result={}
        for p in rows:
            result.setdefault((p.symbol,p.date,p.unit,p.price_mode,p.period_label),[]).append(p)
        return result
    a,b=index(official),index(dom)
    details=[]; matched=mismatched=0
    for key in sorted(a.keys() & b.keys()):
        def vals(p):return tuple(Decimal(v) if v is not None else None for v in (p.low,p.mid,p.high,p.change_pct))
        av,bv={vals(p) for p in a[key]},{vals(p) for p in b[key]}
        same=len(av)==len(bv)==1 and av==bv
        matched+=int(same);mismatched+=int(not same)
        if not same:details.append({'key':key,'reason':'값 불일치 또는 동일 종목의 여러 뷰 충돌'})
    return {'matched':matched,'mismatched':mismatched,'official_only':len(a.keys()-b.keys()),
            'dom_only':len(b.keys()-a.keys()),'details':details}


def import_official(path, folder, workbook_path=None):
    rows, report=read_official_csv(path)
    existing=load_prices(folder)
    report['comparison']=compare_sources(rows,[p for p in existing if p.source!='Official CSV'])
    if report['comparison']['mismatched']:
        report['warnings'].append(f"공식 CSV / DOM 불일치 {report['comparison']['mismatched']}건: last_diagnostic.json 대조표 확인")
    if not report['comparison']['matched']:
        report['warnings'].append('동일 조건의 DOM 대조 일치 행 0건: 원본 다운로드 검증 필요')
    inventory=[{'codes':sorted({p.symbol for p in rows}),
                'description_by_code':{p.symbol:p.description for p in rows},'widget':'Official CSV'}]
    diag={'widget_count':1,'processed_widgets':1,'found_symbols':inventory[0]['codes'],
          'price_symbols':inventory[0]['codes'],'warnings':report['warnings'], 'csv_report':report,'data_dir':str(folder)}
    save_sqlite(path_bundle(folder)['db'],rows,inventory,diag)
    try:export_all(folder,workbook_path)
    except Exception as exc:
        diag['warnings'].append('DB 저장 완료; 내보내기 재시도 필요: '+str(exc))
    with atomic_text(path_bundle(folder)['diag']) as fp:
        json.dump(diag,fp,ensure_ascii=False,indent=2)
    return rows,diag


def load_prices(folder,workspace_id=None,include_legacy=True):
    """All-year price history. Changed workspace does not hide previously stored data.

    Old workspace quotes are used only where the active workspace has no same series/date.
    Raw DB retains provenance for both workspaces. Explicit workspace_id is scoped.
    """
    db=path_bundle(folder)['db']
    if not db.exists():return []
    active=workspace_id or current_workspace()[1]
    with closing(sqlite3.connect(db)) as cx:
        cx.row_factory=sqlite3.Row
        if include_legacy and workspace_id is None:
            rows=cx.execute('SELECT * FROM prices ORDER BY CASE WHEN workspace_id=? THEN 0 ELSE 1 END, '
                            'assessment_date DESC,symbol,price_mode,unit,view_key',(active,))
        else:
            rows=cx.execute('SELECT * FROM prices WHERE workspace_id=? ORDER BY assessment_date DESC,symbol,price_mode,unit,view_key',(active,))
        result={}
        for r in rows:
            k=(r['symbol'],r['assessment_date'],r['price_mode'],r['unit'],r['view_key'])
            if k not in result:
                result[k]=Price(r['symbol'],r['assessment_date'],r['low'],r['mid'],r['high'],r['change_pct'],
                                r['unit'],r['description'],r['widget'],r['price_mode'],r['source'],r['view_key'],r['period_label'])
        return sorted(result.values(),key=lambda p:(p.date,p.symbol,p.view_key),reverse=True)


def export_workbook(folder, today=None, output_path=None):
    """Secure on-site Excel COM; other platforms retain offline plain-XLSX export."""
    path=Path(output_path) if output_path else path_bundle(folder)['xlsx']
    if IS_WINDOWS:
        from excel_secure import write_com_sheets,make_sheets
        from smbs_rates import load_rates
        prices=load_prices(folder)
        sheets=make_sheets(prices,latest_quotes(prices,today),load_rates(path_bundle(folder)['db']))
        log(folder, f'Excel 내보내기: {path.resolve()} ({"기존 갱신" if path.exists() else "자동 신규 생성"})')
        return write_com_sheets(path,sheets,logger=lambda msg:log(folder,msg))
    try:
        from openpyxl import Workbook, load_workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.worksheet.table import Table, TableStyleInfo
    except ImportError as exc:
        raise RuntimeError('Excel 내보내기 패키지 필요: py -m pip install openpyxl. DB/CSV는 보존됩니다.') from exc
    path=Path(output_path) if output_path else path_bundle(folder)['xlsx']
    if path.suffix.lower()!='.xlsx':raise ValueError('누적 파일은 .xlsx만 지원합니다. 매크로 파일은 별도 .xlsx 사본을 사용하세요.')
    path.parent.mkdir(parents=True,exist_ok=True)
    prices=load_prices(folder)
    wb=load_workbook(path) if path.exists() else Workbook()
    if not path.exists():wb.remove(wb.active)
    temp=None
    try:
        cols=['symbol','date','low','mid','high','change_pct','unit','description',
              'widget','price_mode','source','view_key','period_label']
        sheets={
            'RawData':(cols,[tuple(getattr(p,c) for c in cols) for p in prices]),
            'Daily':(['date','symbol','description','low','mid','high','unit','change_pct','price_mode','widget','source'],
                     [(p.date,p.symbol,p.description,p.low,p.mid,p.high,p.unit,p.change_pct,p.price_mode,p.widget,p.source)
                      for p in prices if p.price_mode in {'Actual','Unspecified'} and not p.period_label]),
            'Latest':(['symbol','description','date','low','mid','high','unit','change_pct','price_mode','freshness','widget','source'],
                      [(r['symbol'],r['description'],r['date'],r['low'],r['mid'],r['high'],r['unit'],r['change_pct'],
                        r['price_mode'], '당일' if r['freshness']=='当日' else '이전 발표',r['widget'],r['source'])
                       for r in latest_quotes(prices,today)])}
        for name,(headers,rows) in sheets.items():
            if name in wb:wb.remove(wb[name])
            ws=wb.create_sheet(name);ws.append(headers)
            for row_index,row in enumerate(rows,2):
                ws.append(row)
                # Treat every external string as text, never a spreadsheet formula.
                for col_index,value in enumerate(row,1):
                    cell=ws.cell(row_index,col_index)
                    if name!='RawData' and headers[col_index-1] in {'low','mid','high','change_pct'} and value is not None:
                        cell.value=float(Decimal(value));cell.number_format='0.00########'
                    elif isinstance(cell.value,str):cell.data_type='s'
            ws.freeze_panes='C2';ws.sheet_view.showGridLines=False
            ws.auto_filter.ref=ws.dimensions
            for cell in ws[1]:
                cell.font=Font(color='FFFFFF',bold=True)
                cell.fill=PatternFill('solid',fgColor='183B56')
                cell.alignment=Alignment(vertical='center')
            ws.row_dimensions[1].height=28
            for cells in ws.columns:
                header=cells[0].value
                ws.column_dimensions[cells[0].column_letter].width=55 if header=='description' else 25 if header in {'widget','view_key'} else 18
            if rows:
                tab=Table(displayName='FM_'+name,ref=ws.dimensions)
                tab.tableStyleInfo=TableStyleInfo(name='TableStyleMedium2',showRowStripes=True)
                ws.add_table(tab)
        # Full-year history is rebuilt from SQLite, preserving existing sheet names and stable series-column mapping.
        from smbs_rates import load_rates, add_summary_sheets
        add_summary_sheets(wb, prices, load_rates(path_bundle(folder)['db']))
        wb.active=wb.sheetnames.index('일별시세') if prices or load_rates(path_bundle(folder)['db']) else wb.sheetnames.index('Latest')
        fd,name=tempfile.mkstemp(prefix='fastmarkets.',suffix='.xlsx',dir=path.parent)
        os.close(fd);temp=Path(name)
        wb.save(temp)
        os.replace(temp,path)
        return path
    except PermissionError as exc:
        raise PermissionError('Excel 파일이 열려 있거나 쓰기 권한이 없습니다. 닫고 다시 내보내세요. 기존 Excel/DB는 보존됩니다.') from exc
    finally:
        wb.close()
        if temp is not None:temp.unlink(missing_ok=True)


def export_all(folder,workbook_path=None):
    export_files(folder)
    log(folder, f'CSV 출력 완료: {path_bundle(folder)["csv"]} (Excel 단계와 별개)')
    try:
        return str(export_workbook(folder,output_path=workbook_path))
    except Exception as exc:
        log(folder, f'CSV는 보존됨 / 누적 Excel만 갱신 실패: {type(exc).__name__}: {str(exc)[:280]}')
        raise


def log(folder: Path, msg: str, callback=None):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with path_bundle(folder)["log"].open("a", encoding="utf-8") as fp:
            fp.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)
    if callback:
        callback(line)


def normalize_number(value):
    if value is None:
        return None
    raw = str(value).strip().replace(",", "").replace("−", "-").replace("%", "")
    if not raw or raw.lower() in {"-", "—", "–", "n/a", "na", "null", "none"}:
        return None
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", raw):
        return None
    try:
        return str(Decimal(raw))
    except InvalidOperation:
        return None


def normalize_date(s: str) -> str | None:
    match = DATE_RE.search(str(s or ""))
    if not match:
        return None
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(match.group(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def period_end(s: str) -> str | None:
    # e.g. '1 Oct - 16 Oct 2026': the period end, not a daily published price.
    match = re.search(r"\b\d{1,2}\s+[A-Za-z]{3,9}\s*(?:-|–|to)\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", s or "", re.I)
    return normalize_date(match.group(1)) if match else None


def unit_from_description(desc: str) -> str:
    s = desc.lower()
    if "$ / tonne" in s or "$/tonne" in s or "usd/tonne" in s:
        return "$/tonne"
    if "$ / kg" in s or "$/kg" in s or "usd/kg" in s:
        return "$/kg"
    if "$ / lb" in s or "$/lb" in s or "usd/lb" in s:
        return "$/lb"
    if "% payable" in s or "payable indicator" in s or "%payable" in s:
        return "% payable"
    return ""  # Do not assign a guessed unit.


@dataclass(frozen=True)
class Price:
    symbol: str
    date: str
    low: str | None
    mid: str | None
    high: str | None
    change_pct: str | None
    unit: str
    description: str
    widget: str
    price_mode: str
    source: str
    view_key: str
    period_label: str = ""


def classify_mode(text: str) -> str:
    raw = (text or "").lower()
    if "monthly average" in raw or "monthly avg" in raw:
        return "Monthly Average"
    if "forecast" in raw or "전망" in raw:
        return "Forecast"
    if "actual" in raw or "실적" in raw:
        return "Actual"
    return "Unspecified"  # Never silently label unknown data as Actual.


def read_snapshot(snapshot: dict, lookback: int, now: date | None = None):
    """Parse merged DOM snapshots, respecting exact series codes and row identity."""
    now = now or date.today()
    cutoff = (now - timedelta(days=lookback)) if lookback else date(1900, 1, 1)
    output: dict[tuple, Price] = {}
    found_symbols = set()
    with_prices = set()
    warnings = []
    inventory = []
    for idx, w in enumerate(snapshot.get("widgets", [])):
        title = (w.get("title") or f"위젯 {idx+1}").strip()
        headers = {}
        for h in w.get("headers", []):
            code = str(h.get("code") or "").upper()
            if CODE_RE.fullmatch(code):
                headers[code] = (h.get("description") or "").strip()
        raw_codes = set(str(x).upper() for x in w.get("directCodes", []))
        codes = {c for c in raw_codes | set(headers) if CODE_RE.fullmatch(c)}
        found_symbols.update(codes)
        mode = classify_mode(w.get("mode") or "")
        # A stable view key across runs unless the user changes panel order/series.
        view_base = f"{idx:02d}|{title}|{','.join(sorted(codes))}|{mode}"
        view_key = hashlib.sha1(view_base.encode("utf-8")).hexdigest()[:16]
        reported = set()
        parse_stats = {'rows_total':0,'date_missing':0,'date_ambiguous':0,
                       'date_outside_period':0,'no_numeric_prices':0,'rows_accepted':0}
        for g in w.get("grids", []):
            rows = g.get("rows") or []
            for r in rows:
                parse_stats['rows_total'] += 1
                if r.get('conflicted'):
                    warnings.append(f"{title}: 행 {r.get('index')} 스크롤 값 충돌 — 저장 제외")
                    continue
                cells = r.get("cells") or []
                date_candidates = {normalize_date(c.get("text") or "") for c in cells if c.get("colId", "").lower() in {"date", "assessment-date", "assessmentdate", "datevalue", "date-col"}}
                date_candidates.discard(None)
                # Some grids use different date col-id; accept an unambiguous date-format cell.
                if not date_candidates:
                    date_candidates = {normalize_date(c.get("text") or "") for c in cells if normalize_date(c.get("text") or "")}
                date_candidates.discard(None)
                # A period (e.g. 1 Oct - 16 Oct 2026) is not a daily price.
                period = next((str(c.get("text") or "") for c in cells
                               if period_end(str(c.get("text") or ""))), "")
                if period:
                    end_date = period_end(period)
                    if date_candidates and date_candidates != {end_date}:
                        warnings.append(f"{title}: 기간 종료일과 날짜 열이 충돌 — 행 제외")
                        continue
                    date_candidates = {end_date}
                if len(date_candidates) != 1:
                    parse_stats['date_ambiguous' if len(date_candidates)>1 else 'date_missing'] += 1
                    if len(date_candidates) > 1:
                        warnings.append(f"{title}: 행 {r.get('index')} 날짜 충돌 — 해당 행 제외")
                    continue
                date_str = next(iter(date_candidates))
                if date_str is None or not cutoff <= date.fromisoformat(date_str) <= now:
                    parse_stats['date_outside_period'] += 1
                    continue
                groups = {}
                generic = {}
                for c in cells:
                    column = str(c.get("colId") or "")
                    value = normalize_number(c.get("title") or c.get("text"))
                    pattern = COL_RE.fullmatch(column)
                    if pattern:
                        symbol, field = pattern.groups()
                        groups.setdefault(symbol.upper(), {})[field.lower()] = value
                    elif column.lower() in {"low", "mid", "high", "change"}:
                        generic[column.lower()] = value
                if not groups and len(codes) == 1 and generic:
                    groups[next(iter(codes))] = generic
                if not any(any(values.get(v) is not None for v in ('low','mid','high')) for values in groups.values()):
                    parse_stats['no_numeric_prices'] += 1
                for symbol, values in groups.items():
                    found_symbols.add(symbol)
                    if all(values.get(v) is None for v in ("low", "mid", "high")):
                        continue
                    if values.get('low') is not None and values.get('high') is not None and Decimal(values['low'])>Decimal(values['high']):
                        warnings.append(f'{title}/{symbol}/{date_str}: Low > High — 행 제외')
                        continue
                    desc = headers.get(symbol, "")
                    unit = unit_from_description(desc) or str(w.get("unit") or "")
                    p = Price(symbol, date_str, values.get("low"), values.get("mid"), values.get("high"),
                              values.get("change") or values.get("percentage-change"), unit, desc, title, mode,
                              "AG Grid", view_key, period)
                    key = (p.symbol, p.date, p.view_key, p.unit, p.price_mode)
                    prev = output.get(key)
                    if prev and (prev.low, prev.mid, prev.high) != (p.low, p.mid, p.high):
                        warnings.append(f"{title}/{symbol}/{date_str}: 스크롤 중 서로 다른 가격 감지, 확인 필요")
                        continue
                    output[key] = p
                    parse_stats['rows_accepted'] += 1
                    with_prices.add(symbol)
                    reported.add(symbol)
        chart_rows = w.get("chartRows") or []
        if chart_rows:
            # Chart history can safely be assigned only when a single code is present.
            if len(codes) != 1:
                warnings.append(f"{title}: 차트에 여러 종목 코드({len(codes)}개), 시리즈 매핑 불명으로 차트 행 제외")
            else:
                symbol = next(iter(codes))
                for r in chart_rows:
                    date_str = normalize_date(r.get("date") or "")
                    if not date_str or not cutoff <= date.fromisoformat(date_str) <= now:
                        continue
                    raw = r.get("priceTitle") or r.get("priceText") or ""
                    m = RANGE_RE.fullmatch(str(raw).strip())
                    if m:
                        low, high, mid = normalize_number(m[1]), normalize_number(m[2]), None
                        if Decimal(low)>Decimal(high):
                            warnings.append(f'{title}/{symbol}/{date_str}: Low > High — 차트 행 제외')
                            continue
                    else:
                        low, high, mid = None, None, normalize_number(raw)
                    if all(v is None for v in (low, mid, high)):
                        continue
                    desc = headers.get(symbol, "") or str(w.get("description") or title)
                    unit = unit_from_description(desc) or str(w.get("unit") or "")
                    p = Price(symbol, date_str, low, mid, high, normalize_number(r.get("change")), unit,
                              desc, title, mode, "Chart", view_key)
                    key = (p.symbol, p.date, p.view_key, p.unit, p.price_mode)
                    if key not in output:  # Prefer explicit AG Grid values over chart for same view.
                        output[key] = p
                    with_prices.add(symbol)
                    reported.add(symbol)
        inventory.append({"widget": title, "mode": mode, "codes": sorted(codes),
                          "description_by_code": headers, "captured_codes": sorted(reported),
                          "grid_rows": sum(len(g.get("rows", [])) for g in w.get("grids", [])),
                          "chart_rows": len(chart_rows), "scroll_caps": w.get("scrollCaps", []),
                          "grid_probes": w.get("gridProbes", []),"parse_stats":parse_stats})
        if not reported:
            warnings.append(f"{title}: 지정 기간에 매핑 가능한 가격 없음 (비어있는 위젯 또는 구조 검증 필요)")
        missing = codes - reported
        if missing:
            warnings.append(f"{title}: 메타데이터에 있으나 가격이 없는 코드 {', '.join(sorted(missing))}")
        for cap in w.get("scrollCaps", []):
            warnings.append(f"{title}: 가상 스크롤 전수 범위 미확인 ({cap})")
    if not snapshot.get("widgets"):
        warnings.append("위젯을 찾지 못했습니다. 작업공간과 로그인 상태를 확인하세요.")
    return sorted(output.values(), key=lambda p: (p.date, p.symbol, p.view_key), reverse=True), inventory, sorted(set(warnings))


# JavaScript is limited to the visible, authenticated browser DOM. No requests to private APIs.
INVENTORY_JS = r"""
return (() => {
  const t = e => (e?.innerText || e?.textContent || '').trim();
  const cssVisible = e => { if (!e || !e.isConnected) return false;
    const s = getComputedStyle(e), r=e.getBoundingClientRect();
    return s.display!=='none' && s.visibility!=='hidden' && r.width>10 && r.height>5; };
  const widgets=[], used=new Set(), content='[data-testid="price-history-row"],.ag-root,.ag-root-wrapper';
  const headings=[...document.querySelectorAll('.title-text')];
  for (const header of headings) {
    const title=(header.getAttribute('title') || t(header)).trim(); if(!title) continue;
    let parent=header.parentElement, panel=null;
    for(let i=0;parent && i<20;i++,parent=parent.parentElement){
      if(parent.querySelector(content)) {
        const heads=[...parent.querySelectorAll('.title-text')].filter(cssVisible);
        if(heads.length===1){panel=parent;break;}
        if(heads.length>1)break;
      }
    }
    if(!panel || used.has(panel))continue;
    used.add(panel);
    let id='fmwidget-'+widgets.length;
    panel.setAttribute('data-fm-collector-widget',id);
    const list=[...panel.querySelectorAll('.ag-root')];
    list.forEach((g,i)=>g.setAttribute('data-fm-collector-grid',String(i)));
    widgets.push({id,title,gridCount:list.length});
  }
  return {url:location.origin+location.pathname, title: document.title, widgets};
})();
"""

SAMPLE_JS = r"""
const id=arguments[0];
return (() => {
  const panel=document.querySelector('[data-fm-collector-widget="'+id+'"]');
  if(!panel)return {missing:true};
  const txt=e=>(e?.innerText||e?.textContent||'').trim();
  const titleEl=panel.querySelector('.title-text');
  const title=titleEl?.getAttribute('title') || txt(titleEl) || id;
  const panelText=txt(panel).slice(0,25000);
  const codes=[...new Set((panelText.match(/MB-[A-Z0-9-]+/gi)||[]).map(s=>s.toUpperCase()))];
  const headers=[...panel.querySelectorAll('fui-time-series-header-group-cell[id]')].map(e=>({
    code:e.getAttribute('id'), description: e.querySelector('[data-testid="ts-header-display-name"]')?.getAttribute('title') || txt(e.querySelector('.column-description')) || ''
  }));
  const unit=panelText.match(/Original Base\s*([^\n]+)/i)?.[1]?.trim()||'';
  // A text label is not enough to infer a forecast. Use selected/active mode only.
  let mode='';
  const candidates=[...panel.querySelectorAll('[aria-selected="true"],[aria-pressed="true"],.mat-mdc-select-value-text,.selected,[data-state="active"]')]
     .map(txt).map(x=>x.trim()).filter(x=>/^(Actual|Forecasts?|Monthly Avg|Monthly Average|실적|전망)$/i.test(x));
  if(candidates.length)mode=candidates[0];
  if(!mode){
    // Actual/Forecasts live inside a clickable dropdown, not necessarily aria-selected.
    const ctl=panel.querySelector('fui-price-calculation-type-dropdown .mdc-button__label');
    const label=txt(ctl).trim();
    if(/^(Actual|Forecasts?)$/i.test(label))mode=label;
  }
  const chartRows=[...panel.querySelectorAll('[data-testid="price-history-row"]')].map(e=>{
    const p=e.querySelector('.price-col .price[title],.price-col [title]');
    return {date:txt(e.querySelector('.date-col')),priceTitle:p?.getAttribute('title')||'',
      priceText:txt(e.querySelector('.price-col')),change:txt(e.querySelector('[data-testid="percentage-change"]'))};
  });
  const grids=[...panel.querySelectorAll('.ag-root')].map(grid=>{
    // Pinned fragments can be siblings of .ag-root in the same single-grid wrapper.
    // Never search the entire widget: multiple grids can reuse row-index=0.
    const wrapper=grid.closest('.ag-root-wrapper');
    const scope=wrapper && wrapper.querySelectorAll('.ag-root').length===1 ? wrapper : grid;
    const rows=new Map();
    for(const e of scope.querySelectorAll('.ag-row[row-index]')) {
      const i=e.getAttribute('row-index');
      if(!rows.has(i))rows.set(i,new Map());
      for(const c of e.querySelectorAll('[role="gridcell"][col-id],.ag-cell[col-id]')) {
        let cid=c.getAttribute('col-id'); if(!cid)continue;
        const inner=c.querySelector('fui-price-cell [title], span[title]');
        const value=inner?.getAttribute('title') || c.getAttribute('title') || '';
        const isDate=/^(date|assessment[-_]?date|datevalue|date-col)$/i.test(cid) || Boolean(c.querySelector('fui-date-cell'));
        if(isDate)cid='date';
        const cell={colId:cid,text:txt(c)||(isDate?value:''),title:value};
        const previous=rows.get(i).get(cid);
        if(previous && (previous.text||previous.title) && (cell.text||cell.title)
           && (previous.text||previous.title)!==(cell.text||cell.title)) {
          rows.get(i).set('__date_conflict__',{colId:'__date_conflict__',text:'conflict'});
        } else if(!previous || !(previous.text||previous.title)) rows.get(i).set(cid,cell);
      }
    }
    // AG Grid may place Date in a pinned sibling container. Join by row-index,
    // never by apparent screen row number (virtual grids recycle rows).
    for (const [i,cols] of rows) {
       if (cols.get('date')?.text || cols.get('date')?.title) continue;
       const pin=[...scope.querySelectorAll('.ag-pinned-left-cols-container .ag-row[row-index]')]
          .find(r=>r.getAttribute('row-index')===i);
      const dateCell=pin?.querySelector('[col-id="date"],.date-ag-grid-column,fui-date-cell');
      const dateText=txt(dateCell);
      if (dateText && /\d{4}/.test(dateText)) {
        cols.set('date',{colId:'date',text:dateText,title:''});
      }
    }
    return {index:grid.getAttribute('data-fm-collector-grid'),rows:[...rows].map(([i,c])=>({index:Number(i),conflicted:c.has('__date_conflict__'),cells:[...c.values()]}))};
  });
  return {id,title,unit,directCodes:codes,headers,grids,chartRows,mode};
})();
"""

SCROLL_INFO_JS = r"""
const wid=arguments[0],gid=String(arguments[1]);
return (()=>{
 const panel=document.querySelector('[data-fm-collector-widget="'+wid+'"]');
 const grid=panel?.querySelector('[data-fm-collector-grid="'+gid+'"]');if(!grid)return null;
 const panelBox=grid.getBoundingClientRect();
 const get=(e)=>e?{top:e.scrollTop,left:e.scrollLeft,maxY:Math.max(0,e.scrollHeight-e.clientHeight),
   maxX:Math.max(0,e.scrollWidth-e.clientWidth),height:e.clientHeight,width:e.clientWidth}:null;
 const candidate=(axis)=>{
  const sels=axis==='x'?['.ag-body-horizontal-scroll-viewport','.ag-center-cols-viewport',
     '[scrollbarviewport]','.ng-scroll-viewport','.ng-scrollbar-viewport','.ng-scrollbar','[scrollable="true"]']:
     ['.ag-body-viewport','.ag-body-vertical-scroll-viewport','[scrollbarviewport]','.ng-scroll-viewport'];
  const nodes=[...new Set(sels.flatMap(sel=>[...grid.querySelectorAll(sel),...panel.querySelectorAll(sel)]))];
  return nodes.find(e=>{const r=e.getBoundingClientRect();const overlap=Math.max(0,Math.min(r.right,panelBox.right)-Math.max(r.left,panelBox.left));
   return overlap>10 && (axis==='x'?e.scrollWidth-e.clientWidth:e.scrollHeight-e.clientHeight)>2;})||null;
 };
 const x=candidate('x'),y=candidate('y');
 // Angular/ngx-scrollbar sometimes supplies only the thumb as the public horizontal control.
 const thumbs=[...panel.querySelectorAll('scrollbar-x [scrollbarthumbx],.ng-scrollbar-thumb[scrollbarthumbx]')];
 const thumb=thumbs.filter(e=>{const r=e.getBoundingClientRect();return Math.max(0,Math.min(r.right,panelBox.right)-Math.max(r.left,panelBox.left))>10;})
   .sort((a,b)=>Math.abs(a.getBoundingClientRect().top-panelBox.bottom)-Math.abs(b.getBoundingClientRect().top-panelBox.bottom))[0]||null;
 const track=thumb?.closest('[scrollbartrackx]')||thumb?.parentElement;
 const tr=track?.getBoundingClientRect(),th=thumb?.getBoundingClientRect();
 const thumbInfo=tr&&th?{travel:Math.max(0,tr.width-th.width),width:th.width,trackWidth:tr.width,
   offset:th.left-tr.left,selector:'scrollbar-x [scrollbarthumbx]'}:null;
 return {v:get(y),h:get(x),thumb:thumbInfo,
   native_x:!!x,has_external_thumb:!!thumbInfo};
})();
"""

SCROLL_JS = r"""
const wid=arguments[0],gid=String(arguments[1]),axis=arguments[2],value=Number(arguments[3]);
return (()=>{
 const panel=document.querySelector('[data-fm-collector-widget="'+wid+'"]');
 const grid=panel?.querySelector('[data-fm-collector-grid="'+gid+'"]');if(!grid)return {ok:false,reason:'grid missing'};
 const search=axis==='y'?['.ag-body-viewport','.ag-body-vertical-scroll-viewport','[scrollbarviewport]']:
    ['.ag-body-horizontal-scroll-viewport','.ag-center-cols-viewport','[scrollbarviewport]','.ng-scroll-viewport'];
 const candidates=[...new Set(search.flatMap(q=>[...grid.querySelectorAll(q),...panel.querySelectorAll(q)]))];
 const e=candidates.find(e=>axis==='y'?e.scrollHeight-e.clientHeight>2:e.scrollWidth-e.clientWidth>2);
 if(!e)return {ok:false,reason:'no native scroll viewport'};
 const before=axis==='y'?e.scrollTop:e.scrollLeft;
 if(axis==='y')e.scrollTop=value;else e.scrollLeft=value;
 e.dispatchEvent(new Event('scroll',{bubbles:true}));
 return {ok:true,before,after:axis==='y'?e.scrollTop:e.scrollLeft};
})();
"""

GRID_PROBE_JS = r"""
const wid=arguments[0],gid=String(arguments[1]);
return (()=>{
 const panel=document.querySelector('[data-fm-collector-widget="'+wid+'"]');
 const grid=panel?.querySelector('[data-fm-collector-grid="'+gid+'"]');
 if(!grid)return {status:'grid-not-found'};
 const cells=[...grid.querySelectorAll('.ag-cell[col-id],[role="gridcell"][col-id]')];
 const head=[...grid.querySelectorAll('.ag-header-cell[col-id]')].map(x=>x.getAttribute('col-id')).filter(Boolean);
 const codes=[...grid.querySelectorAll('fui-time-series-header-group-cell[id]')].map(x=>x.id);
 const seen=[...new Set(cells.map(c=>c.getAttribute('col-id')).filter(Boolean))];
 const first=[...grid.querySelectorAll('.ag-row[row-index]')].slice(0,3).map(row=>({
  index:row.getAttribute('row-index'),
  cells:[...row.querySelectorAll('.ag-cell[col-id]')].slice(0,14).map(c=>({
   id:c.getAttribute('col-id'), value:(c.querySelector('[title]')?.getAttribute('title')||c.innerText||'').trim().slice(0,60)
  }))
 }));
 const vp=grid.querySelector('.ag-body-horizontal-scroll-viewport')||grid.querySelector('.ag-center-cols-viewport');
 return {status:'ok',rowCount:grid.getAttribute('aria-rowcount'),columnCount:grid.getAttribute('aria-colcount'),
   headerIds:head.slice(0,60),headerCodes:codes.slice(0,40),visibleIds:seen.slice(0,60),rows:first,
   horizontal:vp?{left:vp.scrollLeft,width:vp.clientWidth,scrollWidth:vp.scrollWidth}:null};
})();
"""

VISIBLE_GRID_JS = r"""
const wid=arguments[0],gid=String(arguments[1]);
return (()=>{
 const panel=document.querySelector('[data-fm-collector-widget="'+wid+'"]');
 const grid=panel?.querySelector('[data-fm-collector-grid="'+gid+'"]');if(!grid)return '';
 // Column identifiers are the primary proof that virtualized data moved horizontally.
 // Only visible cells are sampled; reading the entire DOM on each scroll is unnecessary.
 return [...grid.querySelectorAll('.ag-cell[col-id],[role="gridcell"][col-id]')]
   .filter(e=>e.getClientRects().length>0).slice(0,200)
   .map(e=>(e.getAttribute('row-index')||e.closest('.ag-row')?.getAttribute('row-index')||'')
        +':'+e.getAttribute('col-id')+'='+(e.getAttribute('title')||e.textContent||'').trim().slice(0,60))
   .join('|');
})();
"""


def move_grid_scroll(driver,widget_id,grid_id,axis,target,info=None,previous=None):
    """Native viewport first, Angular scrollbar-thumb fallback for horizontal grids.
    Returns whether the content position demonstrably changed; no private network endpoints.
    """
    target=float(target)
    before=driver.execute_script(VISIBLE_GRID_JS,widget_id,grid_id) if axis=='x' else None
    outcome=driver.execute_script(SCROLL_JS,widget_id,grid_id,axis,target)
    if outcome and outcome.get('ok'):
        changed=outcome.get('after')!=outcome.get('before')
        if axis!='x':return changed or (target==0 and outcome.get('after')==0)
        if changed:
            # Angular virtualized columns render asynchronously after scrollLeft changes.
            # A zero-delay signature check creates a false 'x=159' failure.
            for _ in range(6):
                time.sleep(.075)
                seen=driver.execute_script(VISIBLE_GRID_JS,widget_id,grid_id)
                if seen and seen!=before:return True
            # The native viewport moved, but the visible cells did not demonstrably change.
            # Continue to thumb fallback; caller logs the probe for diagnosis.
        elif target==0 and outcome.get('after')==0:
            return True
    if axis!='x':return False
    # Drag only the matching scrollbar thumb in the user's actual DOM structure.
    meta=info or driver.execute_script(SCROLL_INFO_JS,widget_id,grid_id) or {}
    thumb=meta.get('thumb') or {}
    travel=thumb.get('travel',0)
    if travel<=1:return False
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.by import By
    grid=driver.find_element(By.CSS_SELECTOR,f'[data-fm-collector-widget="{widget_id}"] [data-fm-collector-grid="{grid_id}"]')
    panel=grid.find_element(By.XPATH,'ancestor::*[@data-fm-collector-widget][1]')
    controls=panel.find_elements(By.CSS_SELECTOR,'scrollbar-x [scrollbarthumbx]')
    if not controls:return False
    # Multiple independent scrollbar-x components may coexist in the widget.
    # Select the control whose rectangle is closest to the target grid.
    grid_rect=grid.rect
    def distance(e):
        r=e.rect
        vertical=max(0,grid_rect['y']-r['y']-r['height'],r['y']-grid_rect['y']-grid_rect['height'])
        horizontal=max(0,grid_rect['x']-r['x']-r['width'],r['x']-grid_rect['x']-grid_rect['width'])
        return (vertical+horizontal,abs(r['y']-(grid_rect['y']+grid_rect['height'])))
    controls.sort(key=distance)
    current=driver.execute_script(SCROLL_INFO_JS,widget_id,grid_id) or {}
    thumb_info=current.get('thumb') or {}
    native=current.get('h') or {}
    max_x=native.get('maxX',0)
    if max_x>0:
        desired=float(thumb_info.get('travel',0))*min(1,max(0,target/max_x))
    else:
        # No exposed native max. Caller passes normalized thumb px position.
        desired=min(float(thumb_info.get('travel',0)),max(0,target))
    delta=desired-float(thumb_info.get('offset',0))
    if abs(delta)<1:return True
    ActionChains(driver).move_to_element(controls[0]).click_and_hold().move_by_offset(int(round(delta)),0).release().perform()
    for _ in range(6):
        time.sleep(.075)
        after=driver.execute_script(VISIBLE_GRID_JS,widget_id,grid_id)
        if after and after!=before:return True
    return False


def merge_samples(base: dict, next_sample: dict, errors: list):
    """Merge virtualization passes by stable grid ID + row-index + column ID."""
    if not base:
        return json.loads(json.dumps(next_sample))
    for h in next_sample.get("headers", []):
        if h not in base["headers"]:
            base["headers"].append(h)
    base["directCodes"] = sorted(set(base.get("directCodes", [])) | set(next_sample.get("directCodes", [])))
    if not base.get("mode"):
        base["mode"] = next_sample.get("mode") or ""
    existing_chart = {(r.get("date"),r.get("priceTitle")):r for r in base.get("chartRows", [])}
    for r in next_sample.get("chartRows", []):
        existing_chart[(r.get("date"),r.get("priceTitle"))] = r
    base["chartRows"] = list(existing_chart.values())
    grids = {str(g.get("index")):g for g in base.get("grids", [])}
    for gr in next_sample.get("grids", []):
        g=grids.setdefault(str(gr.get("index")),{"index":gr.get("index"),"rows":[]})
        index={int(r["index"]):r for r in g.get("rows", [])}
        for row in gr.get("rows", []):
            i=int(row["index"])
            existing=index.setdefault(i,{"index":i,"cells":[]})
            cols={c.get("colId"):c for c in existing.get("cells", [])}
            for c in row.get("cells", []):
                cid=c.get("colId")
                if cid in cols and (cols[cid].get("title") or cols[cid].get("text"))!=(c.get("title") or c.get("text")):
                    if (cols[cid].get("title") or cols[cid].get("text")) and (c.get("title") or c.get("text")):
                        errors.append(f"행 {i},열 {cid}: 서로 다른 데이터 발견")
                        existing['conflicted']=True
                if cid not in cols or not cols[cid].get("text"):
                    cols[cid]=c
            existing["cells"] = list(cols.values())
        g["rows"]=sorted(index.values(),key=lambda x:x["index"])
    base["grids"]=list(grids.values())
    return base


def grid_columns_materialized(probe):
    """AG Grid may render columns outside viewport; no drag is needed if
    each advertised data-column has actual DOM gridcells already materialized.
    This is a DOM-coverage decision, NOT proof of numeric data extraction.
    """
    if not isinstance(probe,dict):return False
    expected={x for x in probe.get('headerIds',[]) if x and x!='date'}
    rendered=set(probe.get('visibleIds',[]))
    return bool(expected) and expected.issubset(rendered)


def positions(max_scroll: float, page: float, limit=120):
    if max_scroll <= 2:
        return [0]
    step=max(1,int(page*0.85))
    count=int(max_scroll//step)+1
    if count > limit:
        # preserve beginning & end, mark non-exhaustiveness in caller.
        result=[min(max_scroll,i*step) for i in range(limit-1)]+[max_scroll]
        return sorted(set(int(x) for x in result))
    return sorted(set([0]+[min(int(max_scroll),i*step) for i in range(1,count+1)]+[int(max_scroll)]))




def daily_vertical_positions(max_scroll: float, page: float, days: int, *, daily_limit=18):
    """Only page through recent observations in scheduled runs.

    --days 0 or >60 explicitly opts into historical exhaustive traversal.
    Never fake a full-scan claim if a daily pagination budget is exceeded.
    """
    if days==0 or days>60:
        return positions(max_scroll,page,limit=160),True
    step=max(1,int(page*0.85))
    if max_scroll<=2:return [0],False
    return [int(min(max_scroll,i*step)) for i in range(min(daily_limit, int(max_scroll//step)+2))
            if i==0 or min(max_scroll,i*step)!=min(max_scroll,(i-1)*step)],False


def oldest_visible_price_date(widget_sample:dict,grid_idx:int):
    """Find the oldest unambiguous date in the current grid's materialized rows."""
    ds=[]
    for grid in widget_sample.get('grids',[]):
        if str(grid.get('index'))!=str(grid_idx):continue
        for row in grid.get('rows',[]):
            for cell in row.get('cells',[]):
                if str(cell.get('colId','')).lower() in ('date','assessment-date','assessmentdate','datevalue','date-col'):
                    parsed=normalize_date(cell.get('text') or '')
                    if parsed:ds.append(parsed)
    return min(ds) if ds else None

class SessionError(RuntimeError):
    pass


class PortOwnershipError(SessionError):
    """디버그 포트 소유자를 검증하지 못했거나 전용 Chrome이 아닌 경우."""


def _canonical_path(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(os.path.expandvars(str(path).strip().strip('"')))))


def _chrome_profile_from_cmdline(cmdline):
    """Windows Chrome 실행 인수의 --user-data-dir 문자열을 추출한다."""
    # subprocess.list2cmdline은 공백 있는 전체 스위치를 따옴표로 감쌀 수 있음.
    # 예: "--user-data-dir=C:\Users\John Doe\ChromeProfile_9444"
    match = re.search(
        r'(?:^|\s)"?--user-data-dir(?:=|\s+)(?:"([^"]+)"|((?:(?!\s+--)[^"])+))',
        cmdline or '', re.I,
    )
    return (match.group(1) or match.group(2)).strip().rstrip('"') if match else None


def verify_chrome_owner(processes, profile=CHROME_PROFILE, port=PORT):
    """소유자 오인 접속 방지: 모든 Listener의 프로세스+실행 인수 검사 (fail closed)."""
    if not processes:
        raise PortOwnershipError(f"{port} 포트의 소유자 정보를 확인할 수 없습니다. 타 프로그램에 연결하지 않습니다.")
    for proc in processes:
        pid = proc.get("pid", "?")
        name = str(proc.get("name") or "").lower()
        cmd = str(proc.get("command_line") or "")
        addr = str(proc.get("local_address") or "")
        if addr not in {"127.0.0.1", "::1"}:
            raise PortOwnershipError(f"{port} 포트가 로컬 전용 주소가 아닌 {addr}에 열려 있어 접속을 거부합니다.")
        if name != "chrome.exe" or not re.search(r'(?:^|\s)--remote-debugging-port(?:=|\s+)'+str(port)+r'(?=\s|$)', cmd, re.I):
            raise PortOwnershipError(f"{port} 포트 PID {pid}는 Fastmarkets 전용 Chrome으로 확인되지 않습니다. 기존 브라우저를 종료하지 않습니다.")
        found_profile = _chrome_profile_from_cmdline(cmd)
        if not found_profile or _canonical_path(found_profile) != _canonical_path(profile):
            raise PortOwnershipError(f"{port} 포트 PID {pid}의 Chrome 프로필이 다릅니다. 자동 연결하지 않습니다.")
    return True


def inspect_windows_listeners(port=PORT):
    """9444 TCP LISTEN 소유 프로세스/CommandLine을 Windows CIM에서 확인."""
    if not IS_WINDOWS:
        raise PortOwnershipError("디버그 포트 소유권 검증은 현재 Windows에서만 지원합니다.")
    # 모든 바인딩 주소의 Listener 검사; 다른 IP에 같은 포트를 열어도 거부.
    script = ("$ErrorActionPreference='Stop'; "
              "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
              "$rows=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -eq "+str(port)+"); "
              "$out=@(foreach($row in $rows){ "
              "$p=Get-CimInstance Win32_Process -Filter ('ProcessId='+[string]$row.OwningProcess) -ErrorAction Stop; "
              "[pscustomobject]@{pid=[int]$row.OwningProcess;name=[string]$p.Name;"
              "command_line=[string]$p.CommandLine;executable_path=[string]$p.ExecutablePath;local_address=[string]$row.LocalAddress}}); "
              "ConvertTo-Json -InputObject $out -Compress -Depth 4")
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise PortOwnershipError("Windows 디버그 포트 소유자 조회 실패: PowerShell/CIM 권한 또는 실행 시간 확인") from e
    if completed.returncode != 0:
        # 관리자 권한으로 재시도하거나 보안 정책 확인; 무검증 접속은 금지.
        raise PortOwnershipError("Windows 포트 소유자 조회 오류: PowerShell Get-NetTCPConnection/Get-CimInstance 권한 확인")
    try:
        data = json.loads(completed.stdout.strip().lstrip("\ufeff") or "[]")
    except (ValueError, TypeError) as e:
        raise PortOwnershipError("포트 소유자 조회 응답을 해석하지 못했습니다. 연결하지 않습니다.") from e
    if isinstance(data, dict):
        data=[data]
    if not isinstance(data, list):
        raise PortOwnershipError("포트 소유자 정보 형식이 올바르지 않습니다.")
    return data


def cdp_version(port=PORT):
    """프록시를 거치지 않고 localhost DevTools 메타데이터만 조회."""
    from urllib.request import Request
    try:
        opener=build_opener(ProxyHandler({}))
        with opener.open(Request(f"http://127.0.0.1:{port}/json/version", headers={"Accept":"application/json"}), timeout=0.8) as response:
            if response.status != 200:
                return None
            data=json.loads(response.read(32768).decode("utf-8"))
        return data if isinstance(data,dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


@contextmanager
def exclusive_browser_job():
    """GUI와 --once 예약 실행이 같은 Chrome 프로필을 동시에 조작하지 못하도록 잠금."""
    APP_HOME.mkdir(parents=True,exist_ok=True)
    with BROWSER_LOCK_PATH.open("a+b") as fp:
        fp.seek(0,os.SEEK_END)
        if fp.tell() < 1:
            fp.write(b"0")
            fp.flush()
        fp.seek(0)
        try:
            if IS_WINDOWS:
                import msvcrt
                msvcrt.locking(fp.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(fp.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as e:
            raise SessionError("Fastmarkets 수집기 또는 예약 실행이 이미 브라우저를 사용 중입니다. 완료 후 다시 시도하세요.") from e
        try:
            yield
        finally:
            fp.seek(0)
            if IS_WINDOWS:
                msvcrt.locking(fp.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(fp.fileno(),fcntl.LOCK_UN)


def _safe_driver_error(value):
    """Redact bearer credentials, query fragments and common secret fields before storing locally."""
    text = str(value)
    text = re.sub(r"(?i)\b(bearer\s+)\S+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)\b(password|passwd|token|access_token|refresh_token|secret|cookie|authorization|api_key)\s*[:=]\s*[^\s,;&]+",
                  r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)(https?://[^\s?#<>\"']+)[?#][^\s<>\"']*", r"\1?[REDACTED]", text)
    return text[:2500]


def _driver_version(path):
    """Only interrogate a previously resolved driver executable, never download/modify one."""
    if not path or not Path(path).is_file():
        return None
    try:
        result = subprocess.run([str(path), "--version"], timeout=4,
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode == 0:
            return _safe_driver_error(result.stdout.strip())[:160]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _cached_chromedrivers():
    """Enumerate candidates only; cache presence does NOT prove which driver was selected."""
    root = Path.home() / ".cache" / "selenium" / "chromedriver"
    if not root.is_dir():
        return []
    found = []
    try:
        # Limit discovery depth to the known cache layout: platform/version/chromedriver.exe.
        for platform_dir in root.iterdir():
            if not platform_dir.is_dir():
                continue
            for version_dir in platform_dir.iterdir():
                if not version_dir.is_dir():
                    continue
                exe = version_dir / ("chromedriver.exe" if IS_WINDOWS else "chromedriver")
                if exe.is_file():
                    found.append({"path": str(exe), "version": version_dir.name})
    except OSError:
        return found[:20]
    return sorted(found, key=lambda x:x["version"], reverse=True)[:20]


def _driver_diagnostic(stage, chrome_binary, driver_path=None, error=None):
    """Local, bounded diagnostic. Never collect passwords, cookies, tabs or command lines."""
    import platform
    report = {"time": datetime.now().isoformat(timespec="seconds"), "stage": stage,
              "port": PORT, "expected_profile": str(CHROME_PROFILE),
              "python": sys.version.split()[0], "python_executable": sys.executable,
              "chrome_binary": str(chrome_binary or ""),
              "chrome": str((cdp_version(PORT) or {}).get("Browser") or ""),
              "driver_path": str(driver_path or ""),
              "driver_version": _driver_version(driver_path),
              "platform": platform.system(),
              "selenium_manager_cached_candidates": _cached_chromedrivers(),
              "selenium_driver_env_set": bool(os.environ.get("SE_CHROMEDRIVER")),
              "app_driver_override_set": bool(os.environ.get(DRIVER_OVERRIDE_ENV))}
    try:
        import selenium
        report["selenium"] = getattr(selenium, "__version__", "unknown")
    except ImportError:
        report["selenium"] = "not_installed"
    if error is not None:
        import traceback
        report["exception_type"] = type(error).__name__
        report["exception_message"] = _safe_driver_error(error)
        report["traceback_frames"] = [
            {"module": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
            for frame in traceback.extract_tb(error.__traceback__)[-16:]
        ]
        if error.__cause__ is not None:
            report["cause_type"] = type(error.__cause__).__name__
            report["cause_message"] = _safe_driver_error(error.__cause__)
    try:
        with atomic_text(DRIVER_DIAGNOSTIC_PATH) as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass
    return report


class ChromeSession:
    def __init__(self, notify=None):
        self.driver = None
        self.notify = notify or (lambda msg: None)
        self._listener_checked_at=0
        self._listener_cache=None
        self._cdp_identity=None

    @staticmethod
    def _chrome_path():
        for p in [Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))/"Google/Chrome/Application/chrome.exe",
                  Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"))/"Google/Chrome/Application/chrome.exe",
                  Path(os.environ.get("LOCALAPPDATA", ""))/"Google/Chrome/Application/chrome.exe"]:
            if p.is_file(): return str(p)
        raise SessionError("Google Chrome 실행 파일이 없습니다.")

    def _validate_listener(self, expected_port=PORT, allow_cache=False):
        info=cdp_version(expected_port)
        identity=(info or {}).get('webSocketDebuggerUrl')
        if (allow_cache and expected_port==PORT and self._listener_cache and identity
            and identity==self._cdp_identity and time.monotonic()-self._listener_checked_at<5
            and re.match(r'^Chrome/\d',str((info or {}).get('Browser','')))):
            return self._listener_cache
        # Windows CIM occasionally times out during a busy office-PC session.
        # Retry only a transient QUERY failure. Wrong PID/profile is NEVER bypassed.
        for attempt in range(2):
            try:
                owners=inspect_windows_listeners(expected_port)
                break
            except PortOwnershipError as exc:
                transient=('소유자 조회 실패' in str(exc) or '소유자 조회 오류' in str(exc))
                if not transient or attempt:
                    raise
                self.notify('9444 포트 소유자 조회 일시 실패 → 1회 재확인')
                time.sleep(.2)
        # no owner with working port = inconsistent result, treat as unsafe
        verify_chrome_owner(owners, CHROME_PROFILE, expected_port)
        info=cdp_version(expected_port)
        product=str((info or {}).get("Browser") or "")
        if not re.match(r"^Chrome/\d", product):
            raise PortOwnershipError(f"{expected_port} 포트는 Google Chrome DevTools로 확인되지 않습니다 (Browser={product or '없음'}).")
        self._listener_checked_at=time.monotonic()
        self._listener_cache=owners
        self._cdp_identity=(info or {}).get('webSocketDebuggerUrl')
        return owners

    def connect(self):
        # Reuse must pass exactly the same ownership gate as a new connection.
        if self.driver:
            self._validate_listener()
            try:
                if self.driver.window_handles:
                    self.ensure_tab()
                    return self.driver
            except Exception:
                self.detach()
        try:
            import selenium
        except ImportError as e:
            raise SessionError('Selenium이 없습니다. GUI의 "필수 패키지 설치"를 누르세요.') from e
        # 최초 연결 및 재연결 모두 PORT, Browser, 프로필 소유자 일치 확인.
        listeners=inspect_windows_listeners(PORT)
        if listeners:
            self._validate_listener()
            self.notify(f"Fastmarkets 전용 Chrome 재사용 (포트 {PORT}, 프로필 검증 완료)")
        else:
            if cdp_version(PORT) is not None:
                raise PortOwnershipError("DevTools 응답은 있지만 포트 소유자를 확인할 수 없습니다. 연결하지 않습니다.")
            CHROME_PROFILE.mkdir(parents=True,exist_ok=True)
            self.notify(f"Fastmarkets 전용 Chrome 실행 (포트 {PORT}, 다른 Chrome/Edge는 유지)")
            proc=subprocess.Popen(
                [self._chrome_path(),f"--remote-debugging-port={PORT}",
                 "--remote-debugging-address=127.0.0.1",f"--user-data-dir={CHROME_PROFILE}",
                 "--no-first-run","--no-default-browser-check",WORKSPACE_URL],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
            )
            deadline=time.monotonic()+14
            while time.monotonic()<deadline:
                if cdp_version(PORT):break
                if proc.poll() is not None:
                    raise SessionError("Fastmarkets 전용 Chrome이 시작 직후 종료되었습니다. Chrome 정책·프로필 상태를 확인하세요.")
                time.sleep(.2)
            if not cdp_version(PORT):
                raise SessionError(f"Chrome 포트 {PORT} 응답이 없습니다. 프로필 중복 실행, 사내 보안 정책, Chrome 시작 실패를 확인하세요.")
            self._validate_listener()
        before=self._validate_listener()
        self.driver=self._attach_driver(owners=before)
        # Check ownership again after ChromeDriver attaches (port reassignment race).
        # On mismatch refuse to navigate or touch any browser tab.
        try:
            after=self._validate_listener()
            if {p['pid'] for p in before}!={p['pid'] for p in after}:
                raise PortOwnershipError('연결 중 Chrome PID가 변경되었습니다. 재연결하세요.')
        except PortOwnershipError:
            self.detach()
            raise
        self.ensure_tab()
        return self.driver

    def _attach_driver(self, owners=None):
        """Attach only to pre-verified Fastmarkets Chrome; preserve existing tabs/browser."""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        # Confirm actual 9444 owner rather than using the Chrome binary of another instance.
        if IS_WINDOWS:
            owners = owners if owners is not None else inspect_windows_listeners(PORT)
            verify_chrome_owner(owners, CHROME_PROFILE, PORT)
            running_paths = {str(o.get("executable_path") or "").strip() for o in owners}
            running_paths.discard("")
            if len(running_paths) > 1:
                raise PortOwnershipError("9444 포트의 실행 파일 경로가 여러 개입니다. 연결하지 않습니다.")
            chrome_binary = next(iter(running_paths)) if running_paths else self._chrome_path()
            if not Path(chrome_binary).is_file():
                raise SessionError("9444 Chrome 실행 파일의 실제 경로를 확인할 수 없습니다.")
        else:
            chrome_binary = ""
        # Do not pass port/profile startup switches to an already running Chrome.
        opts = Options()
        opts.debugger_address = f"127.0.0.1:{PORT}"
        # Selenium Manager uses this exact executable to resolve driver compatibility.
        if chrome_binary:
            opts.binary_location = chrome_binary
        driver_override = os.environ.get(DRIVER_OVERRIDE_ENV, "").strip().strip('"')
        service = None
        driver_path = None
        try:
            if driver_override:
                override = Path(driver_override).expanduser().resolve()
                if not override.is_file() or override.name.lower() != "chromedriver.exe":
                    raise SessionError(f"{DRIVER_OVERRIDE_ENV} 경로에 chromedriver.exe가 없습니다: {override}")
                from selenium.webdriver.chrome.service import Service
                service = Service(executable_path=str(override))
                driver_path = str(override)
                driver = webdriver.Chrome(service=service, options=opts)
            else:
                driver = webdriver.Chrome(options=opts)
            driver_path = str(getattr(getattr(driver, "service", None), "path", "") or driver_path or "")
            _driver_diagnostic("connected", chrome_binary, driver_path)
            return driver
        except Exception as exc:
            # A failed explicit Service belongs to this request only; never terminate Chrome.
            if service is not None:
                try:
                    service.stop()
                except Exception:
                    pass
            report = _driver_diagnostic("webdriver_session_failed", chrome_binary,
                                        str(getattr(service, "path", "") or driver_path or ""), exc)
            if isinstance(exc, SessionError):
                raise
            reason = report.get("exception_message") or type(exc).__name__
            raise SessionError(
                f"Fastmarkets ChromeDriver 연결 실패 [{type(exc).__name__}]: {reason[:450]}\n"
                f"자세한 진단: {DRIVER_DIAGNOSTIC_PATH} (9444 전용 Chrome만 확인)"
            ) from exc

    def detach(self):
        """Stop only our driver service; never send Browser.close or driver.quit."""
        driver,self.driver=self.driver,None
        self._listener_cache=None;self._cdp_identity=None;self._listener_checked_at=0
        if driver is not None:
            try:driver.service.stop()
            except Exception:pass

    def ensure_tab(self):
        d=self.driver
        if not d:raise SessionError("ChromeDriver가 연결되지 않았습니다.")
        try: handles=d.window_handles
        except Exception as e:raise SessionError("Chrome 연결이 해제되었습니다.") from e
        if not handles:raise SessionError("열려 있는 Chrome 탭이 없습니다.")
        try:
            # current_window_handle can be stale even when window_handles is nonempty.
            current=d.current_window_handle
            if current in handles:
                d.switch_to.window(current)
                return
        except Exception:pass
        for handle in handles:
            try:d.switch_to.window(handle);return
            except Exception:continue
        raise SessionError("유효한 Chrome 탭으로 전환하지 못했습니다.")

    def select_domain_tab(self, hosts):
        d=self.driver
        for handle in list(d.window_handles):
            try:
                d.switch_to.window(handle)
                if urlparse(d.current_url).hostname in hosts:return True
            except Exception:continue
        self.ensure_tab();return False

    def workspace_is_open(self):
        d=self.driver
        try:
            for handle in list(d.window_handles):
                d.switch_to.window(handle)
                parsed=urlparse(d.current_url)
                if parsed.hostname=='dashboard.fastmarkets.com' and f'/w/{current_workspace()[1]}/' in parsed.path:
                    if d.execute_script("return Boolean(document.querySelector('.title-text,.ag-root,[data-testid=price-history-row]'))"):
                        return True
            return False
        except Exception:return False

    def open_workspace(self, username="",password="", wait_seconds=25):
        d=self.connect()
        if self.workspace_is_open():
            self.notify("기존 기획재무그룹 탭 재사용")
            return True
        if not self.select_domain_tab({"dashboard.fastmarkets.com","auth.fastmarkets.com"}):
            # Preserve user's other tabs: create one new tab to navigate.
            self.ensure_tab();d.switch_to.new_window("tab")
        host=urlparse(d.current_url).hostname
        if host != "auth.fastmarkets.com":
            self.notify("기획재무그룹 작업공간으로 이동")
            d.set_page_load_timeout(18)
            try:d.get(current_workspace()[0])
            except Exception as e:
                # Chrome may keep a loading page beyond timeout; check its URL next.
                self.notify(f"페이지 로드 지연: {type(e).__name__}, 현재 주소를 재확인합니다.")
        deadline=time.monotonic()+wait_seconds
        submitted=False
        while time.monotonic()<deadline:
            self.ensure_tab()
            if self.workspace_is_open():
                try:
                    if d.execute_script("return Boolean(document.querySelector('.title-text,.ag-root,[data-testid=price-history-row]'))"):
                        return True
                except Exception:pass
            if self.select_domain_tab({"auth.fastmarkets.com"}):
                try:
                    form=d.find_elements("css selector","#userEmail")
                    if form and not submitted:
                        if not(username and password):
                            self.notify("Chrome에서 로그인을 완료한 뒤 '시세 수집'을 눌러주세요.")
                            return False
                        if urlparse(d.current_url).hostname != "auth.fastmarkets.com":
                            return False
                        form[0].clear();form[0].send_keys(username)
                        pw=d.find_element("css selector","#password")
                        pw.clear();pw.send_keys(password)
                        d.find_element("css selector","#login-button").click()
                        submitted=True
                        self.notify("로그인 제출 완료 — Dashboard 이동 확인 중")
                except Exception as e:
                    self.notify("로그인 입력 대기 또는 추가 인증 필요: "+type(e).__name__)
            time.sleep(.35)
        self.notify("로그인 대기 제한 도달 — 브라우저에서 직접 인증 후 다시 수집하세요.")
        return False

    def scrape(self, days: int, folder: Path, cancelled: threading.Event, callback=None, workbook_path=None, defer_export=False):
        started=time.perf_counter()
        d=self.connect()
        if not self.workspace_is_open():
            # Warm 9444 sessions skip authentication entirely. Cold SSO/MFA may
            # need longer than eight seconds; do not re-login or reload repeatedly.
            login_wait=min(90,max(8,int(config_load().get('login_wait_seconds',30))))
            if not self.open_workspace(*credentials_get(),wait_seconds=login_wait):
                raise SessionError("기획재무그룹 작업공간에 로그인되지 않았습니다.")
        self.notify(f"FMB 작업공간 위젯 탐색: {current_workspace()[1]} (기본 작업공간 {WORKSPACE_ID})")
        try:
            if config_load().get('maximize_chrome',True):d.maximize_window()
        except Exception as exc:self.notify('전용 Chrome 최대화 미적용: '+type(exc).__name__)
        result={};widgets=[]
        # Wait only for a stable DOM rather than a fixed long login delay.
        last_count=-1;stable=0;deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            result=d.execute_script(INVENTORY_JS)
            widgets=result.get("widgets") or []
            if len(widgets)==last_count and widgets:stable+=1
            else:stable=0
            last_count=len(widgets)
            if stable>=3:break
            time.sleep(.3)
        if not widgets:
            raise SessionError("위젯 0개: 로그인/로딩/DOM 변경 여부를 확인하세요.")
        snapshot={"url":result.get("url"),"timestamp":datetime.now().isoformat(),"widgets":[]}
        anomalies=[]
        for ix,meta in enumerate(widgets):
            if cancelled.is_set():raise SessionError("사용자가 수집을 중단했습니다. 기존 DB는 변경하지 않았습니다.")
            self._validate_listener(allow_cache=True)
            self.ensure_tab()
            if not self.workspace_is_open():raise SessionError("수집 중 작업공간 탭이 종료되거나 이동했습니다.")
            widget_id=meta["id"]
            self.notify(f"위젯 {ix+1}/{len(widgets)}: {meta['title']}")
            merged={}
            sample=d.execute_script(SAMPLE_JS,widget_id)
            if sample.get("missing"):
                anomalies.append(f"위젯 {meta['title']}: DOM 재생성으로 탐색 실패")
                continue
            merged=merge_samples(merged,sample,anomalies)
            caps=[];grid_probes=[]
            for gidx in range(meta.get("gridCount",0)):
                info=d.execute_script(SCROLL_INFO_JS,widget_id,gidx)
                if not info:continue
                start_probe=None
                try:
                    start_probe=d.execute_script(GRID_PROBE_JS,widget_id,gidx)
                    if start_probe:
                        grid_probes.append({'grid':gidx,'stage':'initial',**start_probe})
                        self.notify(f"  AGGrid[{gidx}] head={start_probe.get('headerIds',[])[:8]} visible={start_probe.get('visibleIds',[])[:8]}")
                except Exception as ex:self.notify(f"  AGGrid[{gidx}] probe failed: {type(ex).__name__}")
                h=info.get("h") or {};v=info.get("v") or {}
                thumb=info.get('thumb') or {}
                if grid_columns_materialized(start_probe):
                    # ALL declared columns are already in the DOM; horizontal
                    # scrolling again may yield identical cells and false errors.
                    hs=[0]
                    self.notify(f'  AGGrid[{gidx}] 열 전체 DOM 반영 확인; 불필요한 가로 이동 생략')
                elif h.get('maxX',0)>0:
                    hs=positions(h.get('maxX') or 0,h.get('width') or 0,limit=24)
                elif thumb.get('travel',0)>1:
                    hs=positions(thumb['travel'],max(20,thumb.get('width',30)),limit=24)
                else:hs=[0]
                vs,history_mode=daily_vertical_positions(v.get('maxY') or 0,v.get('height') or 0,days)
                if h.get("maxX",0)>0 and len(hs)>=24:caps.append(f"grid {gidx}: 가로 스크롤 24회 제한")
                # Scheduled/daily collection stops at the requested date, not the beginning of 1992.
                if history_mode and v.get('maxY',0)>0 and len(vs)>=160:
                    caps.append(f'grid {gidx}: 과거 전수조사 160단계 제한')
                # Horizontal first, then vertical: each pass reads all visible columns + pinned Date.
                steps=len(hs)*len(vs)
                if steps>360:
                    caps.append(f"grid {gidx}: 스크롤 총 {steps}회 중 360회로 제한")
                n=0
                seen_signatures=set()
                requested_cutoff=(date.today()-timedelta(days=days)).isoformat() if days else None
                reached_cutoff=False
                y_budget_exhausted=False
                try:
                    for x in hs:
                        moved=move_grid_scroll(d,widget_id,gidx,"x",x,info)
                        if x>0 and not moved:
                            caps.append(f'grid {gidx}: 가로 이동 불확실 x={x}; 현재 표시 중인 열만 수집')
                            try:
                                probe=d.execute_script(GRID_PROBE_JS,widget_id,gidx)
                                grid_probes.append({'grid':gidx,'stage':f'x={x}-unconfirmed',**(probe or {})})
                                self.notify(f"  스크롤 불확실 {meta['title']}: x={x}, header={probe.get('headerIds',[])[:8] if probe else []}")
                            except Exception:pass
                            continue  # Do not repeatedly scrape identical visible data.
                        segment_reached=False
                        for yi,y in enumerate(vs):
                            if cancelled.is_set():raise SessionError("사용자가 수집을 중단했습니다. 기존 DB는 변경하지 않았습니다.")
                            if n>=360:break
                            move_grid_scroll(d,widget_id,gidx,"y",y)
                            # The grid is asynchronous; wait briefly only on scroll, no fixed page sleeps.
                            time.sleep(.07)
                            fingerprint=d.execute_script(VISIBLE_GRID_JS,widget_id,gidx)
                            if fingerprint and fingerprint in seen_signatures:
                                n+=1
                                continue
                            if fingerprint:seen_signatures.add(fingerprint)
                            part=d.execute_script(SAMPLE_JS,widget_id)
                            if part.get("missing"):
                                caps.append("위젯 DOM 재생성으로 중간 수집 중단");break
                            merged=merge_samples(merged,part,anomalies)
                            n+=1
                            # Rows are newest-first in supported Fastmarkets price grids.
                            oldest=oldest_visible_price_date(part,gidx)
                            if not history_mode and requested_cutoff and oldest and oldest<requested_cutoff:
                                segment_reached=True
                                reached_cutoff=True
                                break
                            if yi==len(vs)-1 and not history_mode and y < (v.get('maxY') or 0):
                                y_budget_exhausted=True
                        if n>=360:break
                    if y_budget_exhausted and not reached_cutoff:
                        caps.append(f'grid {gidx}: 최근 {days}일 범위 확인 전에 세로 탐색 예산 소진; 과거 전체 탐색은 --days 0')
                finally:
                    # Restore user dashboard to top-left, regardless of parsing outcome.
                    try:
                        move_grid_scroll(d,widget_id,gidx,"x",0,info)
                        move_grid_scroll(d,widget_id,gidx,"y",0)
                    except Exception:pass
            merged["scrollCaps"]=caps
            merged["gridProbes"]=grid_probes
            snapshot["widgets"].append(merged)
            self.notify(f"  {meta['title']}: 가상표 {sum(len(g.get('rows',[])) for g in merged.get('grids',[]))}행, 스크롤경고 {len(caps)}개")
        prices, inventory, warnings=read_snapshot(snapshot,days)
        for w in inventory:
            stats=w.get('parse_stats',{})
            if stats and stats.get('date_missing'):
                source_widget=next((z for z in snapshot['widgets'] if z.get('title')==w['widget']), None)
                examples=[]
                if source_widget:
                    for grid in source_widget.get('grids',[]):
                        for row in grid.get('rows',[]):
                            if len(examples)>=3:break
                            cells=row.get('cells') or []
                            if not any(str(c.get('colId','')).lower()=='date' and normalize_date(c.get('text') or '') for c in cells):
                                examples.append({'row_index':row.get('index'), 'columns':[
                                    {'id':str(c.get('colId',''))[:50],
                                     'text':str(c.get('text',''))[:50]}
                                    for c in cells[:8]]})
                w['date_missing_examples']=examples
                self.notify(f"  날짜 매핑 진단 {w['widget']}: {stats['date_missing']}행 실패; "
                            f"행 샘플은 last_diagnostic.json/date_missing_examples 확인")
            if stats and stats.get('rows_total') and not w.get('captured_codes'):
                self.notify(f"  진단 {w['widget']}: 행 {stats['rows_total']}건; "
                    f"날짜없음 {stats['date_missing']}, 날짜범위밖 {stats['date_outside_period']}, "
                    f"숫자셀없음 {stats['no_numeric_prices']}, 정상매핑 {stats['rows_accepted']}")
        all_titles=" ".join(w.get("title","")+" "+" ".join(w.get("description_by_code",{}).values()) for w in inventory).lower()
        present_titles=" ".join(p.widget+" "+p.description for p in prices).lower()
        for label, tokens in (("탄산리튬",("탄산리튬","lithium carbonate")),
                              ("코발트",("코발트","cobalt")),
                              ("망간",("망간","manganese"))):
            if not any(t in all_titles for t in tokens):
                warnings.append(f"{label}: 해당 위젯/종목을 발견하지 못했습니다.")
            elif not any(t in present_titles for t in tokens):
                warnings.append(f"{label}: 위젯은 발견했으나 가격 수집 결과가 없습니다.")
        warnings=sorted(set(warnings+anomalies))
        coverage=coverage_report(prices,inventory,stored_symbols(folder))
        if coverage['previous_missing']:
            warnings.append('이전 종목이 이번에 미발견: '+', '.join(coverage['previous_missing']))
        for issue in warnings:
            self.notify('진단/FMB: '+issue)
        diagnostics={"captured_at":snapshot["timestamp"],"workspace_id":current_workspace()[1],
                     "widget_count":len(widgets),"processed_widgets":len(snapshot["widgets"]),
                     "found_symbols":sorted({c for w in inventory for c in w["codes"]}),
                     "price_symbols":sorted({p.symbol for p in prices}),
                     "price_rows":len(prices),"widgets":inventory,"warnings":warnings,"coverage":coverage,
                     "timings":{"dom_seconds":round(time.perf_counter()-started,3)},
                     "note":"종목 0건 누락 보장은 원본 전체 목록과의 비교가 필요함. DOM 스크롤은 사이트 상태에 의존."}
        folder.mkdir(parents=True,exist_ok=True)
        with atomic_text(path_bundle(folder)['diag']) as fp:
            json.dump(diagnostics,fp,ensure_ascii=False,indent=2)
        if not prices:
            diagnostics['status']='no_verifiable_quotes'
            diagnostics['warnings'].append('현재 표시 범위에서 검증 가능한 가격 0건: 휴장·미고시·DOM 변경을 구분하려면 진단 확인 필요. 기존 DB/Excel 유지.')
            with atomic_text(path_bundle(folder)['diag']) as fp:
                json.dump(diagnostics,fp,ensure_ascii=False,indent=2)
            return [],diagnostics
        if cancelled.is_set():raise SessionError('저장 직전 중단 요청: 기존 DB 보존')
        saved=time.perf_counter()
        save_sqlite(path_bundle(folder)["db"],prices,inventory,diagnostics)
        try:
            if not defer_export:
                export_all(folder,workbook_path)
        except Exception as exc:
            diagnostics['warnings'].append('DB 저장 완료; 내보내기 재시도 필요: '+str(exc))
        diagnostics['timings']['storage_seconds']=round(time.perf_counter()-saved,3)
        diagnostics['timings']['total_seconds']=round(time.perf_counter()-started,3)
        with atomic_text(path_bundle(folder)['diag']) as fp:
            json.dump(diagnostics,fp,ensure_ascii=False,indent=2)
        return prices,diagnostics


def save_sqlite(db: Path,prices: list[Price],inventory:list[dict],diagnostics:dict):
    workspace_id=current_workspace()[1]
    db.parent.mkdir(parents=True,exist_ok=True)
    from storage_runtime import migrate_database,checkpoint_prices
    migrate_database(db)
    with closing(sqlite3.connect(db,timeout=30)) as cx, cx:
        cx.executescript("""
        CREATE TABLE IF NOT EXISTS prices(
          workspace_id TEXT NOT NULL, symbol TEXT NOT NULL, assessment_date TEXT NOT NULL,
          low TEXT,mid TEXT,high TEXT,change_pct TEXT,unit TEXT NOT NULL,
          description TEXT,widget TEXT NOT NULL,price_mode TEXT NOT NULL,source TEXT NOT NULL,
          view_key TEXT NOT NULL,period_label TEXT NOT NULL DEFAULT '',
          collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(workspace_id,symbol,assessment_date,price_mode,unit,view_key)
        );
        CREATE TABLE IF NOT EXISTS instruments(
          workspace_id TEXT NOT NULL, symbol TEXT NOT NULL,description TEXT NOT NULL,
          unit TEXT NOT NULL,first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(workspace_id,symbol,description,unit)
        );
        CREATE TABLE IF NOT EXISTS collection_runs(
          id INTEGER PRIMARY KEY AUTOINCREMENT,completed_at TEXT DEFAULT CURRENT_TIMESTAMP,
          workspace_id TEXT,widget_count INTEGER,series_count INTEGER,price_count INTEGER,warnings TEXT
        );
        CREATE TABLE IF NOT EXISTS price_revisions(
          id INTEGER PRIMARY KEY, changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
          workspace_id TEXT, symbol TEXT, assessment_date TEXT, view_key TEXT,
          price_mode TEXT, unit TEXT, old_values TEXT, new_values TEXT
        );
        CREATE TRIGGER IF NOT EXISTS prices_audit BEFORE UPDATE ON prices
        WHEN OLD.low IS NOT NEW.low OR OLD.mid IS NOT NEW.mid OR OLD.high IS NOT NEW.high
          OR OLD.change_pct IS NOT NEW.change_pct
        BEGIN
          INSERT INTO price_revisions(workspace_id,symbol,assessment_date,view_key,price_mode,unit,old_values,new_values)
          VALUES(OLD.workspace_id,OLD.symbol,OLD.assessment_date,OLD.view_key,OLD.price_mode,OLD.unit,
          json_array(OLD.low,OLD.mid,OLD.high,OLD.change_pct),json_array(NEW.low,NEW.mid,NEW.high,NEW.change_pct));
        END;
        """)
        for w in inventory:
            for code in w["codes"]:
                desc=w["description_by_code"].get(code,"")
                unit=unit_from_description(desc)
                cx.execute("""INSERT INTO instruments(workspace_id,symbol,description,unit)
                 VALUES(?,?,?,?) ON CONFLICT(workspace_id,symbol,description,unit)
                 DO UPDATE SET last_seen=CURRENT_TIMESTAMP""",(workspace_id,code,desc,unit))
        for p in prices:
            cx.execute("""INSERT INTO prices(workspace_id,symbol,assessment_date,low,mid,high,change_pct,
              unit,description,widget,price_mode,source,view_key,period_label)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(workspace_id,symbol,assessment_date,price_mode,unit,view_key)
              DO UPDATE SET low=COALESCE(excluded.low,prices.low),mid=COALESCE(excluded.mid,prices.mid),high=COALESCE(excluded.high,prices.high),
                change_pct=COALESCE(excluded.change_pct,prices.change_pct),description=CASE WHEN excluded.description='' THEN prices.description ELSE excluded.description END,widget=excluded.widget,
                source=excluded.source,period_label=excluded.period_label,collected_at=CURRENT_TIMESTAMP
              WHERE (excluded.low IS NOT NULL AND excluded.low IS NOT prices.low)
                 OR (excluded.mid IS NOT NULL AND excluded.mid IS NOT prices.mid)
                 OR (excluded.high IS NOT NULL AND excluded.high IS NOT prices.high)
                 OR (excluded.change_pct IS NOT NULL AND excluded.change_pct IS NOT prices.change_pct)
                 OR (excluded.description!='' AND excluded.description IS NOT prices.description)
                 OR excluded.widget IS NOT prices.widget OR excluded.source IS NOT prices.source
                 OR excluded.period_label IS NOT prices.period_label""",
                (workspace_id,p.symbol,p.date,p.low,p.mid,p.high,p.change_pct,p.unit,p.description,
                 p.widget,p.price_mode,p.source,p.view_key,p.period_label))
        cx.execute("""INSERT INTO collection_runs(workspace_id,widget_count,series_count,price_count,warnings)
          VALUES(?,?,?,?,?)""",(workspace_id,diagnostics["widget_count"],len(diagnostics["found_symbols"]),
                            len(prices),"\n".join(diagnostics["warnings"])))
        checkpoint_prices(cx,workspace_id,prices,[] if diagnostics.get('warnings') else inventory)


def export_files(folder: Path):
    b=path_bundle(folder)
    if not b['db'].exists():raise ValueError('저장된 DB가 없습니다. 먼저 수집하세요.')
    with closing(sqlite3.connect(b["db"])) as cx:
        cx.row_factory=sqlite3.Row
        with atomic_text(b['csv'],newline='',encoding='utf-8-sig') as fp:
            writer=csv.writer(fp)
            cols=["symbol","assessment_date","low","mid","high","change_pct","unit",
                  "description","widget","price_mode","source","period_label","collected_at"]
            writer.writerow(cols)
            for row in cx.execute("SELECT "+",".join(cols)+" FROM prices WHERE workspace_id=? ORDER BY assessment_date DESC,symbol,widget",(current_workspace()[1],)):
                writer.writerow([row[c] for c in cols])
        with atomic_text(b['master'],newline='',encoding='utf-8-sig') as fp:
            writer=csv.writer(fp);cols=["symbol","description","unit","first_seen","last_seen"]
            writer.writerow(cols)
            for row in cx.execute("SELECT "+",".join(cols)+" FROM instruments WHERE workspace_id=? ORDER BY symbol,unit",(current_workspace()[1],)):
                writer.writerow([row[c] for c in cols])
        # Preserve full provenance on workspace changes without altering the legacy active-only CSV schema.
        with atomic_text(folder/'fastmarkets_all_workspaces.csv',newline='',encoding='utf-8-sig') as fp:
            writer=csv.writer(fp)
            allcols=['workspace_id','symbol','assessment_date','low','mid','high','change_pct',
                     'unit','description','widget','price_mode','source','view_key','period_label','collected_at']
            writer.writerow(allcols)
            for row in cx.execute('SELECT '+','.join(allcols)+' FROM prices ORDER BY assessment_date DESC,workspace_id,symbol'):
                writer.writerow([row[c] for c in allcols])


def install_packages():
    cmd=[sys.executable,"-m","pip","install","--disable-pip-version-check","selenium>=4.25,<5","keyring>=25,<27"]
    if not IS_WINDOWS:cmd.append("openpyxl>=3.1,<4")  # plain-xlsx offline tests only; Windows uses COM.
    if IS_WINDOWS:cmd.extend(['uiautomation>=2.0,<3','pyperclip>=1.9,<2','pywin32>=306'])
    result=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=240)
    if result.returncode:
        raise RuntimeError("패키지 설치 실패 (사내망/프록시 확인):\n"+(result.stderr or result.stdout)[-2000:])
    return "Selenium / keyring / Excel COM(pywin32) / ECM 패키지 설치 완료."


def get_keyring():
    """Windows에서는 보안 저장소(Windows Credential Manager)만 사용한다.

    일반 keyring.get_keyring()은 환경에 따라 다른 backend 또는 평문 저장
    플러그인을 선택할 수 있으므로 Windows에서는 WinVault를 명시적으로 사용한다.
    """
    if IS_WINDOWS:
        try:
            from keyring.backends.Windows import WinVaultKeyring
            return WinVaultKeyring()
        except ImportError:
            return None
    try:
        import keyring
        return keyring
    except ImportError:
        return None


def credentials_get():
    """저장된 이메일/비밀번호 쌍을 읽는다. 실패 시 빈 값 반환."""
    kr=get_keyring()
    if kr is None:return "",""
    try:
        user=kr.get_password(KEY_SERVICE,"username") or ""
        return user,(kr.get_password(KEY_SERVICE,"password:"+user) or "") if user else ""
    except Exception:
        return "",""


def credentials_set(user,pwd):
    """사용자 명시 동작 또는 로그인 성공 후 저장. 저장 후 읽기 검증."""
    user=str(user or "").strip()
    if not user or not pwd:
        raise ValueError("이메일과 비밀번호를 모두 입력해야 저장할 수 있습니다.")
    kr=get_keyring()
    if kr is None:
        raise RuntimeError("Windows 자격 증명 저장소를 사용할 수 없습니다. '필수 패키지 설치'를 먼저 실행하세요.")
    previous=kr.get_password(KEY_SERVICE,"username") or ""
    # 비밀번호를 먼저 써서 실패 시 기존 이메일 포인터를 보존한다.
    kr.set_password(KEY_SERVICE,"password:"+user,pwd)
    kr.set_password(KEY_SERVICE,"username",user)
    check_user=kr.get_password(KEY_SERVICE,"username") or ""
    check_pwd=kr.get_password(KEY_SERVICE,"password:"+user) or ""
    if check_user != user or check_pwd != pwd:
        raise RuntimeError("계정정보를 기록했지만 저장된 내용을 다시 읽지 못했습니다. Windows 자격 증명 관리자를 확인하세요.")
    if previous and previous != user:
        try:kr.delete_password(KEY_SERVICE,"password:"+previous)
        except Exception:pass
    return True


def credentials_delete():
    kr=get_keyring()
    if kr is None:
        raise RuntimeError("Windows 자격 증명 저장소를 사용할 수 없습니다.")
    user=kr.get_password(KEY_SERVICE,"username") or ""
    # 저장된 사용자 포인터부터 제거하고, 비밀번호 항목도 제거한다.
    for key in (["username","password:"+user] if user else ["username"]):
        try:kr.delete_password(KEY_SERVICE,key)
        except Exception as e:
            # 저장되지 않은 항목은 삭제할 필요가 없다.
            if kr.get_password(KEY_SERVICE,key) is not None:
                raise RuntimeError("저장된 계정정보를 삭제하지 못했습니다.") from e
    if kr.get_password(KEY_SERVICE,"username") is not None:
        raise RuntimeError("계정정보 삭제 검증에 실패했습니다.")
    return True


def schedule_daily(time_hhmm):
    if not IS_WINDOWS:raise RuntimeError("예약 실행은 Windows에서만 지원됩니다.")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d",time_hhmm):
        raise ValueError("예약 시각은 HH:MM 형식이어야 합니다.")
    APP_HOME.mkdir(parents=True,exist_ok=True)
    cmd=APP_HOME/"daily.cmd"
    script=Path(__file__).resolve()
    cmd.write_text(f'@echo off\n"{sys.executable}" "{script}" --once --with-fx >> "{APP_HOME / "scheduler.log"}" 2>&1\n',encoding="mbcs")
    # /IT requires Windows user signed in; no hidden password storage.
    result=subprocess.run(["schtasks","/Create","/F","/TN","FastmarketsCollectorDaily",
                           "/SC","DAILY","/ST",time_hhmm,"/TR",f'cmd.exe /c "{cmd}"',"/IT"],
                          capture_output=True,text=True,encoding="mbcs",errors="replace",timeout=20)
    if result.returncode:raise RuntimeError(result.stderr or result.stdout)
    return result.stdout.strip()


def main_gui():
    import tkinter as tk
    from tkinter import ttk,messagebox,filedialog
    cfg=config_load()
    root=tk.Tk();root.title("Fastmarkets + ECM + 환율 | v3.5.5 · Chrome 9444")
    root.geometry("1280x880");root.minsize(1060,760)
    root.option_add("*Font", "{Malgun Gothic} 10" if IS_WINDOWS else "{Arial} 10")
    style=ttk.Style()
    if IS_WINDOWS and "vista" in style.theme_names():style.theme_use("vista")
    style.configure("Treeview",rowheight=26)
    style.configure("Treeview.Heading",font=("Malgun Gothic",10,"bold"))
    queue=Queue();stop=threading.Event();browser=ChromeSession(lambda m:queue.put(("log",m)))
    running=False
    remembered,stored_pwd=credentials_get()
    user=tk.StringVar(value=remembered);pwd=tk.StringVar();remember=tk.BooleanVar(value=bool(remembered and stored_pwd))
    credential_status=tk.StringVar(value=("저장된 계정 확인됨 · 비밀번호는 화면에 표시하지 않습니다." if remembered and stored_pwd else
                                        "저장된 계정 없음 · 입력 후 '계정정보 저장' 버튼을 누르세요."))
    folder=tk.StringVar(value=str(cfg["data_dir"]));days=tk.StringVar(value=str(cfg["lookback_days"]))
    automatic=tk.StringVar(value=str(cfg["auto_time"]))
    workbook_path=tk.StringVar(value=cfg.get('workbook_path',''))
    workspace_url=tk.StringVar(value=cfg.get('workspace_url',WORKSPACE_URL))
    ecm_search=tk.StringVar(value=cfg.get('ecm_search','금속 가격 현황'))
    ecm_title=tk.StringVar(value=cfg.get('ecm_title','(리뉴얼)금속 가격 현황'))
    state=tk.StringVar(value="준비 — Chrome 연결 후 전체 시세 수집을 누르세요.")
    buttons=[]

    def save_options():
        url,_=verify_workspace_url(workspace_url.get())
        if not ecm_search.get().strip() or not ecm_title.get().strip():
            raise ValueError('ECM 검색어와 대상 문서 이름을 입력하세요.')
        config_save({"data_dir":folder.get(),"lookback_days":int(days.get()),"auto_time":automatic.get(),
          "workbook_path":workbook_path.get(),"workspace_url":url,"ecm_search":ecm_search.get().strip(),
          "ecm_title":ecm_title.get().strip(),"maximize_chrome":cfg.get('maximize_chrome',True)})

    def save_settings_button(label):
        try:
            save_options()
            state.set(f'{label} 저장 완료')
        except Exception as exc:
            messagebox.showerror('설정 확인 필요',str(exc))

    def choose_workbook():
        if running:return
        chosen=filedialog.asksaveasfilename(parent=root,title='계속 갱신할 누적 Excel 파일',defaultextension='.xlsx',filetypes=[('Excel','*.xlsx')],initialfile='fastmarkets_prices.xlsx',initialdir=folder.get())
        if chosen:
            if Path(chosen).exists() and not messagebox.askyesno('누적 Excel 대상',
                '선택 파일의 수집 전용 시트는 Excel COM으로 갱신됩니다. 다른 시트는 보존합니다. 원본 백업을 권장합니다. 계속할까요?'):
                return
            workbook_path.set(chosen);save_options()

    def directory():
        if running:return
        chosen=filedialog.askdirectory(parent=root,title="가격 자료 저장 폴더 선택",initialdir=folder.get())
        if chosen:
            folder.set(chosen)
            try:save_options()
            except Exception:pass

    def launch(label,fn,kind="other"):
        nonlocal running
        if running:return
        running=True;stop.clear();state.set(label+" 실행 중...")
        for b in buttons:b.configure(state="disabled")
        btn_cancel.configure(state="normal" if kind=="collect" else "disabled")
        def work():
            try:
                if kind in {"login", "collect", "fx"}:
                    with exclusive_browser_job():
                        result=fn()
                else:
                    result=fn()
                if kind in {'collect','import'}:
                    rows,diag=result
                    queue.put(('preview',latest_quotes(load_prices(Path(diag.get('data_dir',active_folder))))))
                if kind=='ecm':log(Path(active_folder),str(result))
                queue.put(("result",kind,label,result))
            except Exception as e:
                import traceback
                private_job=('계정정보' in label or '로그인' in label)
                log(Path(active_folder),f"{label} 실패 ({type(e).__name__}): "
                    +('인증단계 오류 — 화면 확인' if private_job else str(e)))
                # Avoid dumping authentication errors or any browser request payload.
                trace='인증 예외 세부내용 미기록' if private_job else ''.join(traceback.format_exception(type(e),e,e.__traceback__)[-7:])
                with (Path(active_folder)/'collector_error_trace.log').open('a',encoding='utf-8') as ef:
                    ef.write(f"[{datetime.now().isoformat()}] {label}\n{trace}\n")
                queue.put(("error",label,str(e)))
        active_folder=folder.get()
        threading.Thread(target=work,daemon=True,name="fastmarkets-collector-worker").start()

    def save_credential_action():
        u,p=user.get().strip(),pwd.get()
        if not u or not p:
            messagebox.showwarning("계정정보 저장", "이메일과 비밀번호를 모두 입력한 후 저장 버튼을 누르세요.")
            return
        def work():
            credentials_set(u,p)
            return u
        launch("계정정보 보안 저장",work,"credentials-saved")

    def delete_credential_action():
        if not messagebox.askyesno("계정정보 삭제", "Windows에 저장된 Fastmarkets 이메일·비밀번호를 삭제하시겠습니까?"):
            return
        launch("저장 정보 삭제",credentials_delete,"credentials-deleted")

    def connect_action():
        save_options()
        u,p=user.get().strip(),pwd.get()
        do_save=remember.get()
        def work():
            u0,p0=credentials_get()
            signed=browser.open_workspace(u or u0,p or (p0 if (u==u0 or not u) else ""))
            # 기존 v3는 로그인 성공하고 두 칸에 모두 새로 입력한 경우에만 저장해
            # 이미 로그인된 세션/수동 인증 후 저장되지 않는 혼동이 있었다.
            # 명시적인 '계정정보 저장' 버튼은 로그인 결과와 무관하게 저장 가능하다.
            if signed and do_save and u and p:
                credentials_set(u,p)
                return {"signed": True, "saved": True}
            return {"signed": signed, "saved": False}
        launch("Chrome 연결 · 로그인",work,"login")

    def collect_action():
        try:
            v=int(days.get())
            if not 0<=v<=3650:raise ValueError()
            target=Path(folder.get()).expanduser()
            if not str(target).strip():raise ValueError()
            save_options()
        except Exception:
            messagebox.showerror("설정 오류","수집 기간은 0(전체)~3650일, 저장 폴더는 유효한 경로여야 합니다.")
            return
        excel=workbook_path.get()
        def collect():
            rows,diag=browser.scrape(v,target,stop,workbook_path=excel,defer_export=True)
            diag['data_dir']=str(target)
            if not stop.is_set():
                queue.put(('log','FMB 완료 → 같은 Chrome의 임시 탭에서 USD/CNH/JPY/EUR 수집'))
                try:
                    fx=fx_one_time(target,excel,driver=browser.driver,defer_export=True,
                                   gui_log=lambda message: queue.put(('log',message)))
                    diag['fx']=fx
                    if fx.get('warnings'):
                        diag['warnings'].extend('SMBS: '+msg for msg in fx['warnings'])
                except Exception as exc:
                    diag['warnings'].append(f'SMBS 수집 실패: {type(exc).__name__}: {str(exc)[:220]}')
                # Rebuild once, after both sources have been independently saved.
                try:
                    diag['excel']=str(export_all(target,excel))
                except Exception as exc:
                    diag['warnings'].append('DB 수집 완료 / Excel 갱신 실패: '+str(exc))
            return rows,diag
        launch("전체 시세 수집",collect,"collect")

    def output_csv():
        target=Path(folder.get())
        excel=workbook_path.get()
        launch('CSV / 누적 Excel 내보내기',lambda:export_all(target,excel))

    def import_csv_action():
        chosen=filedialog.askopenfilename(parent=root,title='Fastmarkets 공식 CSV 선택',filetypes=[('CSV','*.csv'),('모든 파일','*.*')])
        if not chosen:return
        target=Path(folder.get())
        excel=workbook_path.get()
        launch('공식 CSV 검증·가져오기',lambda:import_official(Path(chosen),target,excel),'import')

    def fx_action():
        target=Path(folder.get())
        excel=workbook_path.get()
        def work():
            browser.connect()
            return fx_one_time(target, excel, driver=browser.driver,
                               gui_log=lambda message: queue.put(('log',message)))
        launch('서울외국환중개 4개 통화 수집',work,'fx')

    def ecm_action():
        save_options()
        target=Path(folder.get())
        search_value=ecm_search.get().strip()
        title_value=ecm_title.get().strip()
        def work():
            from ecm_automation import execute
            return execute(lambda s:log(target,s,lambda line:queue.put(('log',line))),
                search_text=search_value,target_title=title_value)
        launch('ECM 검색 · Excel 열기',work,'ecm')

    def schedule_action():
        try:save_options()
        except Exception as exc:
            messagebox.showerror('예약 설정',str(exc));return
        hhmm=automatic.get()
        launch('자동 수집 예약',lambda:schedule_daily(hhmm))

    header=ttk.Frame(root,padding=(16,13));header.pack(fill="x")
    ttk.Label(header,text="FASTMARKETS  /  기획재무그룹",font=("Malgun Gothic",16,"bold")).pack(anchor="w")
    ttk.Label(header,text="전용 디버그 Chrome :9444 | 프로필: ChromeProfile_9444 | 기존 Chrome :9222 · Edge :9337 변경 없음",foreground="#5b6874").pack(anchor="w",pady=(5,0))

    login=ttk.LabelFrame(root,text="로그인",padding=12);login.pack(fill="x",padx=16,pady=(0,9))
    ttk.Label(login,text="이메일").grid(row=0,column=0,sticky="w")
    ttk.Entry(login,textvariable=user,width=28).grid(row=0,column=1,padx=8,sticky="w")
    ttk.Label(login,text="비밀번호").grid(row=0,column=2,sticky="w")
    ttk.Entry(login,textvariable=pwd,show="●",width=27).grid(row=0,column=3,padx=8,sticky="w")
    ttk.Checkbutton(login,text="로그인 성공 시 저장",variable=remember).grid(row=0,column=4,padx=8)
    btn_cred_save=ttk.Button(login,text="계정정보 저장",command=save_credential_action)
    btn_cred_save.grid(row=0,column=5,padx=6)
    btn_cred_delete=ttk.Button(login,text="저장 정보 삭제",command=delete_credential_action)
    btn_cred_delete.grid(row=0,column=6,padx=6)
    ttk.Label(login,textvariable=credential_status,foreground="#19633d").grid(row=1,column=0,columnspan=7,sticky="w",pady=(10,0))
    ttk.Label(login,text="저장 버튼은 로그인 성공 여부와 관계없이 즉시 Windows 자격 증명 관리자에 기록·검증합니다. Fastmarkets 전용 Chrome 프로필에서만 로그인 세션을 재사용합니다.",foreground="#5b6874").grid(row=2,column=0,columnspan=7,sticky="w",pady=(4,0))
    buttons.extend([btn_cred_save,btn_cred_delete])

    options=ttk.LabelFrame(root,text="수집 및 저장",padding=12);options.pack(fill="x",padx=16,pady=(0,9))
    ttk.Label(options,text="저장 폴더").grid(row=0,column=0,sticky="w")
    ttk.Entry(options,textvariable=folder,width=87).grid(row=0,column=1,columnspan=5,sticky="ew",padx=8)
    ttk.Button(options,text="찾아보기",command=directory).grid(row=0,column=6,padx=6)
    ttk.Label(options,text="기간(일)").grid(row=1,column=0,sticky="w",pady=(9,0))
    ttk.Entry(options,textvariable=days,width=7).grid(row=1,column=1,sticky="w",padx=8,pady=(9,0))
    ttk.Label(options,text="0 = 가능한 전체 이력 · 최근 31일 권장 · 차트/표의 실제 표시 날짜 기준",foreground="#5b6874").grid(row=1,column=2,columnspan=5,sticky="w",pady=(9,0))
    options.grid_columnconfigure(1,weight=1)
    ttk.Label(options,text='누적 Excel').grid(row=2,column=0,sticky='w',pady=(8,0))
    ttk.Entry(options,textvariable=workbook_path,width=70).grid(row=2,column=1,columnspan=5,sticky='ew',padx=8,pady=(8,0))
    ttk.Button(options,text='파일 지정',command=choose_workbook).grid(row=2,column=6,padx=6,pady=(8,0))
    actual_excel_target=tk.StringVar()
    def update_excel_target(*_):
        chosen=workbook_path.get().strip()
        actual_excel_target.set('실제 저장 대상: '+str(Path(chosen).expanduser() if chosen else path_bundle(Path(folder.get()))['xlsx'])
            + (' (자동 생성/계속 갱신)' if not chosen else ' (지정 파일 계속 갱신)'))
    folder.trace_add('write',update_excel_target)
    workbook_path.trace_add('write',update_excel_target)
    update_excel_target()
    ttk.Label(options,textvariable=actual_excel_target,foreground='#416079').grid(
        row=5,column=1,columnspan=6,sticky='w',padx=8,pady=(4,0))
    ttk.Label(options,text='대시보드 URL').grid(row=3,column=0,sticky='w',pady=(8,0))
    ttk.Entry(options,textvariable=workspace_url,width=87).grid(row=3,column=1,columnspan=5,sticky='ew',padx=8,pady=(8,0))
    ttk.Button(options,text='주소 저장',command=lambda:save_settings_button('대시보드 주소')).grid(row=3,column=6,padx=6,pady=(8,0))
    ttk.Label(options,text='ECM 검색어').grid(row=4,column=0,sticky='w',pady=(8,0))
    ttk.Entry(options,textvariable=ecm_search,width=38).grid(row=4,column=1,columnspan=3,sticky='ew',padx=8,pady=(8,0))
    ttk.Label(options,text='문서명').grid(row=4,column=4,sticky='e',pady=(8,0))
    ttk.Entry(options,textvariable=ecm_title,width=34).grid(row=4,column=5,sticky='ew',padx=8,pady=(8,0))
    ttk.Button(options,text='ECM 설정 저장',command=lambda:save_settings_button('ECM 설정')).grid(row=4,column=6,padx=6,pady=(8,0))

    actions=ttk.Frame(root,padding=(16,0,16,12));actions.pack(fill="x")
    def add(text,command):
        b=ttk.Button(actions,text=text,command=command)
        b.pack(side="left",padx=(0,8),ipadx=6,ipady=5)
        buttons.append(b)
    add("필수 패키지 설치",lambda:launch("패키지 설치",install_packages))
    add("① Chrome 연결 · 로그인",connect_action)
    add("② FMB + 환율 4종 한 번에 수집",collect_action)
    add("③ 환율만 갱신 (9444 같은 Chrome)",fx_action)
    add("CSV / Excel 갱신",output_csv)
    add("공식 CSV 가져오기",import_csv_action)
    add("ECM 컨트롤",ecm_action)
    btn_cancel=ttk.Button(actions,text="수집 중단",command=lambda:(stop.set(),state.set("중단 요청 — 현재 작업 정리 중...")),state="disabled")
    btn_cancel.pack(side="right")

    sched=ttk.Frame(root,padding=(16,0,16,10));sched.pack(fill="x")
    ttk.Label(sched,text="매일 자동 실행").pack(side="left")
    ttk.Entry(sched,textvariable=automatic,width=9).pack(side="left",padx=8)
    bsch=ttk.Button(sched,text="Windows 예약 등록",command=schedule_action)
    bsch.pack(side="left");buttons.append(bsch)
    ttk.Label(sched,text="로그인 상태의 Windows PC가 켜져 있어야 실행됩니다.",foreground="#5b6874").pack(side="left",padx=12)

    numbers=tk.StringVar(value="위젯 —  | 발견 종목 —  | 가격 확보 종목 —  | 신규 수집행 —  | 경고 —")
    ttk.Label(root,textvariable=numbers,font=("Malgun Gothic",10,"bold"),padding=(16,2)).pack(anchor="w")
    notebook=ttk.Notebook(root);notebook.pack(fill='both',expand=True,padx=16,pady=6)
    latest_panel=ttk.Frame(notebook,padding=6);notebook.add(latest_panel,text='최신 금속 가격')
    ttk.Label(latest_panel,text='당일 발표가 없으면 이전 발표일을 표시합니다. Actual / Unspecified만 표시하며 월평균·Forecast는 원자료에서 확인하세요.').pack(anchor='w',pady=5)
    latest_cols=('symbol','description','date','low','mid','high','unit','change_pct','price_mode','freshness')
    latest_tree=ttk.Treeview(latest_panel,columns=latest_cols,show='headings',height=12)
    for c,n in zip(latest_cols,('코드','금속 / 설명','발표일','Low','Mid','High','단위','변동 %','구분','최신성')):
        latest_tree.heading(c,text=n);latest_tree.column(c,width=230 if c=='description' else 100,minwidth=70)
    latest_tree.tag_configure('today',background='#e3f3eb')
    lscroll=ttk.Scrollbar(latest_panel,orient='vertical',command=latest_tree.yview)
    latest_tree.configure(yscrollcommand=lscroll.set)
    latest_tree.pack(side='left',fill='both',expand=True);lscroll.pack(side='right',fill='y')
    container=ttk.Frame(notebook,padding=6);notebook.add(container,text='원자료 · 이번 수집')
    log_panel=ttk.Frame(notebook,padding=6);notebook.add(log_panel,text='진행 / 진단 로그')
    log_box=tk.Text(log_panel,state='disabled',height=12,wrap='word');log_box.pack(fill='both',expand=True)
    cols=("symbol","date","low","mid","high","unit","mode","widget")
    names=("종목코드","발표일","Low","Mid","High","단위","구분","위젯")
    widths=(130,95,85,85,85,94,110,260)
    tree=ttk.Treeview(container,columns=cols,show="headings",height=11)
    for col,name,width in zip(cols,names,widths):
        tree.heading(col,text=name);tree.column(col,width=width,minwidth=60,anchor="w" if col in ("symbol","date","unit","mode","widget") else "e")
    tree.pack(side="left",expand=True,fill="both")
    sc=ttk.Scrollbar(container,orient="vertical",command=tree.yview);sc.pack(side="right",fill="y")
    tree.configure(yscrollcommand=sc.set)
    ttk.Label(root,textvariable=state,padding=(16,6),wraplength=1100).pack(fill="x")
    footer=ttk.Frame(root,padding=(16,5,16,12));footer.pack(fill="x")
    ttk.Label(footer,text="수집 실패 시 last_diagnostic.json / collector.log 확인. 기존 데이터는 지우지 않습니다.",foreground="#5b6874").pack(side="left")
    def on_close():
        if running:
            stop.set()
            state.set("종료 요청 — 수집 작업이 멈춘 후 프로그램을 종료할 수 있습니다.")
            messagebox.showinfo("종료 대기", "진행 중인 브라우저 작업에 중단을 요청했습니다. 작업이 종료된 후 다시 닫아주세요.")
            return
        threading.Thread(target=browser.detach,name='fastmarkets-driver-detach',daemon=False).start()
        root.destroy()

    ttk.Button(footer,text="프로그램 종료",command=on_close).pack(side="right")
    root.protocol("WM_DELETE_WINDOW",on_close)

    def pump():
        nonlocal running
        while True:
            try:item=queue.get_nowait()
            except Empty:break
            if item[0]=="log":
                log(Path(folder.get()),'GUI: '+str(item[1]))
                state.set(item[1])
                log_box.configure(state='normal');log_box.insert('end',str(item[1])+'\n');log_box.see('end');log_box.configure(state='disabled')
            elif item[0]=='preview':
                for x in latest_tree.get_children():latest_tree.delete(x)
                for r in item[1][:1500]:
                    r['freshness']='당일' if r['freshness']=='当日' else '이전 발표'
                    latest_tree.insert('','end',values=tuple(r.get(c) or '' for c in latest_cols),tags=('today',) if r['freshness']=='당일' else ())
            elif item[0]=="error":
                _,name,error=item
                running=False
                for b in buttons:b.configure(state="normal")
                btn_cancel.configure(state="disabled")
                state.set(f"{name} 실패: {error}")
                log(Path(folder.get()),f"오류: {name}: {error}")
                messagebox.showerror(name+" 실패",error[:1800])
            elif item[0]=="result":
                _,kind,name,value=item
                running=False
                for b in buttons:b.configure(state="normal")
                btn_cancel.configure(state="disabled")
                if kind in {"collect","import"}:
                    prices,diag=value
                    for x in tree.get_children():tree.delete(x)
                    for p in prices[:1500]:
                        tree.insert("","end",values=(p.symbol,p.date,p.low or "",p.mid or "",p.high or "",p.unit,p.price_mode,p.widget))
                    numbers.set(f"위젯 {diag['processed_widgets']}/{diag['widget_count']}  | 발견 종목 {len(diag['found_symbols'])}  | 가격 확보 종목 {len(diag['price_symbols'])}  | 수집행 {len(prices)}  | 경고 {len(diag['warnings'])}")
                    prefix='신규 가격 없음 · 기존 DB 유지' if diag.get('status')=='no_verifiable_quotes' else '가격 DB 저장 완료'
                    state.set(f"{prefix}: {path_bundle(Path(diag.get('data_dir',folder.get())))['csv']}  /  확인 사항 {len(diag['warnings'])}개")
                    if diag["warnings"]:
                        for w in diag['warnings']:
                            log(Path(folder.get()),'FMB 경고: '+str(w))
                        messagebox.showwarning("부분 수집·검증 필요",
                            f"검증 필요 {len(diag['warnings'])}건.\n자세한 내용은 VSC 터미널의 FMB 경고 및 last_diagnostic.json을 확인하세요.")
                    if kind=='import':
                        comparison=diag['csv_report']['comparison']
                        state.set(f"CSV 저장: 일치 {comparison['matched']} / 불일치 {comparison['mismatched']} / CSV만 {comparison['official_only']} / DOM만 {comparison['dom_only']}")
                elif kind=='fx':
                    excel_ok=bool(value.get('workbook'))
                    state.set('SMBS 환율 '+str(value.get('collected',0))+'건 수집, 신규 '
                              +str(value.get('stored',{}).get('inserted',0))+'건, 정정 '
                              +str(value.get('stored',{}).get('updated',0))+'건. Excel '+('갱신' if excel_ok else '미갱신'))
                    if value.get('warnings'):
                        for w in value['warnings']:
                            log(Path(folder.get()),'SMBS 경고: '+str(w))
                        messagebox.showwarning('환율 일부 수집 보류',
                            f"환율 수집 검증 {len(value['warnings'])}건. VSC 터미널 및 fx_last_diagnostic.json 확인")
                elif kind=='cached':
                    queue.put(('preview',latest_quotes(value)))
                    state.set('저장 DB의 최신 가격 표시 완료 · 새 가격은 전체 수집으로 갱신하세요.')
                elif kind=="login":
                    if value["saved"]:
                        credential_status.set("저장된 계정 확인됨 · Windows 자격 증명 관리자에 보관 중")
                    state.set("Chrome 연결 및 로그인 완료" if value["signed"] else
                              "Chrome에서 로그인을 완료한 뒤 다시 수집하세요. 계정정보는 별도 저장 버튼으로 저장할 수 있습니다.")
                elif kind=="credentials-saved":
                    remember.set(True)
                    credential_status.set("저장 확인 완료 · Windows 자격 증명 관리자 (계정: "+str(value)+")")
                    state.set("계정정보 보안 저장 및 다시 읽기 확인 완료. 재실행해도 자동으로 불러옵니다.")
                    pwd.set("")
                elif kind=="credentials-deleted":
                    remember.set(False)
                    pwd.set("")
                    user.set("")
                    credential_status.set("저장된 계정 없음 · 삭제 검증 완료")
                    state.set("저장된 로그인 정보 삭제 완료")
                else:
                    state.set(name+" 완료"+(": "+str(value) if isinstance(value,str) else ""))
        root.after(140,pump)
    root.after(140,pump)
    root.after(250,lambda:launch('저장 가격 불러오기',lambda:load_prices(Path(cfg['data_dir'])),'cached'))
    root.mainloop()


def fx_one_time(folder, workbook_path=None, *, start=None, end=None, gui_log=None,
                driver=None, defer_export=False):
    """SMBS via caller-owned Chrome 9444: temporary tab, same SQLite, same Excel."""
    from smbs_rates import collect_rates,save_rates
    target=Path(folder)
    target.mkdir(parents=True,exist_ok=True)
    try:
        rates,diag=collect_rates(start=start,end=end,logger=(gui_log or (lambda s:log(target,s))),driver=driver)
    except Exception as exc:
        failure={'started_at':datetime.now().isoformat(),'source':'SMBS',
                 'collected':0,'warnings':[f'{type(exc).__name__}: {str(exc)[:500]}'],
                 'note':'수집 전 단계 실패. 기존 SQLite/Excel 변경 없음'}
        with atomic_text(target/'fx_last_diagnostic.json') as fp:
            json.dump(failure,fp,ensure_ascii=False,indent=2)
        raise
    if rates:
        stored=save_rates(path_bundle(target)['db'],rates)
        diag['stored']=stored
        latest={}
        for q in rates:
            if q.currency not in latest or q.quote_date>latest[q.currency].quote_date:
                latest[q.currency]=q
        diag['latest_values']={k:{'date':v.quote_date,'rate':v.rate,'difference':v.difference,'unit':v.unit}
                              for k,v in sorted(latest.items())}
        for code,quote in sorted(latest.items()):
            log(target,f"SMBS verified {code} {quote.quote_date}: {quote.rate} KRW/{quote.unit} {code}, change {quote.difference}",gui_log)
        try:
            if not defer_export:
                diag['workbook']=str(export_workbook(target,output_path=workbook_path))
        except Exception as exc:
            diag['warnings'].append('환율 DB 저장 성공 / Excel 갱신 실패: '+str(exc))
    else:
        diag['stored']={'inserted':0,'updated':0,'unchanged':0}
    diag['collected']=len(rates)
    with atomic_text(target/'fx_last_diagnostic.json') as fp:
        json.dump(diag,fp,ensure_ascii=False,indent=2)
    return diag


def one_time(days=None):
    cfg=config_load()
    folder=Path(cfg["data_dir"])
    if days is None:days=int(cfg["lookback_days"])
    b=ChromeSession(lambda m:log(folder,m))
    try:
        with exclusive_browser_job():
            u,p=credentials_get()
            if not b.open_workspace(u,p):
                log(folder,"로그인 인증이 필요합니다. 예약 실행에서는 별도 인증을 처리하지 않습니다.")
                return 1
            rows,diagnostic=b.scrape(days,folder,threading.Event(),workbook_path=cfg.get('workbook_path'))
            log(folder,f"완료: 가격 {len(rows)}행 / 종목 {len(diagnostic['price_symbols'])} / 경고 {len(diagnostic['warnings'])}")
            return 2 if diagnostic["warnings"] else 0
    except Exception as e:
        log(folder,"실패: "+str(e))
        return 1
    finally:b.detach()


def inspect_excel_target(folder: Path, workbook_path=''):
    """No-write check for corporate Excel file, path, and container signature."""
    import zipfile
    target=Path(workbook_path or path_bundle(folder)['xlsx']).expanduser()
    print(f'\n[Excel 읽기 전 검증] 경로={target}',flush=True)
    print(f'경로 유형: 기존파일={target.exists()}  폴더 존재={target.parent.exists()}',flush=True)
    if target.exists():
        print(f'크기: {target.stat().st_size:,} bytes',flush=True)
        print(f'일반 XLSX ZIP 형식: {zipfile.is_zipfile(target)} (False이면 DRM·손상·비표준형식 등 확인 필요)',flush=True)
        print(f'읽기 권한(OS): {os.access(target,os.R_OK)}',flush=True)
    print('대상 파일이 없으면 동일 경로에 신규 누적 Excel을 생성합니다.' if not target.exists() else '기존 파일은 동일 경로에서 안전하게 갱신합니다.',flush=True)
    print('이 명령은 Excel을 실행하지 않고, 파일을 변경하지 않습니다.',flush=True)

def inspect_stored_data(folder: Path):
    """Read-only SQL verification (does not expose any account credentials)."""
    p=path_bundle(folder)['db']
    if not p.exists():raise FileNotFoundError(f'SQLite DB 경로에 파일이 없습니다: {p}')
    with closing(sqlite3.connect(p)) as cx:
        fmb=cx.execute('SELECT count(*) FROM prices').fetchone()[0]
        fx=cx.execute("SELECT count(*) FROM fx_rates").fetchone()[0] if cx.execute("SELECT name FROM sqlite_master WHERE name='fx_rates'").fetchone() else 0
        print(f'\n[DB 검증] {p}\nFMB: {fmb}행, SMBS: {fx}행',flush=True)
        if fx:
            for code,day,unit,rate,diff in cx.execute('SELECT currency,quote_date,quote_unit,rate,difference FROM fx_rates '
                'WHERE (currency,quote_date) IN (SELECT currency,max(quote_date) FROM fx_rates GROUP BY currency) ORDER BY currency'):
                print(f'SMBS {code} {day}: {rate} KRW/{unit}{code} (전일대비 {diff})',flush=True)
            q=cx.execute("SELECT rate,difference FROM fx_rates WHERE currency='USD' AND quote_date='2026-09-28'").fetchone()
            print('USD 2026-09-28 확인:',q, '정상 예시=(1352.00, -8.00)',flush=True)

def main():
    parser=argparse.ArgumentParser(description=APP)
    parser.add_argument("--once",action="store_true",help="예약 또는 명령행에서 한 번 수집")
    parser.add_argument("--days",type=int,help="0: 전체, 1~3650: 최근 N일")
    parser.add_argument("--fx-once",action="store_true",help="SMBS 4개 통화 수집 및 같은 누적 Excel 갱신")
    parser.add_argument("--export-only",action="store_true",help="사이트 재수집 없이 DB에서 CSV 및 누적 Excel 재생성")
    parser.add_argument("--verify-db",action="store_true",help="읽기 전용: 저장된 FMB·환율 실제 수치 확인")
    parser.add_argument("--probe-excel",action="store_true",help="읽기 전용: Excel 경로, 크기, DRM 가능성 점검")
    parser.add_argument("--export-fresh",action="store_true",help="기존 DRM 원본을 열지 않고 날짜별 새 Excel 파일로 별도 출력")
    parser.add_argument("--with-fx",action="store_true",help="--once 완료 후 SMBS 환율 수집을 독립 수행")
    parser.add_argument("--fx-start",help="요청 고시기간 시작일: YYYY.MM.DD (조회 DOM 확인 후만 사용)")
    parser.add_argument("--fx-end",help="요청 고시기간 종료일: YYYY.MM.DD (조회 DOM 확인 후만 사용)")
    args=parser.parse_args()
    if args.days is not None and not 0<=args.days<=3650:parser.error('--days는 0~3650입니다.')
    if bool(args.fx_start)!=bool(args.fx_end):parser.error('--fx-start와 --fx-end는 반드시 함께 사용하세요.')
    if args.verify_db:
        inspect_stored_data(Path(config_load()['data_dir']))
        return
    if args.probe_excel:
        cfg=config_load()
        inspect_excel_target(Path(cfg['data_dir']),cfg.get('workbook_path'))
        return
    if args.export_fresh:
        cfg=config_load();folder=Path(cfg['data_dir']);stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
        fresh=folder/f'fastmarkets_prices_fresh_{stamp}.xlsx'
        original=Path(cfg.get('workbook_path') or path_bundle(folder)['xlsx'])
        protected=original.exists() and not __import__('zipfile').is_zipfile(original)
        print('기존 Excel 파일은 열거나 수정하지 않습니다. 별도 새 파일:',fresh,flush=True)
        generated=Path(export_workbook(folder,output_path=str(fresh)))
        if protected and __import__('zipfile').is_zipfile(generated):
            # A corporate DRM-protected original must never be silently exported
            # into an unprotected XLSX. This safety check applies to explicit exports too.
            generated.unlink(missing_ok=True)
            raise RuntimeError('원본은 보안/비표준 Excel인데 신규 파일이 일반 XLSX였습니다. 회사 보안 정책 보호를 위해 새 파일을 삭제했습니다.')
        print('새 Excel 결과:',generated,flush=True)
        return
    if args.export_only:
        cfg=config_load()
        if args.once or args.fx_once or args.with_fx:
            parser.error('--export-only는 수집 명령과 함께 사용할 수 없습니다.')
        try:
            print('내보내기 완료: '+export_all(Path(cfg['data_dir']),cfg.get('workbook_path')))
            sys.exit(0)
        except Exception as exc:
            print(f'DB 보존 / Excel 재갱신 필요: {type(exc).__name__}: {exc}', file=sys.stderr)
            sys.exit(2)
    if args.fx_once:
        cfg=config_load()
        try:
            b=ChromeSession(lambda m:log(Path(cfg['data_dir']),m))
            try:
                with exclusive_browser_job():
                    b.connect()
                    report=fx_one_time(Path(cfg['data_dir']),cfg.get('workbook_path'),start=args.fx_start,end=args.fx_end,driver=b.driver)
            finally:b.detach()
            print(json.dumps(report,ensure_ascii=False,indent=2))
            sys.exit(2 if report.get('warnings') else 0)
        except Exception as exc:
            print(f'SMBS 수집 실패: {type(exc).__name__}: {exc}',file=sys.stderr)
            sys.exit(1)
    if args.once:
        if not args.with_fx:sys.exit(one_time(args.days))
        cfg=config_load();folder=Path(cfg['data_dir']);b=ChromeSession(lambda m:log(folder,m))
        result=0
        try:
            with exclusive_browser_job():
                u,p=credentials_get()
                if not b.open_workspace(u,p):
                    log(folder,'FMB 로그인 필요. 기존 브라우저/DB 보존')
                    result=2
                else:
                    try:
                        rows,diag=b.scrape(args.days if args.days is not None else int(cfg['lookback_days']),
                                          folder,threading.Event(),workbook_path=cfg.get('workbook_path'),defer_export=True)
                        log(folder,f'FMB {len(rows)}행 수집 완료 / 경고 {len(diag.get("warnings",[]))}건')
                        if diag.get('warnings'):result=2
                    except Exception as exc:
                        result=2;log(folder,'FMB 수집 실패: '+type(exc).__name__+': '+str(exc))
                try:
                    fx=fx_one_time(folder,cfg.get('workbook_path'),driver=b.connect(),defer_export=True)
                    log(folder,f'SMBS {fx.get("collected",0)}건 수집 완료')
                    if fx.get('warnings'):result=2
                except Exception as exc:
                    log(folder,'SMBS 실패: '+type(exc).__name__+': '+str(exc));result=2
                try:
                    export_all(folder,cfg.get('workbook_path'))
                except Exception as exc:
                    log(folder,'Excel 내보내기 실패(기존 DB 보존): '+str(exc));result=2
        except Exception as exc:
            log(folder,'통합 수집 중단: '+type(exc).__name__+': '+str(exc));result=1
        finally:b.detach()
        sys.exit(result)
    main_gui()


if __name__=="__main__":
    main()
