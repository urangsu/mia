"""Public LME Official table only: scoped source dates, explicit contracts/sides.

No hidden endpoints, calculated Mid or change to Fastmarkets raw storage. The
caller supplies an already ownership-verified driver; only our new tab is closed.
"""
from contextlib import closing
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlparse

from naver_markets import DOM, KST, Node

SOURCE_URL = 'https://www.lme.com/Market-data/Reports-and-data/LME-Official-Prices#LME+Official+prices'
POLL_SECONDS = 3.0
METALS = {'Copper': 'CU', 'Nickel': 'NI', 'Cobalt': 'CO'}
CONTRACTS = {'Cash': 'CASH', '3-month': '3M'}
COLUMNS = ('instrument_id', 'market_date', 'metal', 'contract', 'side', 'value',
           'unit', 'currency', 'price_type', 'is_settlement', 'captured_at', 'source_url', 'raw_json')
MONTHS = {name: number for number, name in enumerate(
    ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'), 1)}


def _source_ok(url):
    try:
        parsed = urlparse(url)
        return (parsed.scheme == 'https' and parsed.hostname in ('www.lme.com', 'lme.com')
                and not parsed.username and not parsed.password and parsed.port in (None, 443)
                and parsed.path.lower().rstrip('/') == '/market-data/reports-and-data/lme-official-prices')
    except (TypeError, ValueError):
        return False


def _children(node, tags):
    return [child for child in node.children if isinstance(child, Node) and child.tag in tags]


def _text(node):
    return re.sub(r'\s+', ' ', node.text()).strip()


def _number(text):
    text = text.strip()
    if not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', text):
        return None
    value = text.replace(',', '')
    return value if Decimal(value) > 0 else None


def _source_date(label):
    match = re.fullmatch(r'Data valid for (\d{1,2}) ([A-Za-z]+) (20\d{2})', label)
    if not match or match[2] not in MONTHS:
        return None
    try:
        return date(int(match[3]), MONTHS[match[2]], int(match[1]))
    except ValueError:
        return None


def _slots(table):
    heads = [node for node in table.walk() if node.tag == 'thead']
    if len(heads) != 1:
        return None
    rows = [node for node in heads[0].walk() if node.tag == 'tr']
    if len(rows) != 2:
        return None
    groups = []
    for cell in _children(rows[0], ('th',)):
        label = _text(cell)
        normalized = re.sub(r'[-\s]', '', label).lower()
        contract = 'Cash' if normalized == 'cash' else '3-month' if normalized == '3month' else None
        try:
            width = int(cell.attrs.get('colspan', '1'))
        except ValueError:
            return None
        if width < 1 or width > 40:
            return None
        groups.extend([contract] * width)
    sides = _children(rows[1], ('th',))
    if len(sides) != len(groups):
        return None
    slots = [(index, contract, _text(sides[index])) for index, contract in enumerate(groups)
             if contract is not None]
    if len(slots) != 4 or {(contract, side) for _, contract, side in slots} != {
        (contract, side) for contract in CONTRACTS for side in ('Bid', 'Ask')}:
        return None
    return slots


def parse(html, captured_at=None, source_url=SOURCE_URL):
    warnings = []
    if not _source_ok(source_url):
        return {'rows': [], 'warnings': ['LME Official source URL mismatch']}
    try:
        captured = datetime.now(KST) if captured_at is None else (
            captured_at if isinstance(captured_at, datetime) else datetime.fromisoformat(str(captured_at)))
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=KST)
    except (ValueError, TypeError):
        return {'rows': [], 'warnings': ['LME Official capture timestamp invalid']}
    datasets = [node for node in DOM(html).root.walk() if node.attrs.get('id') == 'dataset-tab-0']
    if len(datasets) != 1:
        return {'rows': [], 'warnings': ['LME Official scoped dataset-tab-0 missing/ambiguous']}
    scope = datasets[0]
    tops = [node for node in scope.walk() if 'data-set-tabs__content-top' in node.attrs.get('class', '').split()]
    labels = []
    units = []
    for top in tops:
        for node in top.walk():
            if node.tag != 'span':
                continue
            ancestor = node
            refreshed = False
            while ancestor is not None and ancestor is not top.parent:
                if '--refreshed-on' in ancestor.attrs.get('class', ''):
                    refreshed = True
                ancestor = ancestor.parent
            if refreshed:
                continue
            text = _text(node)
            if text.startswith('Data valid for '):
                labels.append(text)
            if text == 'Prices shown in USD per metric tonne':
                units.append(text)
    unique_labels = set(labels)
    market_day = _source_date(next(iter(unique_labels))) if len(unique_labels) == 1 else None
    if market_day is None or not units or market_day > captured.astimezone(KST).date():
        return {'rows': [], 'warnings': ['LME Official valid source date/USD per metric tonne unit missing, invalid or future']}
    rows = {}
    conflicts = set()
    for table in (node for node in scope.walk() if node.tag == 'table'):
        slots = _slots(table)
        if slots is None:
            continue
        for node in table.walk():
            if node.tag != 'tr':
                continue
            cells = _children(node, ('th', 'td'))
            if not cells or cells[0].tag != 'th' or cells[0].attrs.get('scope') != 'row':
                continue
            metal = _text(cells[0])
            if metal not in METALS:
                continue
            for index, contract, side in slots:
                if len(cells) <= index or cells[index].tag != 'td' or cells[index].attrs.get('data-table-column-header') != side:
                    warnings.append('LME '+metal+' '+contract+' '+side+': source column mismatch/missing')
                    continue
                value = _number(_text(cells[index]))
                if value is None:
                    warnings.append('LME '+metal+' '+contract+' '+side+': missing/invalid source price')
                    continue
                key = metal, contract, side
                if key in conflicts:
                    continue
                if key in rows and Decimal(rows[key]['value']) != Decimal(value):
                    conflicts.add(key)
                    del rows[key]
                    warnings.append('LME duplicate conflicting Official price quarantined: '+'/'.join(key))
                    continue
                rows[key] = dict(instrument_id='LME_'+METALS[metal]+'_'+CONTRACTS[contract]+'_'+side.upper(),
                    market_date=market_day.isoformat(), metal=metal, contract=contract, side=side,
                    value=value, unit='USD/t', currency='USD', price_type='Official',
                    is_settlement=(contract == 'Cash' and side == 'Ask'), captured_at=captured.isoformat(), source_url=source_url,
                    raw_json=json.dumps(dict(source_date_label=next(iter(unique_labels)),
                        unit_label=units[0], text=node.text()), ensure_ascii=False))
    for metal in METALS:
        for contract in CONTRACTS:
            bid, ask = rows.get((metal, contract, 'Bid')), rows.get((metal, contract, 'Ask'))
            if bid and ask and Decimal(bid['value']) > Decimal(ask['value']):
                del rows[(metal, contract, 'Bid')]
                del rows[(metal, contract, 'Ask')]
                warnings.append('LME '+metal+' '+contract+': Bid above Ask, pair quarantined')
    result = list(rows.values())
    if len(result) < 12:
        warnings.append('LME Official incomplete: '+str(len(result))+'/12 source prices')
    return {'rows': result, 'warnings': warnings}


def _schema(cx):
    cx.execute('''CREATE TABLE IF NOT EXISTS lme_official_prices(
        instrument_id TEXT NOT NULL,market_date TEXT NOT NULL,metal TEXT NOT NULL,
        contract TEXT NOT NULL,side TEXT NOT NULL,value TEXT NOT NULL,unit TEXT NOT NULL,
        currency TEXT NOT NULL,price_type TEXT NOT NULL,is_settlement INTEGER NOT NULL,
        captured_at TEXT NOT NULL,source_url TEXT NOT NULL,raw_json TEXT NOT NULL,
        PRIMARY KEY(market_date,metal,contract,side))''')
    cx.execute('''CREATE TABLE IF NOT EXISTS lme_official_revisions(
        id INTEGER PRIMARY KEY,market_date TEXT NOT NULL,metal TEXT NOT NULL,contract TEXT NOT NULL,
        side TEXT NOT NULL,old_json TEXT NOT NULL,new_json TEXT NOT NULL,revised_at TEXT NOT NULL)''')


def save_rows(db_path, rows):
    checked = []
    for row in rows:
        row = {name: row[name] for name in COLUMNS}
        if (row['metal'] not in METALS or row['contract'] not in CONTRACTS or row['side'] not in ('Bid', 'Ask')
                or row['unit'] != 'USD/t' or row['currency'] != 'USD' or row['price_type'] != 'Official'
                or _number(str(row['value'])) is None or not _source_ok(row['source_url'])):
            raise ValueError('Invalid LME Official storage row')
        if date.fromisoformat(row['market_date']).isoformat() != row['market_date']:
            raise ValueError('Invalid LME source market date')
        if row['instrument_id'] != 'LME_'+METALS[row['metal']]+'_'+CONTRACTS[row['contract']]+'_'+row['side'].upper():
            raise ValueError('LME instrument identity mismatch')
        if bool(row['is_settlement']) != (row['contract'] == 'Cash' and row['side'] == 'Ask'):
            raise ValueError('LME settlement-side mismatch')
        checked.append(row)
    counts = dict(inserted=0, revised=0, unchanged=0)
    with closing(sqlite3.connect(db_path)) as cx:
        cx.row_factory = sqlite3.Row
        with cx:
            _schema(cx)
            # A partial DOM capture must not cross a previously trusted opposite
            # side. Validate the whole prospective batch before any price/audit
            # writes, preserving both cached facts if the merge is inconsistent.
            prospective = {}
            for row in checked:
                pair_key = tuple(row[name] for name in ('market_date', 'metal', 'contract'))
                if pair_key not in prospective:
                    prospective[pair_key] = {old['side']: Decimal(old['value']) for old in cx.execute(
                        'SELECT side,value FROM lme_official_prices WHERE market_date=? AND metal=? AND contract=?', pair_key)}
                prospective[pair_key][row['side']] = Decimal(row['value'])
            for pair_key, sides in prospective.items():
                if 'Bid' in sides and 'Ask' in sides and sides['Bid'] > sides['Ask']:
                    raise ValueError('LME '+ '/'.join(pair_key)+': merged Bid above Ask; entire batch rejected, cached source and revisions unchanged')
            for row in checked:
                key = tuple(row[name] for name in ('market_date', 'metal', 'contract', 'side'))
                old = cx.execute('SELECT * FROM lme_official_prices WHERE market_date=? AND metal=? AND contract=? AND side=?', key).fetchone()
                if old is not None and Decimal(old['value']) == Decimal(row['value']):
                    counts['unchanged'] += 1
                    continue
                if old is not None:
                    cx.execute('INSERT INTO lme_official_revisions(market_date,metal,contract,side,old_json,new_json,revised_at) VALUES(?,?,?,?,?,?,?)',
                               (*key, json.dumps(dict(old), ensure_ascii=False), json.dumps(row, ensure_ascii=False), row['captured_at']))
                    counts['revised'] += 1
                else:
                    counts['inserted'] += 1
                cx.execute('INSERT OR REPLACE INTO lme_official_prices('+','.join(COLUMNS)+') VALUES('+','.join('?' for _ in COLUMNS)+')',
                           tuple(row[name] for name in COLUMNS))
    return counts


def load_rows(db_path):
    if not Path(db_path).is_file():
        return []
    with closing(sqlite3.connect(db_path)) as cx:
        cx.row_factory = sqlite3.Row
        if not cx.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lme_official_prices'").fetchone():
            return []
        rows = [dict(row) for row in cx.execute('SELECT * FROM lme_official_prices ORDER BY market_date DESC,metal,contract,side')]
    for row in rows:
        row['is_settlement'] = bool(row['is_settlement'])
    return rows


def collect_and_save(driver, db_path, cancelled=lambda: False, logger=lambda message: None):
    result = dict(status='failed', rows=0, warnings=[])
    original = owned = None
    try:
        if cancelled():
            result['status'] = 'cancelled'
            return result
        original = driver.current_window_handle
        driver.switch_to.new_window('tab')
        owned = driver.current_window_handle
        if owned == original:
            owned = None
            raise RuntimeError('LME owned tab was not created')
        if cancelled():
            result['status'] = 'cancelled'
            return result
        driver.get(SOURCE_URL)
        deadline = time.monotonic()+POLL_SECONDS
        while True:
            if cancelled():
                result['status'] = 'cancelled'
                return result
            if not _source_ok(driver.current_url):
                raise ValueError('LME Official unexpected redirect/source identity')
            parsed = parse(driver.page_source, source_url=driver.current_url)
            if len(parsed['rows']) == 12 or time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        if cancelled():
            result['status'] = 'cancelled'
            return result
        result['warnings'] = parsed['warnings']
        if parsed['rows']:
            result['storage'] = save_rows(db_path, parsed['rows'])
            result['rows'] = len(parsed['rows'])
            result['status'] = 'complete' if len(parsed['rows']) == 12 else 'partial'
        logger('LME Official: '+result['status']+' '+str(result['rows'])+'/12')
    except Exception as exc:
        result['status'] = 'failed'
        result['warnings'].append('LME Official: '+str(exc))
    finally:
        try:
            if owned is not None and owned in driver.window_handles:
                driver.switch_to.window(owned)
                driver.close()
        except Exception as exc:
            result['status'] = 'failed'
            result['warnings'].append('LME owned-tab cleanup failed: '+str(exc))
        try:
            if original is not None and original in driver.window_handles:
                driver.switch_to.window(original)
        except Exception as exc:
            result['status'] = 'failed'
            result['warnings'].append('LME original-tab restore failed: '+str(exc))
    return result
