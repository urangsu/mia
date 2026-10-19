"""Choose prior completed NAVER source-market closes, without network or inference.

select_closes(rows, captured_at) returns {rows, warnings, captured_at, cutoff_date}.
Rows use instrument_id/value or stock_code/price. Inputs must already be verified:
only final/stale statuses with source-close evidence qualify; this selector does not create source-close
evidence from age or reconstruct a close from vendor change/pct. Upstream live
NAVER historical DOM compatibility remains unverified. Until two confirmed actual
market dates exist, output is missing_history (including futures).

All numerical outputs are exact Decimal strings. Naive capture timestamps, if
supplied, mean KST. Strict cutoff is capture's KST calendar date, even after close.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import re

KST=timezone(timedelta(hours=9))


def _capture(value):
    moment=value if isinstance(value,datetime) else datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if moment.tzinfo is None:moment=moment.replace(tzinfo=KST)
    return moment.astimezone(KST)


def _number(value):
    if isinstance(value,bool) or value is None:return None
    try:
        result=Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation,ValueError):return None


def _text(value):
    if value is None:return None
    text=format(value if value else Decimal(0),'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def is_verified_close(row):
    """Legacy final denotes explicit closed semantics; age-only stale never does.

    New observations carry a strict boolean close_verified in raw_json. Explicit
    false evidence also blocks final; malformed/absent stale evidence fails closed.
    """
    if row.get('status') not in ('final','stale'):return False
    raw=row.get('raw_json') or {}
    if isinstance(raw,str):
        try:raw=json.loads(raw)
        except (ValueError,TypeError):raw={}
    if not isinstance(raw,dict):raw={}
    flags=[container['close_verified'] for container in (row,raw) if 'close_verified' in container]
    if flags:
        return all(flag is True for flag in flags)
    return row.get('status')=='final'


def select_closes(rows,captured_at):
    captured=_capture(captured_at)
    cutoff=captured.date().isoformat()
    groups=defaultdict(list)
    warnings=[]
    for original in rows:
        row=dict(original)
        if row.get('instrument_id'):
            identity=('instrument_id',str(row['instrument_id']))
        elif isinstance(row.get('stock_code'),str) and re.fullmatch(r'\d{6}',row['stock_code']):
            identity=('stock_code',row['stock_code'])
        else:
            warnings.append('Observation without a valid instrument_id or zero-preserving stock_code excluded')
            continue
        groups[identity].append(row)
    output=[]
    for (kind,key),observations in sorted(groups.items()):
        by_date=defaultdict(list)
        for observation in observations:
            market_date=observation.get('market_date')
            if not is_verified_close(observation) or not isinstance(market_date,str):continue
            try:
                source_date=date.fromisoformat(market_date)
            except ValueError:continue
            if source_date.isoformat()!=market_date or market_date>=cutoff:continue
            number=_number(observation.get('value' if kind=='instrument_id' else 'price'))
            if number is None:
                warnings.append(key+' '+market_date+': invalid verified close excluded')
                continue
            by_date[market_date].append((number,observation))
        dates=[]
        quarantined=[]
        for market_date,items in by_date.items():
            signatures={(number,item.get('unit'),item.get('currency')) for number,item in items}
            if len(signatures)>1:
                quarantined.append(market_date)
                warnings.append(key+' '+market_date+': conflicting same-date observations quarantined')
            else:
                # Identical repeated observations do not manufacture another day.
                dates.append((market_date,items[-1][0],items[-1][1]))
        dates.sort(key=lambda x:x[0],reverse=True)
        result={kind:key,'previous_close':None,'prior_close':None,'previous_date':None,
                'prior_date':None,'change':None,'pct':None,'unit':None,'currency':None,
                'status':'missing_history','source_url':None,'previous_source_url':None,
                'prior_source_url':None,'quarantined_dates':sorted(quarantined)}
        for prefix,entry in zip(('previous','prior'),dates[:2]):
            market_date,number,observation=entry
            result[prefix+'_date']=market_date
            result[prefix+'_close']=_text(number)
            result[prefix+'_source_url']=observation.get('source_url')
        if dates:
            observation=dates[0][2]
            result.update(unit=observation.get('unit'),currency=observation.get('currency'),source_url=observation.get('source_url'))
        if len(dates)<2:
            warnings.append(key+': missing_history; two confirmed distinct pre-capture source-market dates required, never inferred from current price/change')
        elif not dates[0][2].get('unit') or (dates[0][2].get('unit'),dates[0][2].get('currency')) != (dates[1][2].get('unit'),dates[1][2].get('currency')):
            warnings.append(key+': missing_history; close units/currencies absent or incomparable')
        else:
            previous,prior=dates[0][1],dates[1][1]
            result.update(status='close_pair',change=_text(previous-prior))
            if prior:
                result['pct']=_text((previous-prior)/prior*Decimal(100))
            else:
                warnings.append(key+': prior close is zero; percentage is undefined (not fabricated)')
        output.append(result)
    return {'rows':output,'warnings':warnings,'captured_at':captured.isoformat(),'cutoff_date':cutoff}
