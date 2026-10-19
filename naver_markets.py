"""Conservative NAVER DOM-only adapter (no HTTP clients or private endpoints).

parse_* return {rows: list[dict], warnings: list[str]}; numeric values are Decimal
strings. Missing dates are never inferred. collect uses only the supplied Selenium
driver, and collect_and_save stores undated/unverified captures in naver_raw_captures.
Synthetic fixture coverage is not a claim of current NAVER DOM compatibility.
"""
import json
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from urllib.parse import urlparse
from naver_close import is_verified_close

KST = timezone(timedelta(hours=9))
ALLOWED_HOSTS = frozenset(('stock.naver.com', 'finance.naver.com'))
INDICATORS = ('KOSPI', 'KOSDAQ', 'SP500', 'NASDAQ', 'US10Y', 'KR10Y', 'GOLD', 'WTI')
PAGES = (
    ('indicators', 'https://stock.naver.com/market'),
    ('equities', 'https://stock.naver.com/market/stock/kr/stocklist/capitalization'),
    ('equities', 'https://finance.naver.com/item/main.naver?code=005490'),
)
ALIASES = {
    'KOSPI': ('kospi', '코스피'), 'KOSDAQ': ('kosdaq', '코스닥'),
    'SP500': ('sp500', 's&p500', 's&p 500', '.inx', 'spi@spx', 'nix.spi500'),
    'NASDAQ': ('nasdaq', '나스닥종합', '나스닥 종합', '.ixic', 'nas@ixic'),
    'US10Y': ('us10y', '미국 10년', '미국채10년', '미국채 10년'),
    'KR10Y': ('kr10y', '한국 10년', '국고채10년', '국고채 10년'),
    'GOLD': ('gold', '국제 금', '국제금', '금 선물'),
    'WTI': ('wti', '서부텍사스'),
}


class Node:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self):
        if self.tag in ('script', 'style', 'noscript'):
            return ''
        if self.children and all(not isinstance(c, Node) for c in self.children) and '가격이 업데이트되었습니다' in ''.join(self.children):
            return ''
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children).strip()


class DOM(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node()
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'):
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Node(tag, attrs, self.current))

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, text):
        self.current.children.append(text)


def _stamp(value=None):
    if value is None:
        return datetime.now(KST).isoformat(timespec='seconds')
    if isinstance(value, datetime):
        return (value.replace(tzinfo=KST) if value.tzinfo is None else value).isoformat()
    return str(value)


def _date(node):
    candidates = [n.attrs.get('data-date', '') or n.attrs.get('datetime', '') for n in node.walk()]
    candidates.append(node.text())
    for value in candidates:
        match = re.search(r'(?<!\d)(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})(?!\d)', value)
        if match:
            try:
                return datetime(*map(int, match.groups())).date().isoformat()
            except ValueError:
                pass
    return None


def _number(text):
    text = text.replace(',', '').replace('−', '-').replace('＋', '+')
    text = re.sub(r'(?<=[\d.])\s+(?=[\d.])', '', text)
    match = re.search(r'[+\-]?\d+(?:\.\d+)?', text)
    if not match:
        return None
    down=any(s in text for s in ('하락','▼','내림')) or match.group().startswith('-')
    up=any(s in text for s in ('상승','▲','오름')) or match.group().startswith('+')
    if down and up:
        return None
    value = Decimal(match.group())
    if down:
        value = -abs(value)
    elif up:
        value = abs(value)
    return str(value)


def _node_number(node):
    labels=' '.join(n.attrs.get('aria-label','') for n in node.walk()
                    if '가격이 업데이트되었습니다' not in n.attrs.get('aria-label',''))
    return _number(node.text()+' '+labels)


