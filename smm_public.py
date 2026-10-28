"""Three public SMM homepage quotes only. No private API or locked history.

Homepage USD/tonne quotes keep their source date and unspecified tax basis.
Nickel equivalent is a user-defined derived value, never a nickel spot quote.
"""
from contextlib import closing
from datetime import datetime
from decimal import Decimal, localcontext
import json
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urljoin, urlsplit
from naver_markets import DOM, Node, KST

SOURCE_URL='https://www.metal.com/ko'
TARGETS={
    'SMM-Li-LC-001':('전지급 탄산리튬','리튬','lithium','201102250059'),
    'SMM-NI-NC-001':('배터리급 황산니켈','니켈','nickel','201908270001'),
    'SMM-CO-CM-001':('중국 코발트 메탈','코발트','cobalt','201102250375'),
}
COLUMNS=('code','market_date','value','change','unit','currency','captured_at','source_url','assessment_url','status','raw_json')
NUMBER=r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?'


def _text(value):
    return re.sub(r'\s+',' ',value.text()).strip()


def _decimal_text(value):
    text=format(value,'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def nickel_equivalent(value):
    with localcontext() as ctx:
        ctx.prec=40
        number=Decimal(str(value))
        if not number.is_finite() or number<0:raise ValueError('Invalid sulphate quote')
        return _decimal_text(number/Decimal('0.2232'))


def source_ok(url, *, homepage=True):
    try:
        p=urlsplit(url)
        return (p.scheme=='https' and p.hostname in ('www.metal.com','metal.com')
            and not p.username and not p.password and p.port in (None,443)
            and (not homepage or bool(re.fullmatch(r'/(?:[a-z]{2}/?)?',p.path))))
    except (TypeError,ValueError):return False


def parse(html, *, captured_at=None,source_url=SOURCE_URL):
    rows={};conflicts=set();warnings=[]
    if not source_ok(source_url):return dict(rows=[],warnings=['SMM source URL mismatch'])
    try:
        captured=datetime.fromisoformat(str(captured_at)) if captured_at else datetime.now(KST)
        if captured.tzinfo is None:raise ValueError('timezone required')
    except (TypeError,ValueError):return dict(rows=[],warnings=['SMM capture timezone missing/invalid'])
    for node in DOM(html).root.walk():
        if node.tag!='tr':continue
        cells=[c for c in node.children if isinstance(c,Node) and c.tag=='td']
        if len(cells)!=6:continue
        codes=[code for code in TARGETS if re.search(r'(?<![A-Za-z0-9-])'+re.escape(code)+r'(?![A-Za-z0-9-])',_text(cells[1]),re.I)]
        if len(codes)!=1:continue
        code=codes[0];name,group,category,key=TARGETS[code]
        links=[c.attrs.get('href','') for c in cells[1].walk() if c.tag=='a']
        href=urljoin(source_url,links[0]) if len(links)==1 else ''
        path=urlsplit(href).path
        if (not source_ok(href,homepage=False) or not re.fullmatch(r'/(?:[a-z]{2}/)?'+category+'/'+key+'/?',path,re.I)
                or node.attrs.get('data-row-key',key)!=key):
            warnings.append(code+': product link/identity mismatch');continue
        match=re.fullmatch('('+NUMBER+r')\s*USD/(?:tonne|t)',_text(cells[2]))
        delta=re.fullmatch(r'([+\-−]?\s*'+NUMBER+')',_text(cells[3]))
        try:
            day=datetime.strptime(_text(cells[5]),'%m/%d/%Y').date()
            if day>captured.astimezone(KST).date() or not match or not delta:raise ValueError('date/unit/value')
            number=Decimal(match[1].replace(',',''))
            if number<=0:raise ValueError('positive price required')
            change=Decimal(delta[1].replace(',','').replace(' ','').replace('−','-'))
        except (ValueError,ArithmeticError):
            warnings.append(code+': public row date/unit/value missing or invalid');continue
        row=dict(code=code,market_date=day.isoformat(),value=_decimal_text(number),change=_decimal_text(change),
            unit='USD/t',currency='USD',captured_at=captured.isoformat(),source_url=source_url,assessment_url=href,
            status='observed',raw_json=json.dumps(dict(displayed_average=_text(cells[2]),displayed_change=_text(cells[3]),
                displayed_date=_text(cells[5]),tax_basis='unspecified',kind='public_homepage_average'),ensure_ascii=False))
        identity=(code,day.isoformat())
        if identity in rows and (rows[identity]['value'],rows[identity]['change'])!=(row['value'],row['change']):conflicts.add(identity)
        rows[identity]=row
    for identity in conflicts:
        rows[identity].update(value=None,change=None,status='conflict')
        warnings.append(identity[0]+': conflicting public rows quarantined')
    missing=set(TARGETS)-{r['code'] for r in rows.values()}
    if missing:warnings.append('SMM missing public quotes: '+', '.join(sorted(missing)))
    return dict(rows=list(rows.values()),warnings=warnings)


def checked_row(original):
    row={name:original[name] for name in COLUMNS}
    if row['code'] not in TARGETS or row['unit']!='USD/t' or row['currency']!='USD' or not source_ok(row['source_url']):
        raise ValueError('SMM storage identity/unit/source mismatch')
    stamp=datetime.fromisoformat(row['captured_at'])
    day=datetime.strptime(row['market_date'],'%Y-%m-%d').date()
    if stamp.tzinfo is None or day>stamp.astimezone(KST).date():raise ValueError('SMM invalid source date/timezone')
    _,_,category,key=TARGETS[row['code']]
    if not source_ok(row['assessment_url'],homepage=False) or not re.fullmatch(r'/(?:[a-z]{2}/)?'+category+'/'+key+'/?',urlsplit(row['assessment_url']).path,re.I):
        raise ValueError('SMM product source mismatch')
    if row['status']=='conflict':
        if row['value'] is not None or row['change'] is not None:raise ValueError('SMM conflicted quote must be blank')
    elif row['status']=='observed':
        value,delta=Decimal(str(row['value'])),Decimal(str(row['change']))
        if not value.is_finite() or value<=0 or not delta.is_finite():raise ValueError('SMM invalid number')
    else:raise ValueError('SMM unknown status')
    return row


def save_rows(db_path,rows):
    rows=[checked_row(r) for r in rows];counts=dict(inserted=0,revised=0,unchanged=0)
    batch={}
    for row in rows:
        key=tuple(row[k] for k in ('code','market_date','unit'))
        if key in batch and any(batch[key][k]!=row[k] for k in ('value','change','status')):
            raise ValueError('SMM conflicting duplicate storage batch')
        batch[key]=row
    rows=list(batch.values())
    with closing(sqlite3.connect(db_path)) as cx,cx:
        cx.row_factory=sqlite3.Row
        cx.execute('''CREATE TABLE IF NOT EXISTS smm_observations(code TEXT NOT NULL,market_date TEXT NOT NULL,
            value TEXT,change TEXT,unit TEXT NOT NULL,currency TEXT NOT NULL,captured_at TEXT NOT NULL,
            source_url TEXT NOT NULL,assessment_url TEXT NOT NULL,status TEXT NOT NULL,raw_json TEXT NOT NULL,
            PRIMARY KEY(code,market_date,unit))''')
        cx.execute('CREATE TABLE IF NOT EXISTS smm_revisions(id INTEGER PRIMARY KEY,old_json TEXT,new_json TEXT,revised_at TEXT)')
        for row in rows:
            key=tuple(row[k] for k in ('code','market_date','unit'))
            old=cx.execute('SELECT * FROM smm_observations WHERE code=? AND market_date=? AND unit=?',key).fetchone()
            if old and all(old[k]==row[k] for k in ('value','change','status','currency','assessment_url')):
                counts['unchanged']+=1;continue
            if old:
                cx.execute('INSERT INTO smm_revisions(old_json,new_json,revised_at) VALUES(?,?,?)',
                    (json.dumps(dict(old),ensure_ascii=False),json.dumps(row,ensure_ascii=False),row['captured_at']))
                counts['revised']+=1
            else:counts['inserted']+=1
            cx.execute('INSERT OR REPLACE INTO smm_observations('+','.join(COLUMNS)+') VALUES('+','.join('?' for _ in COLUMNS)+')',tuple(row[k] for k in COLUMNS))
    return counts


def collect_and_save(driver,db_path,cancelled=lambda:False,logger=lambda _:None):
    result=dict(status='failed',rows=0,warnings=[]);original=owned=None
    try:
        if cancelled():return dict(result,status='cancelled')
        original=driver.current_window_handle;driver.switch_to.new_window('tab');owned=driver.current_window_handle
        if owned==original:owned=None;raise RuntimeError('SMM owned tab was not created')
        driver.get(SOURCE_URL);deadline=time.monotonic()+3
        while True:
            if cancelled():return dict(result,status='cancelled')
            if not source_ok(driver.current_url):raise ValueError('SMM unexpected redirect')
            parsed=parse(driver.page_source,source_url=driver.current_url)
            if len(parsed['rows'])==3 or time.monotonic()>=deadline:break
            time.sleep(.1)
        result['warnings']=parsed['warnings']
        if cancelled():return dict(result,status='cancelled')
        if parsed['rows']:
            result['storage']=save_rows(db_path,parsed['rows']);result['rows']=len(parsed['rows'])
            result['status']='complete' if len(parsed['rows'])==3 and not parsed['warnings'] else 'partial'
        logger('SMM public: '+result['status']+' '+str(result['rows'])+'/3')
    except Exception as exc:result['warnings'].append('SMM public: '+str(exc))
    finally:
        try:
            if owned is not None and owned in driver.window_handles:driver.switch_to.window(owned);driver.close()
        except Exception as exc:result['status']='failed';result['warnings'].append('SMM owned-tab cleanup: '+str(exc))
        try:
            if original is not None and original in driver.window_handles:driver.switch_to.window(original)
        except Exception as exc:result['status']='failed';result['warnings'].append('SMM original-tab restore: '+str(exc))
    return result


def export_csv(db_path,output):
    """Raw quotes only; derived Ni series remain explicitly separate in reports."""
    import csv
    from FastmarketsCollector_v3_4 import atomic_text
    with closing(sqlite3.connect(db_path)) as cx:
        cx.row_factory=sqlite3.Row
        if not cx.execute("SELECT 1 FROM sqlite_master WHERE name='smm_observations'").fetchone():return None
        rows=[dict(row) for row in cx.execute('SELECT * FROM smm_observations ORDER BY market_date,code')]
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with atomic_text(output) as stream:
        writer=csv.writer(stream);writer.writerow(COLUMNS)
        writer.writerows(tuple(row[k] for k in COLUMNS) for row in rows)
    return str(output)
