"""Pure KRX live-cap capture comparisons, never official market-day closes.

The cohort is the latest observed KST capture day. Each member's latest capture
is compared with its previous distinct capture day, not an invented prior close.
Numbers are Decimal strings; callers may choose a display-only numeric format.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
import json
import re

KST=timezone(timedelta(hours=9))
COLUMNS=('순위','종목명','코드','시장일','시가총액','단위','상태','출처',
         '수집시각','비교수집일','비교시총','시총증감','등락률(%)','이전순위','순위변동')


def _object(value):
    result=json.loads(value) if isinstance(value,str) else value
    if not isinstance(result,dict):raise ValueError('object required')
    return result


def _stamp(value):
    stamp=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('timezone required')
    return stamp.astimezone(KST)


def _text(value):
    result=format(value,'f')
    return result.rstrip('0').rstrip('.') if '.' in result else result


def compare_captures(captures):
    """Return columns/data rows/warnings without changing or filling observations.

    Only explicit KRX_ALL live_ranking KRW/억원 evidence is admitted. Exact-time
    conflicts quarantine that code/day; an older time or older comparison day
    never conceals a conflict. POSCO can remain an unranked extra instrument.
    """
    groups=defaultdict(lambda:defaultdict(list));warnings=[]
    for original in captures:
        if original.get('entity')!='equities':continue
        code=original.get('entity_key')
        try:
            row=_object(original.get('raw_json'))
            code=row.get('stock_code')
            if not isinstance(code,str) or not re.fullmatch(r'\d{6}',code) or original.get('entity_key')!=code:
                raise ValueError('invalid stock identity')
            evidence=_object(row.get('raw_json'))
            if evidence.get('market_scope')!='KRX_ALL' or evidence.get('kind')!='live_ranking':
                raise ValueError('KRX_ALL live_ranking evidence required')
            if evidence.get('market_cap_unit')!='억원' or row.get('currency')!='KRW':
                raise ValueError('KRW capitalization scale must be 억원')
            rank=row.get('rank')
            if rank is not None and (isinstance(rank,bool) or not isinstance(rank,int) or not 1<=rank<=10):
                raise ValueError('invalid Top10 rank')
            if rank is None and code!='005490':raise ValueError('unranked non-POSCO capture')
            if isinstance(row.get('market_cap'),bool):raise ValueError('invalid capitalization')
            cap=Decimal(str(row.get('market_cap')))
            if not cap.is_finite() or cap<0:raise ValueError('invalid capitalization')
            stamp=_stamp(original.get('captured_at'))
            if row.get('captured_at') and _stamp(row['captured_at'])!=stamp:
                raise ValueError('capture timestamp mismatch')
            groups[code][stamp.date().isoformat()].append((stamp,cap,row))
        except (ValueError,TypeError,KeyError,InvalidOperation) as exc:
            warnings.append(f'{code or "unknown"}: capture excluded; {exc}')
    latest_day=max((day for days in groups.values() for day in days),default=None)
    selected={}
    for code,days in groups.items():
        selected[code]={}
        for day,items in days.items():
            stamp=max(item[0] for item in items)
            newest=[item for item in items if item[0]==stamp]
            signatures={(cap,row.get('rank'),row.get('name'),row.get('source_url')) for _,cap,row in newest}
            if len(signatures)!=1:
                selected[code][day]=None
                warnings.append(f'{code} {day}: exact-timestamp capture conflict quarantined')
            else:selected[code][day]=newest[-1]
    rows=[]
    for code,days in selected.items():
        current=days.get(latest_day)
        if current is None:continue  # No historical cohort forward-fill.
        stamp,cap,row=current
        prior_day=max((day for day in days if day<latest_day),default=None)
        prior=days.get(prior_day)
        previous_cap=delta=pct=prior_rank=rank_move=None
        state='missing_prior_capture'
        if prior is not None:
            _,previous_cap,previous=prior
            with localcontext() as ctx:
                ctx.prec=max(50,len(cap.as_tuple().digits)+len(previous_cap.as_tuple().digits)+20)
                delta=cap-previous_cap
                pct=delta/previous_cap*100 if previous_cap else None
            prior_rank=previous.get('rank')
            if row.get('rank') is not None and prior_rank is not None:rank_move=prior_rank-row['rank']
            state='capture_pair'
            if not previous_cap:warnings.append(f'{code}: prior capture is zero; percentage undefined')
        rows.append((row.get('rank'),row.get('name'),code,None,_text(cap),'억원',state,row.get('source_url'),
            stamp.isoformat(),prior_day,_text(previous_cap) if previous_cap is not None else None,
            _text(delta) if delta is not None else None,_text(pct) if pct is not None else None,prior_rank,rank_move))
    rows.sort(key=lambda row:(row[0] if row[0] is not None else 999,row[2]))
    return dict(columns=COLUMNS,rows=rows,warnings=list(dict.fromkeys(warnings)))