def _field(node, field):
    aliases = {'value': ('price', 'value', 'now_value', 'current'),
               'change': ('change', 'diff', 'gap'), 'pct': ('rate', 'percent', 'pct'),
               'price': ('price', 'now_value', 'current'),
               'market_cap': ('market_cap', 'marketcap', '시가총액')}
    for n in node.walk():
        key = n.attrs.get('data-field', '')
        if key == field:
            return _node_number(n)
    for n in node.walk():
        identity = (n.attrs.get('class','') + ' ' + n.attrs.get('aria-label','')).lower()
        if any(re.search(r'(?<![a-z])' + re.escape(a), identity) for a in aliases.get(field, (field,))):
            if field == 'change' and '%' in n.text():
                continue
            value = _node_number(n)
            if value is not None:
                return value
    return None


def _unit(node):
    for n in node.walk():
        if n.attrs.get('data-unit'):
            return n.attrs['data-unit']
        if n.attrs.get('data-field') == 'unit':
            return n.text()
    match = re.search(r'(달러/배럴|달러/트로이온스|USD/oz|USD/bbl|포인트|원/주|(?<![가-힣])원(?![가-힣])|\bKRW\b|\bUSD\b)', node.text())
    return match.group() if match else None


def _market_cap_unit(node):
    """Capitalization scale is independent of price unit; never copy 원 here."""
    for n in node.walk():
        explicit=n.attrs.get('data-market-cap-unit')
        if explicit and explicit.strip():return explicit.strip()
        if n.attrs.get('data-field')=='market_cap_unit' and n.text().strip():return n.text().strip()
    return None


def _currency(node):
    text = node.text()+' '+str(_unit(node) or '')+' '+' '.join(n.attrs.get('data-currency','') for n in node.walk())
    usd=bool(re.search(r'USD|달러|\$',text,re.I))
    krw=bool(re.search(r'KRW|원|₩',text,re.I))
    if usd and not krw: return 'USD'
    if krw and not usd: return 'KRW'
    return None


def _commodity_unit_ok(key, unit, currency):
    if key not in ('GOLD','WTI'): return unit is not None
    if not unit or not currency: return False
    denominator = r'(?:/|당)\s*(?:oz|트로이온스|온스)' if key=='GOLD' else r'(?:/|당)\s*(?:bbl|배럴)'
    return bool(re.search(denominator,unit,re.I))


def _shared_market_date(node, root):
    # Only explicit scoped metadata may flow into an undated row. Never scan
    # root.text() or descendants of neighboring rows for a convenient date.
    ancestor=node.parent
    while ancestor:
        if ancestor.tag in ('table','section','main'):
            raw=ancestor.attrs.get('data-market-date') or ancestor.attrs.get('data-market-asof') or ancestor.attrs.get('data-date')
            if raw:
                return _date(Node('time',{'datetime':raw}))
        ancestor=ancestor.parent
    for n in root.walk():
        raw=n.attrs.get('data-market-asof')
        if raw:
            parent=n
            row_scoped=False
            while parent:
                if parent.tag=='tr' or parent.attrs.get('data-stock-code'):
                    row_scoped=True
                    break
                parent=parent.parent
            if row_scoped: continue
            return _date(Node('time',{'datetime':raw}))
    return None


def _arith_ok(value, change, pct):
    if value is None or change is None or pct is None:
        return False
    v, c, p = map(Decimal, (value, change, pct))
    if v <= 0 or v-c <= 0:
        return False
    half = lambda d: Decimal(5).scaleb(d.as_tuple().exponent - 1)
    # Propagate displayed-price and change rounding independently, then add
    # the displayed percentage's own half-unit rounding interval.
    tolerance = half(p) + Decimal(100) * (abs(v)*half(c) + abs(c)*half(v)) / ((v-c)**2)
    return abs(c/(v-c)*100-p) <= tolerance


def _close_verified(node):
    return bool(re.search(r'장\s*마감|거래\s*종료|종가|\bclosed\b',node.text(),re.I)) or any(
        n.attrs.get('data-price-type','').lower()=='close' or n.attrs.get('data-session','').lower()=='closed'
        for n in node.walk())


def _status(node, date, captured, valid):
    if not date or not valid:
        return 'unverified'
    if date < datetime.fromisoformat(captured).astimezone(KST).date().isoformat():
        return 'stale'
    return 'final' if _close_verified(node) else 'provisional'


