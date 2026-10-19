"""One read transaction, one immutable numerical snapshot, all output formats."""
from __future__ import annotations
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from collections import defaultdict
import json
import sqlite3
import math

REPORT_NAMES=('보고용_금속시세','보고용_환율','보고용_시장지표','증시_시총스냅샷','보고용_시총','보고용_종합')

def _freeze_tables(tables):
    return MappingProxyType({k:tuple(tuple(row) for row in rows) for k,rows in tables.items()})

def _number(value):
    if value is None or value=='':return None
    try:
        number=Decimal(str(value))
        result=float(number) if number.is_finite() else None
        return result if result is not None and math.isfinite(result) else None
    except (InvalidOperation,ValueError):return None

def excel_safe(value):
    if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):
        return "'"+value
    return value

@dataclass(frozen=True)
class ReportContext:
    snapshot_id: str
    as_of: str
    label: str
    tables: object
    source_dates: object
    warnings: tuple
    workspace_id: str
    start: str | None
    end: str
    _sheets: object

    def to_dict(self):
        return dict(snapshot_id=self.snapshot_id,as_of=self.as_of,label=self.label,
                    workspace_id=self.workspace_id,start=self.start,end=self.end,
                    source_dates=dict(self.source_dates),warnings=list(self.warnings),
                    tables={k:[list(r) for r in rows] for k,rows in self.tables.items()},
                    workbook_sheets={k:[list(r) for r in rows] for k,rows in self._sheets.items()})

def canonical_json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)

def _data_as_of(observations):
    """Latest reliable stored capture, never the wall-clock export time.

    SQLite CURRENT_TIMESTAMP (FMB) is UTC. Other naive timestamps have no
    trustworthy zone and are deliberately not assigned an invented timezone.
    """
    candidates=[]
    for value,sqlite_utc in observations:
        if not isinstance(value,str) or ('T' not in value and ' ' not in value):continue
        try:stamp=datetime.fromisoformat(value)
        except ValueError:continue
        if stamp.tzinfo is None:
            if not sqlite_utc:continue
            stamp=stamp.replace(tzinfo=timezone.utc)
        candidates.append(stamp)
    return max(candidates).isoformat() if candidates else ''

