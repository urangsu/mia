"""Offline FDR read model. Calendar gaps never become an older valid-looking pair."""
from decimal import Decimal
import json
from fdr_provider import instruments
from market_sessions import expected_pair, capture_time
from naver_close import is_verified_close


def prepare(observations,targets,captured_at,*,start=None,end=None,series=None,quarantine=()):
    captured=capture_time(captured_at)
    codes={t['instrument_id'] for t in targets}
    specs=instruments([])
    # The 25-code limit bounds one HTTP collection, not years of stored history.
    for code in codes:
        if code.isdigit():specs[code]=instruments([code])[code]
    eligible=[];pairs={};stocks=[];warnings=[];withdrawn=[];audit=[]
    for code in sorted(codes):
        if code not in specs:continue
        spec=specs[code]
        if series is not None and code not in series and not any(str(s).startswith('FDR|'+code+'|') for s in series):continue
        dates=expected_pair(spec.calendar,captured)
        audit.extend(q for q in quarantine if q['instrument_id']==code and q['source_symbol']==spec.symbol)
        blocked={q['market_date'] for q in quarantine if q['instrument_id']==code and q['source_symbol']==spec.symbol and q['active']}
        if spec.kind!='equity':
            withdrawn.extend((day,f'FDR|{code}|{spec.unit}|Actual|MID') for day in blocked if (not start or day>=start) and (not end or day<end))
        accepted=[]
        for original in observations:
            if original['instrument_id']!=code:continue
            row=dict(original,provider='FinanceDataReader',status='final')
            day=row['market_date']
            if day in blocked:continue
            if (start and day<start) or (end and day>=end):continue
            if row.get('source_symbol')!=spec.symbol or (row.get('unit'),row.get('currency'))!=(spec.unit,spec.currency):continue
            if not is_verified_close(row):continue
            # The stored row was admitted only after the source session ended.
            # Never turn older cached captures into evidence for a later session.
            row.update(instrument_id=code)
            accepted.append(row)
        eligible.extend(accepted)
        by_date={r['market_date']:r for r in accepted}
        previous,prior=(by_date.get(d) for d in dates)
        pair=dict(instrument_id=code,previous_date=dates[0],prior_date=dates[1],previous_close=previous['value'] if previous else None,
            prior_close=prior['value'] if prior else None,change=None,pct=None,unit=spec.unit,currency=spec.currency,
            status='missing_history',source_url=spec.source_url,previous_source_url=spec.source_url,prior_source_url=spec.source_url,
            label=spec.label,kind=spec.kind)
        if previous and prior:
            a,b=Decimal(previous['value']),Decimal(prior['value'])
            pair.update(status='close_pair',change=str(a-b),pct=str((a-b)/b*100) if b else None)
        else:warnings.append(f'FDR {code}: missing_history; 기대 거래일 {dates[0]}, {dates[1]} 이력 부족')
        for target in targets:
            if target['instrument_id']==code and target.get('status') in ('failed','partial'):
                warnings.append('FDR 최근 조회 '+code+': '+(target.get('error') or target['status']))
        if spec.kind=='equity':stocks.append(pair)
        else:pairs[code]=pair
    if codes:
        warnings.append('FDR 출처: 한국지수·국내주가 NAVER, 해외 Yahoo. GOLD=GC=F·WTI=CL=F 연속선물 Close이며 현물·공식 정산가가 아닙니다. US10Y는 CBOE ^TNX입니다.')
    return dict(indicators=[r for r in eligible if r['kind']!='equity'],observations=eligible,pairs=pairs,stocks=stocks,warnings=warnings,withdrawn=withdrawn,quarantine=audit)