def _identity(node):
    raw = ' '.join((node.attrs.get('data-mini-chart-id',''), node.attrs.get('data-nlogs',''))).lower()
    for key, aliases in ALIASES.items():
        if any(a in raw for a in aliases):
            return key
    # Labels can disambiguate opaque stable identifiers, never unlabeled charts.
    for key, aliases in ALIASES.items():
        if any(a in node.text().lower() for a in aliases):
            return key
    return None


def _merge_observation(rows,row,key,warnings):
    old=next((item for item in rows if item[key]==row[key] and item.get('market_date')==row.get('market_date')),None)
    if old is None:
        rows.append(row);return
    field='value' if key=='instrument_id' else 'price'
    def fact(item):
        number=Decimal(item[field]) if item.get(field) is not None else None
        return number,item.get('unit'),item.get('currency')
    if fact(old)!=fact(row):
        old['status']='unverified'
        old['raw_json']=json.dumps({'conflict':True,'close_verified':False,'observations':[old.get('raw_json'),row.get('raw_json')]},ensure_ascii=False)
        warnings.append(str(row[key])+': conflicting same-instrument/date DOM observations quarantined')


def parse_indicators(html, captured_at=None):
    captured, rows, warnings, seen = _stamp(captured_at), [], [], set()
    root = DOM(html).root
    for node in root.walk():
        if not any(a in node.attrs for a in ('data-mini-chart-id', 'data-nlogs')):
            continue
        key = _identity(node)
        if key is None:
            continue
        value, change, pct = (_field(node, f) for f in ('value','change','pct'))
        date, unit = _date(node), _unit(node)
        valid = _arith_ok(value, change, pct) and _commodity_unit_ok(key,unit,_currency(node))
        status = _status(node, date, captured, valid)
        row = dict(instrument_id=key, market_date=date, captured_at=captured, value=value,
                   change=change, pct=pct, unit=unit, currency=_currency(node), status=status,
                   source_url=PAGES[0][1], raw_json=json.dumps({'text':node.text(),'attrs':node.attrs,'close_verified':_close_verified(node)},ensure_ascii=False))
        _merge_observation(rows,row,'instrument_id',warnings)
        seen.add(key)
        if status == 'unverified': warnings.append(key + ': missing date, unit, numeric fields or change/pct validation failed')
    missing = set(INDICATORS) - seen
    if missing: warnings.append('Indicators absent: ' + ', '.join(sorted(missing)))
    return {'rows':rows, 'warnings':warnings}


