"""Read-only HTML projection; storage precision/provenance remain unchanged."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlsplit
import re

KST = timezone(timedelta(hours=9))
LABELS = {'KOSPI':'코스피','KOSDAQ':'코스닥','SP500':'S&P 500','NASDAQ':'나스닥',
          'US10Y':'미국 국채 10년','KR10Y':'한국 국채 10년','GOLD':'금 선물','WTI':'WTI 원유'}


def _number(value):
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def percentage(value, *, signed=True):
    number = _number(value)
    if number is None:
        return '—'
    number = number.quantize(Decimal('.1'), rounding=ROUND_HALF_UP)
    if not number:
        number = abs(number)
    return ('+' if signed and number > 0 else '') + format(number, '.1f') + '%'


def number_text(value, *, signed=False):
    number = _number(value)
    if number is None:
        return '—'
    rounded = number.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    # A tiny observed change must not silently become zero.
    text = format(number, ',f') if number and not rounded else format(abs(rounded) if not rounded else rounded, ',.2f')
    text = text.rstrip('0').rstrip('.') if '.' in text else text
    return ('+' if signed and number > 0 else '') + text


def safe_url(value):
    for candidate in str(value or '').split(' / '):
        try:
            parsed = urlsplit(candidate.strip())
            if (parsed.scheme in ('http','https') and parsed.hostname and not parsed.username and not parsed.password
                    and not any(c.isspace() or ord(c)<32 for c in candidate)):
                return candidate.strip()
        except ValueError:
            pass
    return ''


def _day(value):
    return str(value or '')[:10].replace('-', '.') or '기준일 미확인'


def _stamp(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if stamp.tzinfo is not None:
            return stamp.astimezone(KST)
    except ValueError:
        pass
    return None


def capture_label(values):
    stamps = sorted(stamp for value in values if (stamp := _stamp(value)))
    if not stamps:
        return '수집시각 미확인'
    first,last = stamps[0],stamps[-1]
    label = last.strftime('%Y.%m.%d %H:%M')
    if first != last:
        label = first.strftime('%Y.%m.%d %H:%M')+'–'+last.strftime('%H:%M' if first.date()==last.date() else '%Y.%m.%d %H:%M')
    return '수집 '+label+' KST'


def _records(context,name):
    rows = context.tables.get(name,())
    return [dict(zip(rows[0],row)) for row in rows[1:]] if rows else []


def _name(text,source='',note=''):
    return dict(text=str(text or '이름 미확인'),href=safe_url(source),css='name',note=note)


def _value(value, *, percent=False,signed=False):
    number = _number(value)
    css = 'numeric'
    if signed and number:
        css += ' positive' if number>0 else ' negative'
    return dict(text=percentage(value,signed=signed) if percent else number_text(value,signed=signed),css=css,href='',note='')


def _table(kind,title,subtitle,headers,rows, *, overview=False):
    return dict(kind=kind,name=title,subtitle=subtitle,headers=headers,rows=rows,overview=overview)


def _groups(rows,*keys):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(key) or '' for key in keys)].append(row)
    return sorted(groups.items(),key=lambda item:tuple(str(v) for v in item[0]),reverse=True)


def _latest_caps(rows):
    """Latest capture-day cohort, no price-only history or old-code forward fill."""
    samples = [r for r in rows if _number(r.get('시가총액')) is not None]
    if not samples:
        return []
    cohort = max((r.get('수집시각') or r.get('시장일') or '')[:10] for r in samples)
    samples = [r for r in samples if (r.get('수집시각') or r.get('시장일') or '')[:10]==cohort]
    selected = defaultdict(list)
    for row in samples:
        selected[row.get('코드') or row.get('종목명')].append(row)
    result = []
    for candidates in selected.values():
        latest = max(r.get('수집시각') or r.get('시장일') or '' for r in candidates)
        newest = [r for r in candidates if (r.get('수집시각') or r.get('시장일') or '')==latest]
        row = dict(newest[-1])
        if len({(str(r.get('시가총액')),r.get('단위'),r.get('종목명')) for r in newest})>1:
            row['시가총액'] = None
        result.append(row)
    return sorted(result,key=lambda r:(r.get('순위') or 999,r.get('코드') or ''))


def presentation_tables(context):
    """Semantic display cells, grouped by actual date; never changes context."""
    tables = []
    for (day,),rows in _groups(_records(context,'보고용_금속시세'),'고시일'):
        body = []
        for row in rows:
            note = str(row.get('단위') or '단위 미확인')
            if row.get('구분')=='Forecast':
                note += ' · 전망치'
            source = row.get('출처')
            if (not safe_url(source) and source in ('Chart','AG Grid','FMB')
                    and re.fullmatch(r'[a-zA-Z0-9_-]{12,80}',context.workspace_id)):
                source = 'https://dashboard.fastmarkets.com/w/'+context.workspace_id+'/'
            cell = _name(row.get('품목명'),source,note)
            cell['detail'] = row.get('원본 조건') or ''
            body.append([cell,_value(row.get('Mid'),percent='%' in note)])
        tables.append(_table('metals','금속 가격 ('+_day(day)+')','',('품목','가격'),body))
    for (day,),rows in _groups(_records(context,'보고용_LME'),'고시일'):
        body = [[_name(r['금속']+(' 현물' if r['계약']=='Cash' else ' 3개월물'),r.get('출처')),_value(r.get('가격'))] for r in rows]
        tables.append(_table('metals','금속 공식가격 ('+_day(day)+')','USD/t · Ask · 현물은 Official Settlement',('금속','가격'),body))
    for (day,),rows in _groups(_records(context,'보고용_환율'),'고시일'):
        body = []
        for row in rows:
            source = safe_url(row.get('출처'))
            if not source and row.get('출처') in ('SMBS','서울외국환중개'):
                source = 'http://www.smbs.biz/ExRate/StdExRate.jsp'
            basis = str(row.get('단위') or '').replace('KRW/','')
            body.append([_name(row.get('통화'),source,basis),_value(row.get('매매기준율')),_value(row.get('전일대비'),signed=True)])
        tables.append(_table('fx','환율 ('+_day(day)+')','원 · 표기 외화 단위당 매매기준율',('통화','기준율','전일 대비'),body))
    for name,kind,title in (('보고용_시장지표','market','시장지표'),('보고용_주가','stocks','주가')):
        for (day,prior),rows in _groups(_records(context,name),'시장일','비교일'):
            body = []
            for row in rows:
                unit = row.get('단위') or ''
                label = row.get('종목명') or LABELS.get(row.get('지표'),row.get('지표'))
                note = '' if kind=='stocks' else {'point':'포인트','points':'포인트'}.get(unit,unit)
                change = _value(row.get('전일대비'),signed=True)
                if unit=='%' and _number(row.get('전일대비')) is not None:
                    # Yield changes: percentage points -> basis points, not % return.
                    change['text'] = percentage(_number(row['전일대비'])*100).replace('%','bp')
                body.append([_name(label,row.get('출처'),note),_value(row.get('수치'),percent=unit=='%'),
                    _value(row.get('비교종가'),percent=unit=='%'),change,
                    _value(row.get('등락률(%)'),percent=True,signed=True)])
            subtitle = '원 · 확정 종가' if kind=='stocks' else '확정 종가 비교'
            if any('calendar_unverified' in str(r.get('상태')) for r in rows):
                subtitle = '관측 종가 · 최신 거래일 확인 필요'
            tables.append(_table(kind,title+' ('+_day(day)+')',subtitle,
                ('종목' if kind=='stocks' else '지표','종가','비교 ('+_day(prior)+')','등락','등락률'),body))
    cap_report = _records(context,'보고용_시총')
    raw_caps = _records(context,'증시_시총스냅샷')
    # A quarantined current report value must never be replaced by raw cache.
    caps = cap_report if cap_report else _latest_caps(raw_caps)
    for (day,prior,unit),rows in _groups(caps,'시장일','비교수집일','단위'):
        capture = any(r.get('수집시각') for r in rows)
        subtitle = capture_label([r.get('수집시각') for r in rows])+' · 확정 종가 아님' if capture else '시장 기준일 '+_day(day)
        subtitle += ' · '+(unit or '단위 미확인')
        comparison = any('비교시총' in r for r in rows)
        if comparison:
            subtitle += ' · 수집 스냅샷 비교 ('+_day(prior)+')' if prior else ' · 첫 수집: 이전 비교 자료 없음'
        headers = ['순위','종목','시가총액']+(['비교 시총','증감','등락률'] if comparison else [])
        body = []
        for row in rows:
            item = [_value(row.get('순위')),_name(row.get('종목명'),row.get('출처')),_value(row.get('시가총액') if unit and unit!='미확인' else None)]
            if comparison:
                item += [_value(row.get('비교시총')),_value(row.get('시총증감'),signed=True),_value(row.get('등락률(%)'),percent=True,signed=True)]
            body.append(item)
        tables.append(_table('caps','시가총액'+(' · 수집 스냅샷' if capture else ' ('+_day(day)+')'),subtitle,headers,body))
    order = {'metals':0,'fx':1,'market':2,'caps':3,'stocks':4}
    tables.sort(key=lambda table:order[table['kind']])
    names = {str(r.get('코드')):r.get('종목명') for r in cap_report+raw_caps+_records(context,'보고용_주가')}
    for (day,),rows in _groups(_records(context,'보고용_종합'),'시장·고시일'):
        body = []
        for row in rows:
            label = names.get(str(row.get('종목'))) or LABELS.get(row.get('종목'),row.get('종목'))
            unit = row.get('단위') or ''
            body.append([_name(label,row.get('출처'),unit),_value(row.get('수치'),percent='%' in unit)])
        tables.append(_table('overview','종합 ('+_day(day)+')','',('항목','수치'),body,overview=True))
    return tables