def build_context(folder,start=None,end=None,series=None,*,synthetic=False,workspace_id=None):
    import FastmarketsCollector_v3_4 as core
    from smbs_rates import FXQuote,prepare_excel_series
    from excel_secure import make_sheets
    folder=Path(folder)
    kst_today=datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    end=end or kst_today
    date.fromisoformat(end)
    if start:date.fromisoformat(start)
    if start and start>end:raise ValueError('시작일은 종료일보다 늦을 수 없습니다')
    naver_cutoff=min(end,kst_today)
    active=workspace_id or core.current_workspace()[1]
    selected=set(series) if series is not None else None
    if isinstance(series,str):selected={series}
    def chosen(code,key=None):return selected is None or code in selected or key in selected
    warnings=[];raw={name:[] for name in ('prices','fx_rates','market_indicators','equity_rank_snapshots')}
    db=core.path_bundle(folder)['db']
    if db.exists():
        with closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)) as cx:
            cx.row_factory=sqlite3.Row
            cx.execute('BEGIN')
            existing={r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in raw:
                if table in existing:
                    raw[table]=[dict(row) for row in cx.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                else:warnings.append(table+': 저장 자료 없음')
            cx.rollback()
    else:warnings.append('SQLite 저장 자료 없음')
    def dated(row,key):
        value=row.get(key) or ''
        try:date.fromisoformat(value)
        except ValueError:return False
        return (not start or value>=start) and value<=end
    prices=[];other=[];provenance=[];observations=[]
    for r in raw['prices']:
        key=f"FMB|{r['symbol']}|{r['unit']}|{r['price_mode']}|MID"
        if not dated(r,'assessment_date') or not chosen(r['symbol'],key):continue
        provenance.append(tuple(r.get(k) for k in ('workspace_id','symbol','assessment_date','low','mid','high','unit','price_mode','view_key','source','collected_at')))
        if r['workspace_id']!=active:other.append(r);continue
        observations.append((r.get('collected_at'),True))
        prices.append(core.Price(r['symbol'],r['assessment_date'],r['low'],r['mid'],r['high'],r['change_pct'],r['unit'],r['description'],r['widget'],r['price_mode'],r['source'],r['view_key'],r['period_label']))
    if other:warnings.append(f'다른 워크스페이스 {len(other)}행: 원본 보존, 현재 보고 수치에서는 제외')
    quotes=[]
    for r in raw['fx_rates']:
        key=f"FX_{r['currency']}_KRW_per_{r['quote_unit']}"
        if dated(r,'quote_date') and chosen(r['currency'],key):
            if _number(r['rate']) is not None and _number(r['difference']) is not None:
                quotes.append(FXQuote(r['quote_date'],r['currency'],r['rate'],r['difference'],r['quote_unit'],r['source']))
                observations.append((r.get('collected_at'),False))
            else:warnings.append(key+': 유효하지 않은 환율 제외')
    from naver_close import is_verified_close
    indicators=[];equities=[];naver_selected={'market_indicators':[],'equity_rank_snapshots':[]}
    for table,code,dest in (('market_indicators','instrument_id',indicators),('equity_rank_snapshots','stock_code',equities)):
        for r in raw[table]:
            key=f"NAVER|{r[code]}|{r.get('unit','')}|Actual|MID"
            if not dated(r,'market_date') or not chosen(r[code],key):continue
            naver_selected[table].append(r)
            if not is_verified_close(r) or r['market_date']>=naver_cutoff:
                warnings.append(f"NAVER {r[code]} {r['market_date']}: 당일·장중·미검증 수치 제외 (기준일 {naver_cutoff} 이전 확정 종가만 사용)");continue
            dest.append(r)
            observations.append((r.get('captured_at'),False))
    prices.sort(key=lambda p:(p.date,p.symbol,p.view_key),reverse=True)
    records=prepare_excel_series(prices,quotes,issues=warnings)
    sheets=make_sheets(prices,core.latest_quotes(prices,today=date.fromisoformat(end)),quotes)
    sheets['워크스페이스원본']=[('workspace_id','symbol','assessment_date','low','mid','high','unit','price_mode','view_key','source','collected_at')]+provenance
    # Raw NAVER observations retain each actual market date; stock ranks never join daily columns.
    naver_keys=sorted({f"NAVER|{r['instrument_id']}|{r['unit']}|Actual|MID" for r in indicators})
    naver_daily=defaultdict(dict)
    for r in indicators:
        key=f"NAVER|{r['instrument_id']}|{r['unit']}|Actual|MID"
        if _number(r['value']) is not None:naver_daily[r['market_date']][key]=_number(r['value'])
    if naver_keys:
        labels={k:f"{k.split('|')[1]} ({k.split('|')[2]})" for k in naver_keys}
        sheets['가격열설정'] += [(k,labels[k],'NAVER / '+k.split('|')[2]) for k in naver_keys]
        old=sheets['일별시세']; merged={r[0]:list(r[1:]) for r in old[2:]}
        all_dates=sorted(set(merged)|set(naver_daily))
        headers=[tuple(old[0])+tuple(labels[k] for k in naver_keys),tuple(old[1])+tuple('NAVER' for k in naver_keys)]
        sheets['일별시세']=headers+[tuple([dt]+merged.get(dt,[None]*(len(old[0])-1))+[naver_daily[dt].get(k) for k in naver_keys]) for dt in all_dates]
        sheets['일별요약']=list(sheets['일별시세'])
        acc=defaultdict(lambda:defaultdict(list))
        for row in sheets['일별시세'][2:]:
            for i,v in enumerate(row[1:]):
                if isinstance(v,(int,float)):acc[row[0][:7]][i].append(v)
        for name,count in (('월별시세',False),('월별건수',True)):
            sheets[name]=[('기준월',)+sheets['일별시세'][0][1:],sheets['일별시세'][1]]+[
                tuple([month]+[(len(acc[month][i]) if count else sum(acc[month][i])/len(acc[month][i])) if acc[month][i] else (0 if count else None) for i in range(len(sheets['일별시세'][0])-1)]) for month in sorted(acc)]
    def latest(rows,key):
        result={}
        for r in sorted(rows,key=lambda r:(r['market_date'],r['captured_at'])):result[r[key]]=r
        return list(result.values())
    metals=[('종목','고시일','Mid','단위','구분','출처')]
    identities={}
    for p in prices:
        if p.price_mode not in {'Actual','Forecast','Unspecified'} or p.period_label:continue
        key=f'FMB|{p.symbol}|{p.unit}|{p.price_mode}|MID'
        identities.setdefault(key,p)
    for key,p in sorted(identities.items()):
        metals.append((p.symbol,p.date,records.get(p.date,{}).get(key),p.unit,p.price_mode,p.source))
    fx=[('통화','고시일','매매기준율','전일대비','단위','출처')]
    latest_fx={}
    for q in sorted(quotes,key=lambda q:q.quote_date):
        identity=(q.currency,q.unit)
        prior=latest_fx.get(identity,[])
        if not prior or prior[0].quote_date<q.quote_date:latest_fx[identity]=[q]
        else:prior.append(q)
    for (currency,unit),samples in sorted(latest_fx.items()):
        dt=samples[0].quote_date
        rate=records.get(dt,{}).get(f'FX_{currency}_KRW_per_{unit}')
        difference=records.get(dt,{}).get(f'FX_{currency}_DIFF_KRW_per_{unit}')
        fx.append((currency,dt,rate,difference,f'KRW/{unit} {currency}',' / '.join(sorted({q.source for q in samples}))))
    from naver_close import select_closes
    from naver_markets import INDICATORS
    present={r['instrument_id'] for r in indicators}
    expected=[code for code in INDICATORS if selected is None or code in selected or any(str(key).startswith('NAVER|'+code+'|') for key in selected)]
    selector_rows=list(indicators)+[{'instrument_id':code,'status':'unverified'} for code in expected if code not in present]
    close_pairs=select_closes(selector_rows,naver_cutoff+'T00:00:00+09:00')
    warnings.extend(close_pairs['warnings'])
    market=[('지표','시장일','수치','비교일','비교종가','전일대비','등락률(%)','단위','상태','출처')]
    indicator_order={code:i for i,code in enumerate(INDICATORS)}
    for r in sorted(close_pairs['rows'],key=lambda item:(indicator_order.get(item['instrument_id'],len(INDICATORS)),item['instrument_id'])):
        pct=_number(r.get('pct'))
        source=' / '.join(dict.fromkeys(v for v in (r.get('previous_source_url'),r.get('prior_source_url'),r.get('source_url')) if v))
        market.append((r['instrument_id'],r.get('previous_date'),_number(r.get('previous_close')),r.get('prior_date'),_number(r.get('prior_close')),_number(r.get('change')),round(pct,6) if pct is not None else None,r.get('unit'),r['status'],source))
    cap=[('순위','종목명','코드','시장일','시가총액','단위','상태','출처')]
    # Only one actual ranking date; don't manufacture a mixed-date Top 10.
    cap_date=max((r['market_date'] for r in equities if r['rank'] is not None),default=None)
    cap_rows=[r for r in equities if r['rank'] is not None and r['market_date']==cap_date]
    # POSCO is an explicit additional instrument, never a fabricated Top-10 rank.
    if not any(r['stock_code']=='005490' for r in cap_rows):
        extra=latest([r for r in equities if r['stock_code']=='005490' and r['rank'] is None],'stock_code')
        cap_rows.extend(extra)
    raw_cap=[cap[0]]
    for r in sorted(cap_rows,key=lambda r:(r['rank'] or 999,r['stock_code'])):
        try:detail=json.loads(r.get('raw_json') or '{}')
        except (ValueError,TypeError):detail={}
        cap_unit=detail.get('market_cap_unit') or detail.get('attrs',{}).get('data-market-cap-unit')
        value=_number(r['market_cap'])
        raw_cap.append((r['rank'],r['name'],r['stock_code'],r['market_date'],value,cap_unit or '미확인',r['status'],r['source_url']))
        if not cap_unit:
            warnings.append(r['stock_code']+': 시총 단위 미확인, 보고 수치 반영 보류')
            value=None
        cap.append((r['rank'],r['name'],r['stock_code'],r['market_date'],value,cap_unit or '미확인',r['status'],r['source_url']))
    tables=dict(zip(REPORT_NAMES,(metals,fx,market,raw_cap,cap,[('구분','종목','시장·고시일','수치','단위','상태','출처')])))
    for table,name in (('market_indicators','NAVER_지표원본'),('equity_rank_snapshots','NAVER_시총원본')):
        selected_raw=naver_selected[table]
        if selected_raw:
            raw_cols=tuple(sorted(selected_raw[0]))
            sheets[name]=[raw_cols]+[tuple(r.get(k) for k in raw_cols) for r in selected_raw]
    for row in metals[1:]:tables['보고용_종합'].append(('금속',row[0],row[1],row[2],row[3],row[4],row[5]))
    for row in fx[1:]:tables['보고용_종합'].append(('환율',row[0],row[1],row[2],row[4],'고시',row[5]))
    for row in market[1:]:tables['보고용_종합'].append(('시장지표',row[0],row[1],row[2],row[7],row[8],row[9]))
    for row in cap[1:]:tables['보고용_종합'].append(('시총',row[2],row[3],row[4],row[5],row[6],row[7]))
    sheets.update(tables)
    source_dates={'FMB':tuple(sorted({p.date for p in prices})), 'SMBS':tuple(sorted({q.quote_date for q in quotes})), 'NAVER 지표':tuple(sorted({r['market_date'] for r in indicators})), 'NAVER 시총':tuple(sorted({r['market_date'] for r in equities}))}
    context=ReportContext('',_data_as_of(observations), 'TEST / 합성 데이터' if synthetic else '시장 수치 보고서',_freeze_tables(tables),MappingProxyType(source_dates),tuple(dict.fromkeys(warnings)),active,start,end,_freeze_tables(sheets))
    from dataclasses import replace
    payload=context.to_dict();payload.pop('snapshot_id')
    return replace(context,snapshot_id=sha256(canonical_json(payload).encode()).hexdigest())

def make_workbook_sheets(context):
    """Fresh mutable cells; never re-query the DB or alter the frozen snapshot."""
    sheets={k:[tuple(excel_safe(c) for c in r) for r in rows] for k,rows in context._sheets.items()}
    sheets['보고서_메타']=[('항목','값'),('Snapshot SHA-256',context.snapshot_id),('자료 기준 시각',context.as_of or '미확인'),('라벨',context.label),('워크스페이스',context.workspace_id),('시작일',context.start),('종료일',context.end)]+[(source+' 시장·고시일',', '.join(dates) or '미고시') for source,dates in context.source_dates.items()]+[('자료 주의사항',excel_safe(w)) for w in context.warnings]
    return sheets