def parse_capitalization(html, captured_at=None):
    captured, rows, warnings, seen = _stamp(captured_at), [], [], set()
    root = DOM(html).root
    scope_verified=any(n.attrs.get('data-market-scope')=='KRX_ALL' or n.attrs.get('data-scope')=='KRX_ALL' or
                       (n.attrs.get('aria-selected')=='true' and n.text().strip() in ('전체','KRX 전체','전체시장','전체 시장')) for n in root.walk())
    if not scope_verified: warnings.append('KRX_ALL market scope not verified; ranking skipped (KOSPI-only is not KRX_ALL)')
    candidates = [n for n in root.walk() if n.tag == 'tr' or n.attrs.get('data-stock-code')]
    for node in candidates:
        code = node.attrs.get('data-stock-code')
        link = next((n for n in node.walk() if n.tag == 'a' and re.search(r'(?:code=|/stock/)\d{6}',n.attrs.get('href',''))),None)
        if code is None and link:
            code = re.search(r'(?:code=|/stock/)(\d{6})',link.attrs['href']).group(1)
        if not code or not re.fullmatch(r'\d{6}', code): continue
        rank = node.attrs.get('data-rank')
        if rank is None:
            cells = [n for n in node.children if isinstance(n,Node) and n.tag=='td']
            rank = cells[0].text() if cells else ''
        rank = int(rank) if str(rank).isdigit() else None
        if not scope_verified: rank=None
        if not (rank is not None and 1 <= rank <= 10) and code != '005490': continue
        date, price = _date(node) or _shared_market_date(node,root), _field(node,'price')
        change, pct = _field(node,'change'), _field(node,'pct')
        market_cap = _field(node,'market_cap')
        if price is None:
            table=node.parent
            while table and table.tag!='table': table=table.parent
            if table:
                headers=[n.text().replace(' ','') for n in table.walk() if n.tag=='th']
                cells=[n for n in node.children if isinstance(n,Node) and n.tag=='td']
                values={h:_node_number(c) for h,c in zip(headers,cells)}
                price,change,pct,market_cap=(values.get(h) for h in ('현재가','전일비','등락률','시가총액'))
        valid = _unit(node) is not None and _arith_ok(price,change,pct)
        status = _status(node,date,captured,valid)
        row = dict(stock_code=code, rank=rank, name=link.text() if link else node.attrs.get('data-name',''),
                   market_date=date,captured_at=captured,price=price,change=change,pct=pct,
                   market_cap=market_cap,unit=_unit(node),currency=_currency(node),
                   status=status, source_url=PAGES[1][1],raw_json=json.dumps({'text':node.text(),'attrs':node.attrs,'market_cap_unit':_market_cap_unit(node),'close_verified':_close_verified(node)},ensure_ascii=False))
        _merge_observation(rows,row,'stock_code',warnings); seen.add(code)
        if status=='unverified': warnings.append(code+': undated or invalid equity capture')
    canonical=next((n.attrs.get('content','') for n in root.walk() if n.tag=='meta' and n.attrs.get('property')=='og:url'),'')
    if '005490' not in seen and _allowed(canonical) and re.search(r'[?&]code=005490(?:&|$)',canonical):
        block=next((n for n in root.walk() if 'rate_info' in n.attrs.get('class','').split()),None)
        if block:
            price_node=next((n for n in block.walk() if 'no_today' in n.attrs.get('class','').split()),None)
            change_node=next((n for n in block.walk() if 'no_exday' in n.attrs.get('class','').split()),None)
            price=_node_number(price_node) if price_node else None
            change=_node_number(change_node) if change_node else None
            pct_match=re.search(r'([+\-−]?\d+(?:\.\d+)?)\s*%',change_node.text()) if change_node else None
            pct=_number(pct_match.group(1)) if pct_match else None
            date_node=next((n for n in root.walk() if 'date' in n.attrs.get('class','').split()),None)
            date=_date(date_node) if date_node else None
            heading=next((n.text() for n in root.walk() if n.tag=='h2'),'')
            rows.append(dict(stock_code='005490',rank=None,name=heading,market_date=date,captured_at=captured,
                             price=price,change=change,pct=pct,market_cap=None,unit=_unit(block),currency=_currency(block),
                             status=_status(block,date,captured,_arith_ok(price,change,pct) and _unit(block) is not None),source_url=canonical,
                             raw_json=json.dumps({'text':block.text(),'attrs':block.attrs,'market_cap_unit':_market_cap_unit(block),'close_verified':_close_verified(block)},ensure_ascii=False)))
            if rows[-1]['status']=='unverified': warnings.append('005490: detail fallback missing date or arithmetic validation')
    if not rows: warnings.append('No capitalization rows recognized')
    return {'rows':rows, 'warnings':warnings}


def _allowed(url):
    parsed = urlparse(url)
    return parsed.scheme == 'https' and parsed.hostname in ALLOWED_HOSTS and not parsed.username and parsed.port in (None,443)


