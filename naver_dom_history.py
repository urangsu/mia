"""Parse observed NAVER daily-price tables, with no network or browser side effects.

Only source-bound 날짜/종가 tables establish historical closes. Today's rows are
excluded even after market hours. Changes, ranks and capitalization are not
derived from history prices; pair comparison belongs to naver_close.
"""
import json
import re
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlparse

from naver_markets import DOM, KST, Node


INDEX_PATHS = {
    'KOSPI': '/domestic/index/KOSPI/price',
    'KOSDAQ': '/domestic/index/KOSDAQ/price',
    'NASDAQ': '/worldstock/index/.IXIC/price',
    'SP500': '/worldstock/index/.INX/price',
    'GOLD': '/marketindex/metals/GCcv1/price',
    'WTI': '/marketindex/energy/CLcv1/price',
    'US10Y': '/marketindex/bond/US10YT=RR/price',
    'KR10Y': '/marketindex/bond/KR10YT=RR/price',
    'KR3Y': '/marketindex/bond/KR3YT=RR/price',
    'KR_CORP_AA_3Y': '/marketindex/domesticInterest/KFIA103009/price',
}


def _source_matches(source_url, instrument_id, equity):
    try:
        source = urlparse(source_url)
        if source.scheme != 'https' or source.hostname != 'stock.naver.com':
            return False
        if source.username or source.password or source.port not in (None, 443):
            return False
        if equity:
            if not re.fullmatch(r'\d{6}', instrument_id):
                return False
            expected = '/domestic/stock/' + instrument_id + '/price'
        else:
            expected = INDEX_PATHS.get(instrument_id)
        return expected is not None and source.path == expected
    except (ValueError, TypeError):
        return False


def _row_date(text):
    match = re.fullmatch(r'\s*(20\d{2}|\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*', text)
    if match is None:
        return None
    year, month, day = map(int, match.groups())
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _close_price(text):
    text = re.sub(r'\s+', '', text)
    if not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', text):
        return None
    value = text.replace(',', '')
    return value if Decimal(value) > 0 else None


def _table_rows(table):
    for node in table.walk():
        if node.tag != 'tr':
            continue
        ancestor = node.parent
        while ancestor and ancestor.tag != 'table':
            ancestor = ancestor.parent
        if ancestor is table:
            yield node


def parse_daily_history(html, instrument_id, source_url, captured_at=None, equity=False,
                        name='', *, unit=None, currency=None):
    """Return {rows, warnings}; accept one close but warn when no pair exists."""
    warnings = []
    if not _source_matches(source_url, instrument_id, equity):
        return {'rows': [], 'warnings': [str(instrument_id) + ': daily history source identity mismatch']}
    if instrument_id == 'GOLD' and (currency != 'USD' or unit not in ('USD/트로이온스', 'USD/oz', 'USD/OZS')):
        return {'rows': [], 'warnings': ['GOLD: explicit USD/ounce recent-contract unit required']}
    if instrument_id == 'WTI' and (currency != 'USD' or unit not in ('USD/bbl', 'USD/BBL', 'USD/배럴')):
        return {'rows': [], 'warnings': ['WTI: explicit USD/barrel recent-contract unit required']}
    if instrument_id in ('US10Y', 'KR10Y','KR3Y','KR_CORP_AA_3Y') and (unit != '%' or currency is not None):
        return {'rows': [], 'warnings': [instrument_id + ': explicit percent government-bond yield unit required']}
    try:
        captured = datetime.now(KST) if captured_at is None else (
            captured_at if isinstance(captured_at, datetime) else datetime.fromisoformat(str(captured_at)))
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=KST)
        today = captured.astimezone(KST).date()
    except (ValueError, TypeError):
        return {'rows': [], 'warnings': [str(instrument_id) + ': invalid capture timestamp']}
    captured_text = captured.isoformat()
    by_date = {}
    conflicts = set()
    matched_table = False
    for table in (node for node in DOM(html).root.walk() if node.tag == 'table'):
        table_rows = list(_table_rows(table))
        columns = None
        for row in table_rows:
            headers = [re.sub(r'\s+', '', child.text()) for child in row.children
                       if isinstance(child, Node) and child.tag == 'th']
            if headers.count('날짜') == 1 and headers.count('종가') == 1:
                columns = headers.index('날짜'), headers.index('종가')
                break
        if columns is None:
            continue
        matched_table = True
        for row in table_rows:
            cells = [child for child in row.children if isinstance(child, Node) and child.tag == 'td']
            if len(cells) <= max(columns):
                continue
            market_day = _row_date(cells[columns[0]].text())
            value = _close_price(cells[columns[1]].text())
            if market_day is None or value is None:
                warnings.append(str(instrument_id) + ': invalid daily history date/close skipped')
                continue
            if market_day >= today:
                continue
            market_date = market_day.isoformat()
            if market_date in conflicts:
                continue
            previous = by_date.get(market_date)
            if previous is not None:
                field = 'price' if equity else 'value'
                if Decimal(previous[field]) != Decimal(value):
                    conflicts.add(market_date)
                    del by_date[market_date]
                    warnings.append(str(instrument_id) + ': conflicting daily closes rejected for ' + market_date)
                continue
            provenance = dict(text=row.text(), close_verified=True,
                table_source='NAVER KRX 일별 시세' if equity else 'NAVER 지수 일별 시세')
            if instrument_id == 'GOLD':
                provenance.update(table_source='NAVER COMEX 금선물 최근월물 일별 시세',
                                  contract_code='GCcv1', price_type='recent_contract_futures')
            elif instrument_id == 'WTI':
                provenance.update(table_source='NAVER NYMEX WTI선물 최근월물 일별 시세',
                                  contract_code='CLcv1', price_type='recent_contract_futures')
            elif instrument_id in ('US10Y', 'KR10Y','KR3Y','KR_CORP_AA_3Y'):
                country = '미국' if instrument_id == 'US10Y' else '한국'
                provenance.update(table_source='NAVER '+country+' 국채10년 수익률 일별 시세',
                                  price_type='government_bond_yield')
                if instrument_id=='KR3Y':provenance['table_source']='NAVER 한국 국채3년 수익률 일별 시세'
                if instrument_id=='KR_CORP_AA_3Y':
                    provenance.update(table_source='NAVER 금융투자협회 회사채3년 AA- 일별 시세',price_type='corporate_bond_yield')
            observation = dict(market_date=market_date, captured_at=captured_text,
                change=None, pct=None, unit='원' if equity else (unit or '포인트'),
                currency='KRW' if equity else currency, status='stale', source_url=source_url,
                raw_json=json.dumps(provenance, ensure_ascii=False))
            if equity:
                observation.update(stock_code=instrument_id, name=name, price=value, rank=None,
                                   market_cap=None, market_cap_unit=None)
            else:
                observation.update(instrument_id=instrument_id, value=value)
            by_date[market_date] = observation
    rows = [by_date[day] for day in sorted(by_date, reverse=True)]
    if not matched_table:
        warnings.append(str(instrument_id) + ': 날짜/종가 daily history table missing')
    if len(rows) < 2:
        warnings.append(str(instrument_id) + ': historical close pair missing')
    return {'rows': rows, 'warnings': warnings}
