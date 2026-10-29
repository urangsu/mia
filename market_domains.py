"""Additive logical domains and explicitly estimated prior values, never observations."""
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
import json

SOURCES={'prices':'metal','lme_official_prices':'metal','smm_observations':'metal',
         'fx_rates':'market','market_indicators':'market','equity_rank_snapshots':'stock',
         'fdr_observations':'market'}
RATES=(('US10Y','미국 국채 10년'),('KR10Y','한국 국고채 10년'),
       ('KR3Y','한국 국고채 3년'),('KR_CORP_AA_3Y','회사채 3년 AA−'))

def initialize(cx):
    """Retain every source table; views carry complete source-row JSON."""
    existing={r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    parts={d:[] for d in ('market','metal','stock')}
    for table,domain in SOURCES.items():
        if table not in existing:continue
        columns=[r[1] for r in cx.execute('PRAGMA table_info('+table+')')]
        quote=lambda s:'"'+s.replace('"','""')+'"'
        field=lambda candidates:next((quote(c) for c in candidates if c in columns),'NULL')
        code=field(('instrument_id','symbol','stock_code','code','currency'))
        day=field(('market_date','assessment_date','quote_date','date'))
        payload='json_object('+','.join("'"+c.replace("'","''")+"',"+quote(c) for c in columns)+')'
        select=f"SELECT '{table}' AS source_table,{code} AS instrument_id,{day} AS observation_date,{payload} AS raw_json FROM {table}"
        if table=='fdr_observations':
            parts['stock'].append(select+f" WHERE {code} GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]'")
            parts['market'].append(select+f" WHERE {code} NOT GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]'")
        else:parts[domain].append(select)
    for domain,queries in parts.items():
        cx.execute('DROP VIEW IF EXISTS domain_'+domain)
        cx.execute('CREATE VIEW domain_'+domain+' AS '+(' UNION ALL '.join(queries) if queries else
            'SELECT NULL AS source_table,NULL AS instrument_id,NULL AS observation_date,NULL AS raw_json WHERE 0'))
    cx.execute('''CREATE TABLE IF NOT EXISTS prior_estimates(
        domain TEXT NOT NULL,code TEXT NOT NULL,prior_date TEXT NOT NULL,basis_date TEXT NOT NULL,
        unit TEXT NOT NULL,value TEXT NOT NULL,status TEXT NOT NULL,evidence_json TEXT NOT NULL,
        PRIMARY KEY(domain,code,prior_date,basis_date,unit,evidence_json))''')

def estimate_prior(value,change,*,kind):
    try:
        value,change=Decimal(str(value)),Decimal(str(change))
        if not value.is_finite() or not change.is_finite():raise ValueError('유한 수치 필요')
        with localcontext() as ctx:
            ctx.prec=40
            if kind=='pct':
                denominator=1+change/100
                if denominator<=0:raise ValueError('등락률 분모 오류')
                result=value/denominator
            elif kind=='bp':result=value-change/100
            elif kind=='absolute':result=value-change
            else:raise ValueError('역산 종류 오류')
            return format(result,'f')
    except InvalidOperation as exc:raise ValueError('숫자 형식 오류') from exc

def save_estimate(cx,*,domain,code,current_date,prior_date,value,change,kind,unit,source,basis_confirmed=False):
    if not basis_confirmed or domain not in ('market','metal','stock'):
        raise ValueError('동일 종목·단위·비교 기준 확인 필요')
    if date.fromisoformat(prior_date)>=date.fromisoformat(current_date):raise ValueError('명시적 직전 기준일 필요')
    result=estimate_prior(value,change,kind=kind)
    evidence=json.dumps(dict(current_value=str(value),change=str(change),kind=kind,source=source,
        limitation='Rounded inputs may imply an interval; not an observed close'),sort_keys=True)
    cx.execute('INSERT OR IGNORE INTO prior_estimates VALUES(?,?,?,?,?,?,?,?)',
        (domain,code,prior_date,current_date,unit,result,'derived_estimated',evidence))
    return result

def rate_cards(context):
    rows=context.tables.get('보고용_시장지표',())
    records=[dict(zip(rows[0],row)) for row in rows[1:]] if rows else []
    cards=[]
    for code,label in RATES:
        matches=[r for r in records if r.get('지표')==code and r.get('단위')=='%']
        latest=max((str(r.get('시장일') or '') for r in matches),default='')
        matches=[r for r in matches if str(r.get('시장일') or '')==latest]
        r=matches[0] if len(matches)==1 else {}
        def number(key):
            try:
                v=Decimal(str(r.get(key)))
                return v if v.is_finite() else None
            except InvalidOperation:return None
        value,change=number('수치'),number('전일대비')
        cards.append(dict(code=code,label=label,value=f'{value:.3f}%' if value is not None else '—',
            change=f'{change*100:+.1f}bp' if change is not None else '',
            css='positive' if change is not None and change>0 else 'negative' if change is not None and change<0 else '',
            note='' if value is not None else '자료 없음'))
    return cards