def collect(driver, cancelled, logger=print, force=False):
    """Driver must already be attached to existing Chrome 9444; never launches Chrome."""
    started, original, owned = time.monotonic(), None, None
    result = {'indicators':[], 'equities':[], 'warnings':[], 'status':'failed'}
    try:
        if cancelled(): result['status']='cancelled'; return result
        original = driver.current_window_handle
        driver.switch_to.new_window('tab')
        owned = driver.current_window_handle
        for kind, url in PAGES:
            if cancelled(): result['status']='cancelled'; break
            if not _allowed(url): raise ValueError('Unapproved source URL')
            driver.get(url)
            if not _allowed(driver.current_url): raise ValueError('NAVER redirect outside source allowlist')
            parsed = {'rows':[], 'warnings':[]}
            # Conditional DOM readiness polling, bounded to three seconds/page.
            deadline = time.monotonic()+3
            while True:
                if cancelled(): result['status']='cancelled'; break
                if not _allowed(driver.current_url): raise ValueError('NAVER late redirect outside source allowlist')
                html = driver.page_source
                parser = parse_indicators if kind=='indicators' else parse_capitalization
                parsed = parser(html)
                usable=[r for r in parsed['rows'] if is_verified_close(r)]
                if kind=='indicators':
                    ready={r['instrument_id'] for r in usable}==set(INDICATORS)
                elif 'code=005490' in url:
                    ready=any(r['stock_code']=='005490' for r in usable)
                else:
                    ready=set(range(1,11)) <= {r['rank'] for r in usable}
                if ready or time.monotonic() >= deadline: break
                time.sleep(0.1)
            if result['status']=='cancelled': break
            for row in parsed['rows']:
                row['source_url']=driver.current_url
                id_field = 'instrument_id' if kind=='indicators' else 'stock_code'
                _merge_observation(result[kind],row,id_field,result['warnings'])
            result['warnings'].extend(parsed['warnings'])
        else:
            ids={r['instrument_id'] for r in result['indicators'] if is_verified_close(r)}
            codes={r['stock_code'] for r in result['equities'] if is_verified_close(r)}
            ranks={r['rank'] for r in result['equities'] if is_verified_close(r)}
            complete=ids==set(INDICATORS) and set(range(1,11))<=ranks and '005490' in codes
            result['status']='complete' if complete else 'partial'
            if not complete:result['warnings'].append('Verified close evidence incomplete: require all 8 indicators, KRX_ALL ranks 1–10 and 005490; daily gate remains retryable')
    except Exception as exc:
        result['warnings'].append(str(exc)); result['status']='failed'
    finally:
        if owned:
            try:
                if owned in driver.window_handles:
                    driver.switch_to.window(owned); driver.close()
            except Exception as exc: result['warnings'].append('Temporary tab cleanup: '+str(exc))
        if original:
            try:
                if original in driver.window_handles: driver.switch_to.window(original)
            except Exception as exc: result['warnings'].append('Original tab restore: '+str(exc))
        result['elapsed']=round(time.monotonic()-started,3)
        for message in result['warnings']: logger('[NAVER] '+message)
    return result


INDICATOR_COLUMNS = ('instrument_id','market_date','captured_at','value','change','pct','unit','currency','status','source_url','raw_json')
EQUITY_COLUMNS = ('stock_code','rank','name','market_date','captured_at','price','change','pct','market_cap','unit','currency','status','source_url','raw_json')


def initialize_schema(cx):
    cx.execute('''CREATE TABLE IF NOT EXISTS market_indicators (
        instrument_id TEXT NOT NULL, market_date TEXT NOT NULL, captured_at TEXT NOT NULL,
        value TEXT, change TEXT, pct TEXT, unit TEXT, currency TEXT, status TEXT,
        source_url TEXT, raw_json TEXT, PRIMARY KEY(instrument_id,market_date))''')
    cx.execute('''CREATE TABLE IF NOT EXISTS equity_rank_snapshots (
        stock_code TEXT NOT NULL, rank INTEGER, name TEXT, market_date TEXT NOT NULL,
        captured_at TEXT NOT NULL, price TEXT, change TEXT, pct TEXT, market_cap TEXT,
        unit TEXT, currency TEXT, status TEXT, source_url TEXT, raw_json TEXT,
        PRIMARY KEY(stock_code,market_date))''')
    cx.execute('''CREATE TABLE IF NOT EXISTS naver_revisions (
        id INTEGER PRIMARY KEY, entity TEXT NOT NULL, entity_key TEXT NOT NULL,
        market_date TEXT NOT NULL, revised_at TEXT NOT NULL, old_json TEXT NOT NULL,
        new_json TEXT NOT NULL)''')
    cx.execute('''CREATE TABLE IF NOT EXISTS naver_daily_runs (
        capture_day TEXT PRIMARY KEY, completed_at TEXT NOT NULL, status TEXT NOT NULL)''')
    cx.execute('''CREATE TABLE IF NOT EXISTS naver_raw_captures (
        id INTEGER PRIMARY KEY, captured_at TEXT NOT NULL, entity TEXT NOT NULL,
        entity_key TEXT NOT NULL, raw_json TEXT NOT NULL, reason TEXT NOT NULL)''')


