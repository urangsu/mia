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

REPORT_NAMES=('보고용_금속시세','보고용_환율','보고용_시장지표','증시_시총스냅샷','보고용_시총','보고용_종합','보고용_주가')

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

def build_context(folder,start=None,end=None,series=None,*,synthetic=False,workspace_id=None,captured_at=None):
    import FastmarketsCollector_v3_4 as core
    from smbs_rates import FXQuote,prepare_excel_series
    from excel_secure import make_sheets
    folder=Path(folder)
    capture=datetime.fromisoformat(captured_at) if captured_at else datetime.now(timezone(timedelta(hours=9)))
    if capture.tzinfo is None:raise ValueError('보고 기준 시각에 시간대가 필요합니다.')
    kst_today=capture.astimezone(timezone(timedelta(hours=9))).date().isoformat()
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
    withdrawn_identities=set()
    if db.exists():
        with closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)) as cx:
            cx.row_factory=sqlite3.Row
            cx.execute('BEGIN')
            existing={r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in raw:
                if table in existing:
                    raw[table]=[dict(row) for row in cx.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                else:warnings.append(table+': 저장 자료 없음')
            for table in ('fdr_observations','fdr_targets','fdr_quarantine','naver_raw_captures','lme_official_prices','smm_observations'):
                raw[table]=[dict(row) for row in cx.execute('SELECT * FROM '+table+' ORDER BY rowid')] if table in existing else []
            if 'price_revisions' in existing:
                for r in cx.execute('''SELECT symbol,assessment_date,unit,price_mode,view_key FROM price_revisions
                    WHERE workspace_id=? AND json_extract(old_values,'$[1]') IS NOT NULL
                    AND json_extract(new_values,'$[1]') IS NULL''',(active,)):
                    withdrawn_identities.add(tuple(r))
            cx.rollback()
    else:warnings.append('SQLite 저장 자료 없음')
    def dated(row,key):
        value=row.get(key) or ''
        try:date.fromisoformat(value)
        except ValueError:return False
        return (not start or value>=start) and value<=end
    captures=[]
    for r in raw.get('naver_raw_captures',[]):
        code=r.get('entity_key')
        if not chosen(code) and not any(str(key).startswith('NAVER|'+str(code)+'|') for key in selected):continue
        day=str(r.get('captured_at') or '')[:10]
        if (not start or day>=start) and day<=end:captures.append(r)
    prices=[];other=[];provenance=[];observations=[];withdrawn=set()
    for r in raw['prices']:
        key=f"FMB|{r['symbol']}|{r['unit']}|{r['price_mode']}|MID"
        if not dated(r,'assessment_date') or not chosen(r['symbol'],key):continue
        provenance.append(tuple(r.get(k) for k in ('workspace_id','symbol','assessment_date','low','mid','high','unit','price_mode','view_key','source','collected_at')))
        if r['workspace_id']!=active:other.append(r);continue
        identity=tuple(r[k] for k in ('symbol','assessment_date','unit','price_mode','view_key'))
        if r['mid'] is None and identity in withdrawn_identities:
            withdrawn.add((r['assessment_date'],key))
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
    pair_capture=capture if naver_cutoff==kst_today else datetime.fromisoformat(naver_cutoff+'T08:30:00+09:00')
    def checked_daily_pair(pair, source_rows):
        code=pair.get('instrument_id') or pair.get('stock_code')
        date_set={pair.get('previous_date'),pair.get('prior_date')}
        evidence=[]
        for observation in source_rows:
            if (observation.get('instrument_id') or observation.get('stock_code'))!=code or observation.get('market_date') not in date_set:continue
            try:detail=json.loads(observation.get('raw_json') or '{}')
            except (ValueError,TypeError):continue
            if detail.get('table_source'):evidence.append(observation['market_date'])
        if len(set(evidence))<2:return pair
        from naver_freshness import check_pair
        checked,issues=check_pair(pair,pair_capture)
        warnings.extend(issues)
        return checked
    public=dict(indicators=[],pairs={},stocks=[],warnings=[],withdrawn=[],quarantine=[],calendar_errors={})
    fallback_codes=set();naver_primary_codes=set()
    if raw.get('fdr_targets'):
        from fdr_reporting import prepare
        # Historical reports retain the same morning convention; today's report
        # uses the actual capture instant, never an assumed market close.
        public_capture=pair_capture
        public=prepare(raw.get('fdr_observations',[]),raw['fdr_targets'],public_capture,start=start,end=naver_cutoff,series=selected,quarantine=raw.get('fdr_quarantine',[]))
        from naver_close import select_closes
        naver_primary_codes={r['instrument_id'] for r in select_closes(indicators,naver_cutoff+'T00:00:00+09:00')['rows'] if r['status']=='close_pair'}
        failed_codes={t['instrument_id'] for t in raw['fdr_targets'] if t.get('status')=='failed'}|set(public['calendar_errors'])
        fallback_codes={code for code in failed_codes if code in public['pairs'] and public['pairs'][code]['status']!='close_pair'}
        retained=[r for r in indicators if r['instrument_id'] not in public['pairs'] or r['instrument_id'] in fallback_codes or r['instrument_id'] in naver_primary_codes]
        retained_codes={r['instrument_id'] for r in retained}
        indicators=retained+[r for r in public['indicators'] if r['instrument_id'] not in retained_codes]
        warnings.extend(public['warnings'])
        observations.extend((r.get('captured_at'),False) for r in public['observations'])
    prices.sort(key=lambda p:(p.date,p.symbol,p.view_key),reverse=True)
    if withdrawn:
        warnings.append(f'가격 정정으로 기존 Mid {len(withdrawn)}개 철회: 누적 Excel/ECM 기존 수치를 비움 대상으로 표시')
    records=prepare_excel_series(prices,quotes,issues=warnings,withdrawn=withdrawn)
    sheets=make_sheets(prices,core.latest_quotes(prices,today=date.fromisoformat(end)),quotes,withdrawn=withdrawn)
    sheets['워크스페이스원본']=[('workspace_id','symbol','assessment_date','low','mid','high','unit','price_mode','view_key','source','collected_at')]+provenance
    # Official LME prices have their own identity, not an FMB Mid or synthetic
    # average. Operating columns are Cash Ask and 3-month Ask; Bid stays raw.
    import lme_official as lme
    lme_rows=[]
    for row in raw.get('lme_official_prices',[]):
        key=f"LME|{row['instrument_id']}|USD/t|Official|{row['side'].upper()}"
        if not dated(row,'market_date') or not chosen(row['instrument_id'],key):continue
        expected_id='LME_'+lme.METALS.get(row['metal'],'?')+'_'+lme.CONTRACTS.get(row['contract'],'?')+'_'+row['side'].upper()
        value=_number(row['value'])
        if (row['instrument_id']!=expected_id or row['side'] not in ('Bid','Ask') or row['unit']!='USD/t'
                or row['currency']!='USD' or row['price_type']!='Official' or not lme._source_ok(row['source_url'])
                or value is None or value<=0 or bool(row['is_settlement'])!=(row['contract']=='Cash' and row['side']=='Ask')):
            warnings.append('LME '+str(row.get('instrument_id'))+': invalid stored source identity excluded');continue
        lme_rows.append(row);observations.append((row['captured_at'],False))
    if lme_rows:
        sheets['LME_공식원본']=[lme.COLUMNS]+[tuple(r.get(c) for c in lme.COLUMNS) for r in lme_rows]
        ask_rows=[r for r in lme_rows if r['side']=='Ask']
        lme_keys=sorted({f"LME|{r['instrument_id']}|USD/t|Official|ASK" for r in ask_rows})
        metal_names={'Nickel':'니켈','Copper':'구리','Cobalt':'코발트'}
        descriptions={f"LME|{r['instrument_id']}|USD/t|Official|ASK":
                      metal_names[r['metal']]+' LME '+r['contract']+' Ask (USD/t)' for r in ask_rows}
        sheets['가격열설정'] += [(key,descriptions[key],'LME Official · 계약/Ask 별도, Cash Ask=Settlement') for key in lme_keys]
        old=sheets['일별시세'];existing_days={r[0]:list(r[1:]) for r in old[2:]};lme_daily=defaultdict(dict)
        for r in ask_rows:lme_daily[r['market_date']][f"LME|{r['instrument_id']}|USD/t|Official|ASK"]=_number(r['value'])
        sheets['일별시세']=[tuple(old[0])+tuple(descriptions[key] for key in lme_keys),tuple(old[1])+tuple('LME' for _ in lme_keys)]+[
            tuple([day]+existing_days.get(day,[None]*(len(old[0])-1))+[lme_daily[day].get(key) for key in lme_keys])
            for day in sorted(set(existing_days)|set(lme_daily))]
        sheets['일별요약']=list(sheets['일별시세'])
        monthly=defaultdict(lambda:defaultdict(list))
        for row in sheets['일별시세'][2:]:
            for i,value in enumerate(row[1:]):
                if isinstance(value,(int,float)):monthly[row[0][:7]][i].append(value)
        for name,count in (('월별시세',False),('월별건수',True)):
            sheets[name]=[('기준월',)+sheets['일별시세'][0][1:],sheets['일별시세'][1]]+[
                tuple([month]+[(len(monthly[month][i]) if count else sum(monthly[month][i])/len(monthly[month][i]))
                    if monthly[month][i] else (0 if count else None) for i in range(len(sheets['일별시세'][0])-1)]) for month in sorted(monthly)]
    # Raw NAVER observations retain each actual market date; stock ranks never join daily columns.
    def indicator_key(r):
        source='FDR' if r.get('provider')=='FinanceDataReader' else 'NAVER'
        return f"{source}|{r['instrument_id']}|{r['unit']}|Actual|MID"
    naver_keys=sorted({indicator_key(r) for r in indicators}|{k for _,k in public['withdrawn']})
    naver_daily=defaultdict(dict)
    for r in indicators:
        key=indicator_key(r)
        if _number(r['value']) is not None:naver_daily[r['market_date']][key]=_number(r['value'])
    for day,key in public['withdrawn']:
        naver_daily[day][key]=None
        for tab in ('일별시세','일별요약'):
            sheets['보류셀'].append((tab,day,key,'FDR 同日 Close 충돌: 기존 수치 철회'))
    if naver_keys:
        labels={k:f"{k.split('|')[1]} ({k.split('|')[2]})" for k in naver_keys}
        sheets['가격열설정'] += [(k,labels[k],k.split('|')[0]+' / '+k.split('|')[2]) for k in naver_keys]
        old=sheets['일별시세']; merged={r[0]:list(r[1:]) for r in old[2:]}
        all_dates=sorted(set(merged)|set(naver_daily))
        headers=[tuple(old[0])+tuple(labels[k] for k in naver_keys),tuple(old[1])+tuple(k.split('|')[0] for k in naver_keys)]
        sheets['일별시세']=headers+[tuple([dt]+merged.get(dt,[None]*(len(old[0])-1))+[naver_daily[dt].get(k) for k in naver_keys]) for dt in all_dates]
        sheets['일별요약']=list(sheets['일별시세'])
        acc=defaultdict(lambda:defaultdict(list))
        for row in sheets['일별시세'][2:]:
            for i,v in enumerate(row[1:]):
                if isinstance(v,(int,float)):acc[row[0][:7]][i].append(v)
        for name,count in (('월별시세',False),('월별건수',True)):
            sheets[name]=[('기준월',)+sheets['일별시세'][0][1:],sheets['일별시세'][1]]+[
                tuple([month]+[(len(acc[month][i]) if count else sum(acc[month][i])/len(acc[month][i])) if acc[month][i] else (0 if count else None) for i in range(len(sheets['일별시세'][0])-1)])
                for month in sorted({row[0][:7] for row in sheets['일별시세'][2:]})]
        for day,key in public['withdrawn']:
            if not acc[day[:7]][len(old[0])-1+naver_keys.index(key)]:
                sheets['보류셀'].append(('월별시세',day[:7],key,'FDR 충돌 후 검증된 월별 표본 없음'))
    def latest(rows,key):
        result={}
        for r in sorted(rows,key=lambda r:(r['market_date'],r['captured_at'])):result[r[key]]=r
        return list(result.values())
    from series_mapping import product_info
    metals=[('품목명','고시일','Mid','단위','구분','출처','코드','그룹','원본 조건')]
    identities={}
    for p in prices:
        if p.price_mode not in {'Actual','Forecast','Unspecified'} or p.period_label:continue
        key=f'FMB|{p.symbol}|{p.unit}|{p.price_mode}|MID'
        identities.setdefault(key,p)
    for key,p in sorted(identities.items()):
        product=product_info(p.symbol,p.description,p.unit,p.price_mode)
        metals.append((product['name'],p.date,records.get(p.date,{}).get(key),p.unit,p.price_mode,p.source,p.symbol,product['group'],product['conditions']))
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
    expected=[code for code in INDICATORS if selected is None or code in selected or any(str(key).startswith(('NAVER|'+code+'|','FDR|'+code+'|')) for key in selected)]
    selector_rows=list(indicators)+[{'instrument_id':code,'status':'unverified'} for code in expected if code not in present]
    close_pairs=select_closes(selector_rows,naver_cutoff+'T00:00:00+09:00')
    resolved=[]
    for r in close_pairs['rows']:
        code=r['instrument_id']
        if code in fallback_codes and r['status']=='close_pair':
            r=dict(r,status='close_pair_naver_fallback')
            warnings.append(f'NAVER {code}: fallback; FDR 조회/캘린더 실패로 저장된 검증 종가 사용 ({r["previous_date"]}, {r["prior_date"]}), 최신 기대 거래일 보장 아님')
        elif code in naver_primary_codes and r['status']=='close_pair':
            r=dict(r,status='close_pair_naver')
        else:r=public['pairs'].get(code,r)
        # Legacy fixtures retain their contract; source-bound daily tables add
        # explicit session freshness without changing observed prices/dates.
        if code not in public['pairs'] or code in naver_primary_codes or code in fallback_codes:
            previous_status=r['status']
            probe=dict(r,status='close_pair') if previous_status.startswith('close_pair') else r
            checked=checked_daily_pair(probe,indicators)
            r=checked if checked['status']!='close_pair' else r
        resolved.append(r)
    close_pairs['rows']=resolved
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
    # Capture visibility is independent from admission to confirmed reporting.
    raw_cap=[cap[0]+('수집시각','종가검증')]
    raw_equities=list(naver_selected['equity_rank_snapshots'])
    latest_captures={}
    for capture_row in sorted(captures,key=lambda r:(r.get('captured_at') or '',r.get('id') or 0)):
        if capture_row.get('entity')!='equities':continue
        try:payload=json.loads(capture_row.get('raw_json') or '{}')
        except (ValueError,TypeError):continue
        if not isinstance(payload,dict) or not payload.get('stock_code'):continue
        # Audit captures are never upgraded to a confirmed observation here.
        payload.update(status='unverified',close_verified=False,captured_at=capture_row.get('captured_at'))
        latest_captures[payload['stock_code']]=payload
    raw_equities.extend(latest_captures.values())
    for r in sorted(raw_equities,key=lambda r:(r.get('market_date') or '',r.get('rank') or 999,r['stock_code'])):
        try:detail=json.loads(r.get('raw_json') or '{}')
        except (ValueError,TypeError):detail={}
        if not isinstance(detail,dict):detail={}
        attrs=detail.get('attrs') if isinstance(detail.get('attrs'),dict) else {}
        cap_unit=detail.get('market_cap_unit') or attrs.get('data-market-cap-unit')
        raw_cap.append((r.get('rank'),r.get('name'),r['stock_code'],r.get('market_date'),_number(r.get('market_cap')),cap_unit or '미확인',r['status'],r.get('source_url'),r.get('captured_at'),'검증됨' if is_verified_close(r) else '미확정'))
    for r in sorted(cap_rows,key=lambda r:(r['rank'] or 999,r['stock_code'])):
        try:detail=json.loads(r.get('raw_json') or '{}')
        except (ValueError,TypeError):detail={}
        cap_unit=detail.get('market_cap_unit') or detail.get('attrs',{}).get('data-market-cap-unit')
        value=_number(r['market_cap'])
        if not cap_unit:
            warnings.append(r['stock_code']+': 시총 단위 미확인, 보고 수치 반영 보류')
            value=None
        cap.append((r['rank'],r['name'],r['stock_code'],r['market_date'],value,cap_unit or '미확인',r['status'],r['source_url']))
    if not any(row[4] is not None and row[5]!='미확인' for row in cap[1:]) and captures:
        from cap_snapshot_compare import compare_captures
        comparison=compare_captures(captures)
        warnings.extend(comparison['warnings'])
        if comparison['rows']:
            cap=[comparison['columns']]
            for row in comparison['rows']:
                cap.append(tuple(_number(value) if i in (4,10,11,12) else value for i,value in enumerate(row)))
            warnings.append('시총 비교는 수집시점 스냅샷 간 비교입니다. 시장 기준일 미확인으로 전일·전전일 확정 시총이 아니며 첫날은 이전 수집 이력이 없습니다.')
    tables=dict(zip(REPORT_NAMES,(metals,fx,market,raw_cap,cap,[('구분','종목','시장·고시일','수치','단위','상태','출처')])))
    stocks=[('코드','종목명','시장일','수치','비교일','비교종가','전일대비','등락률(%)','단위','상태','출처')]
    for r in public['stocks']:
        pct=_number(r['pct'])
        stocks.append((r['instrument_id'],r['label'],r['previous_date'],_number(r['previous_close']),r['prior_date'],_number(r['prior_close']),_number(r['change']),round(pct,6) if pct is not None else None,r['unit'],r['status'],r['source_url']))
    # Public browser histories must reach reports even when HTTP is blocked or
    # FDR is disabled. Rank/capitalization are never inferred from stock closes.
    existing_stocks={r[0]:i for i,r in enumerate(stocks[1:],1)}
    equity_pairs=select_closes(equities,naver_cutoff+'T00:00:00+09:00')
    warnings.extend(equity_pairs['warnings'])
    for r in equity_pairs['rows']:
        code=r['stock_code']; index=existing_stocks.get(code)
        if r['status']!='close_pair': continue
        r=checked_daily_pair(r,equities)
        if index is not None and stocks[index][9]=='close_pair' and r['status']!='close_pair': continue
        name=next((e.get('name') for e in reversed(equities) if e['stock_code']==code and e.get('name')),code)
        pct=_number(r['pct'])
        row=(code,name,r['previous_date'],_number(r['previous_close']),r['prior_date'],_number(r['prior_close']),_number(r['change']),round(pct,6) if pct is not None else None,r['unit'],'close_pair_naver' if r['status']=='close_pair' else r['status'],r['source_url'])
        if index is not None: stocks[index]=row
        else: stocks.append(row)
    tables['보고용_주가']=stocks
    lme_report=[('금속','고시일','계약','방향','가격','단위','기준','출처')]
    latest_lme={}
    for r in sorted(lme_rows,key=lambda row:row['market_date']):
        if r['side']=='Ask':latest_lme[r['instrument_id']]=r
    for r in sorted(latest_lme.values(),key=lambda row:(row['metal'],row['contract'])):
        lme_report.append(({'Nickel':'니켈','Copper':'구리','Cobalt':'코발트'}[r['metal']],r['market_date'],r['contract'],r['side'],_number(r['value']),r['unit'],
                           'Official Settlement' if r['is_settlement'] else 'Official',r['source_url']))
    if lme_rows:tables['보고용_LME']=lme_report
    public_raw=[r for r in raw.get('fdr_observations',[]) if dated(r,'market_date') and chosen(r['instrument_id'],f"FDR|{r['instrument_id']}|{r['unit']}|Actual|MID")]
    if public_raw:
        cols=tuple(sorted(public_raw[0]))
        sheets['FDR_종가원본']=[cols]+[tuple(r.get(k) for k in cols) for r in public_raw]
    held=[q for q in public['quarantine'] if dated(q,'market_date')]
    if held:
        cols=tuple(sorted(held[0]));sheets['FDR_보류이력']=[cols]+[tuple(r.get(k) for k in cols) for r in held]
    for table,name in (('market_indicators','NAVER_지표원본'),('equity_rank_snapshots','NAVER_시총원본')):
        selected_raw=naver_selected[table]
        if selected_raw:
            raw_cols=tuple(sorted(selected_raw[0]))
            sheets[name]=[raw_cols]+[tuple(r.get(k) for k in raw_cols) for r in selected_raw]
    if captures:
        cols=('id','captured_at','entity','entity_key','raw_json','reason')
        sheets['NAVER_미검증캡처']=[cols]+[tuple(r.get(k) for k in cols) for r in captures]
    for row in metals[1:]:tables['보고용_종합'].append(('금속',row[0],row[1],row[2],row[3],row[4],row[5]))
    for row in fx[1:]:tables['보고용_종합'].append(('환율',row[0],row[1],row[2],row[4],'고시',row[5]))
    for row in market[1:]:tables['보고용_종합'].append(('시장지표',row[0],row[1],row[2],row[7],row[8],row[9]))
    for row in cap[1:]:tables['보고용_종합'].append(('시총',row[2],row[3],row[4],row[5],row[6],row[7]))
    for row in stocks[1:]:tables['보고용_종합'].append(('주가',row[0],row[2],row[3],row[8],row[9],row[10]))
    for row in lme_report[1:]:tables['보고용_종합'].append(('금속 LME',row[0]+' '+row[2]+' '+row[3],row[1],row[4],row[5],row[6],row[7]))
    import smm_reporting
    smm_rows=[]
    for row in raw.get('smm_observations',[]):
        key='SMM|'+str(row['code'])+'|'+str(row['unit'])+'|Actual|AVG'
        # A request for derived Ni also retains its raw sulphate provenance.
        derived_key='SMM|'+smm_reporting.NI_EQ+'|USD/t Ni|Derived|AVG'
        if not dated(row,'market_date') or not (chosen(row['code'],key) or
                (row['code']=='SMM-NI-NC-001' and chosen(smm_reporting.NI_EQ,derived_key))):
            continue
        try:
            from smm_public import checked_row
            checked_row(row)
        except (ValueError,TypeError,KeyError,ArithmeticError):
            warnings.append('SMM '+str(row.get('code'))+': invalid stored observation excluded');continue
        smm_rows.append(row);observations.append((row['captured_at'],False))
    smm_reporting.add_to_snapshot(smm_rows,sheets,tables)
    if smm_rows:
        warnings.append('SMM은 공개 홈페이지 USD 평균이며 VAT 기준은 미확인입니다. 니켈 환산은 원시세 / 0.2232 파생값으로 니켈 현물시세가 아닙니다.')
        for row in tables['보고용_SMM'][1:]:tables['보고용_종합'].append(('금속 SMM',row[0],row[1],row[2],row[3],row[4],row[5]))
    sheets.update(tables)
    source_dates={'FMB':tuple(sorted({p.date for p in prices})), 'SMBS':tuple(sorted({q.quote_date for q in quotes})), 'NAVER 지표':tuple(sorted({r['market_date'] for r in indicators if r.get('provider')!='FinanceDataReader'})), 'NAVER 시총':tuple(sorted({r['market_date'] for r in equities}))}
    if public_raw:source_dates['FDR 종가']=tuple(sorted({r['market_date'] for r in public_raw if dated(r,'market_date')}))
    if lme_rows:source_dates['LME']=tuple(sorted({r['market_date'] for r in lme_rows}))
    if smm_rows:source_dates['SMM']=tuple(sorted({r['market_date'] for r in smm_rows}))
    context=ReportContext('',_data_as_of(observations), 'TEST / 합성 데이터' if synthetic else '시장 수치 보고서',_freeze_tables(tables),MappingProxyType(source_dates),tuple(dict.fromkeys(warnings)),active,start,end,_freeze_tables(sheets))
    from dataclasses import replace
    payload=context.to_dict();payload.pop('snapshot_id')
    return replace(context,snapshot_id=sha256(canonical_json(payload).encode()).hexdigest())

def make_workbook_sheets(context):
    """Fresh mutable cells; never re-query the DB or alter the frozen snapshot."""
    sheets={k:[tuple(excel_safe(c) for c in r) for r in rows] for k,rows in context._sheets.items()}
    sheets['보고서_메타']=[('항목','값'),('Snapshot SHA-256',context.snapshot_id),('자료 기준 시각',context.as_of or '미확인'),('라벨',context.label),('워크스페이스',context.workspace_id),('시작일',context.start),('종료일',context.end)]+[(source+' 시장·고시일',', '.join(dates) or '미고시') for source,dates in context.source_dates.items()]+[('자료 주의사항',excel_safe(w)) for w in context.warnings]
    return sheets


def make_accumulation_sheets(context):
    """Metal/FX operating workbook; securities belong only to report outputs.

    Omitted sheets are left untouched by COM, never deleted from existing files.
    The DB and report context keep all observations and provenance.
    """
    sheets=make_workbook_sheets(context)
    excluded={'보고용_시장지표','증시_시총스냅샷','보고용_시총','보고용_주가','보고용_종합'}
    sheets={name:rows for name,rows in sheets.items()
            if name not in excluded and not name.startswith(('NAVER_','FDR_'))}
    for name in ('일별시세','일별요약','월별시세','월별건수'):
        rows=sheets.get(name,[])
        if len(rows)<2:continue
        keep=[i for i,source in enumerate(rows[1]) if i==0 or source not in ('NAVER','FDR')]
        sheets[name]=[tuple(row[i] if i<len(row) else None for i in keep) for row in rows]
    sheets['가격열설정']=[row for row in sheets.get('가격열설정',[]) if not str(row[0]).startswith(('NAVER|','FDR|'))]
    if '보류셀' in sheets:
        sheets['보류셀']=[row for row in sheets['보류셀'] if len(row)<3 or not str(row[2]).startswith(('NAVER|','FDR|'))]
    return sheets