def collect_and_save(driver, db_path, cancelled, logger=print, force=False):
    started, day = time.monotonic(), datetime.now(KST).date().isoformat()
    output = {'indicators':0,'equities':0,'raw_captures':0,'warnings':[],'status':'failed','elapsed':0}
    with closing(sqlite3.connect(db_path)) as cx, cx:
        initialize_schema(cx)
        if not force and cx.execute('SELECT 1 FROM naver_daily_runs WHERE capture_day=? AND status=?',(day,'complete')).fetchone():
            output.update(status='skipped_daily',elapsed=round(time.monotonic()-started,3)); return output
        result=collect(driver,cancelled,logger,force)
        output.update(status=result['status'], warnings=result.get('warnings',[]))
        if result['status'] in ('cancelled','failed') or cancelled():
            if cancelled(): output['status']='cancelled'
            output['elapsed']=round(time.monotonic()-started,3); return output
        for entity,table,columns,key in (('indicators','market_indicators',INDICATOR_COLUMNS,'instrument_id'),('equities','equity_rank_snapshots',EQUITY_COLUMNS,'stock_code')):
            for row in result.get(entity,[]):
                if not row.get('market_date') or row.get('status')=='unverified':
                    cx.execute('INSERT INTO naver_raw_captures(captured_at,entity,entity_key,raw_json,reason) VALUES(?,?,?,?,?)',(_stamp(row.get('captured_at')),entity,row[key],json.dumps(row,ensure_ascii=False),'unverified or missing market date'))
                    output['raw_captures']+=1; continue
                old=cx.execute('SELECT '+','.join('"'+c+'"' for c in columns)+' FROM '+table+' WHERE '+key+'=? AND market_date=?',(row[key],row['market_date'])).fetchone()
                old=dict(zip(columns,old)) if old else None
                semantic=[c for c in columns if c not in ('captured_at','raw_json','source_url')]
                changed=old is not None and any(old[c]!=row.get(c) for c in semantic)
                if changed:
                    cx.execute('INSERT INTO naver_revisions(entity,entity_key,market_date,revised_at,old_json,new_json) VALUES(?,?,?,?,?,?)',(entity,row[key],row['market_date'],row['captured_at'],json.dumps(old,ensure_ascii=False),json.dumps(row,ensure_ascii=False)))
                if old is None or changed:
                    names=','.join('"'+c+'"' for c in columns)
                    cx.execute('INSERT OR REPLACE INTO '+table+' ('+names+') VALUES('+','.join('?' for _ in columns)+')',tuple(row.get(c) for c in columns))
                else:
                    # Refresh observation evidence even when displayed facts are
                    # identical. A later capture can supply an explicit cap scale
                    # absent before; that is not a new price/rank revision.
                    cx.execute('UPDATE '+table+' SET captured_at=?,source_url=?,raw_json=? WHERE '+key+'=? AND market_date=?',
                               (row.get('captured_at'),row.get('source_url'),row.get('raw_json'),row[key],row['market_date']))
                output[entity]+=1
        if result['status']=='complete':
            completed_at=_stamp()
            capture_day=datetime.fromisoformat(completed_at).astimezone(KST).date().isoformat()
            cx.execute('INSERT OR REPLACE INTO naver_daily_runs VALUES(?,?,?)',(capture_day,completed_at,'complete'))
    output['elapsed']=round(time.monotonic()-started,3)
    return output
