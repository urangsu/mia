# -*- coding: utf-8 -*-
"""서울외국환중개: FMB 전용 Chrome(:9444)의 별도 탭에서 조회 → SQLite 누적.

Chrome(:9222), 관리자 Edge(:9337)는 절대 변경/제어하지 않는다. 페이지 DOM 검증 전 날짜 필드를 추측하지 않는다.
실제 Windows 사이트 접속/수집은 개발 환경에서 검증할 수 없으므로
초기 실행은 반드시 --fx-once 로그와 원본 화면 대조가 필요하다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json
import re
import os
import sqlite3
import tempfile
from contextlib import closing
from urllib.parse import urlsplit

SMBS_URL = 'http://www.smbs.biz/ExRate/StdExRate.jsp'
FX_CODES = ('USD', 'CNH', 'JPY', 'EUR')
QUOTE_UNITS = {'USD': 1, 'CNH': 1, 'JPY': 100, 'EUR': 1}
DATE_RX = re.compile(r'(?<!\d)(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})(?!\d)')
NUM_RX = re.compile(r'(?<![\d,])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\d)')


class FXPageError(RuntimeError):
    pass


@dataclass(frozen=True)
class FXQuote:
    quote_date: str
    currency: str
    rate: str
    difference: str
    unit: int
    source: str = '서울외국환중개'


def _unique_visible_number(value: str, kind: str) -> Decimal:
    """동일 문자열 중복 렌더링은 허용, 서로 다른 수치가 섞이면 중단."""
    candidates = [m.group(0) for m in NUM_RX.finditer(value or '')]
    try:
        nums = {Decimal(x.replace(',', '')) for x in candidates}
    except InvalidOperation as exc:
        raise FXPageError(f'{kind} 숫자 해석 실패') from exc
    if len(nums) != 1:
        raise FXPageError(f'{kind}: 숫자 추출이 모호합니다. {value!r}')
    return nums.pop()


def decode_date(text: str) -> str:
    found = {f'{int(y):04d}-{int(m):02d}-{int(d):02d}' for y,m,d in DATE_RX.findall(text or '')}
    if len(found) != 1:
        raise FXPageError(f'고시일 형식이 모호합니다: {text!r}')
    value = next(iter(found))
    try: date.fromisoformat(value)
    except ValueError as exc: raise FXPageError(f'잘못된 고시일: {value}') from exc
    return value


def decode_difference(text: str, image_alt: str, image_classes: str = '') -> Decimal:
    amount = _unique_visible_number(text, '전일대비')
    if amount == 0: return Decimal('0')
    icons = ((image_alt or '')+' '+(image_classes or '')).lower()
    up = '상승' in icons or 'ico_up' in icons or 'ico-up' in icons
    down = '하락' in icons or 'ico_down' in icons or 'ico-down' in icons
    if up == down:
        # Text-only explicit sign is enough only when it unambiguously starts with it.
        t=(text or '').strip()
        if t.startswith('+'):return abs(amount)
        if t.startswith('-') or t.startswith('−'):return -abs(amount)
        raise FXPageError('전일대비 상승/하락 방향을 확인하지 못했습니다. 양수로 추정하지 않습니다.')
    return abs(amount) if up else -abs(amount)


def parse_row(cells: list[str], *, currency: str, alt='', classes='') -> FXQuote:
    """실제 표시 텍스트 10칸을 받아 앞 4칸만 검증. 나머지 0은 수집하지 않음."""
    if currency not in FX_CODES:raise FXPageError('허용하지 않은 통화코드')
    if len(cells) < 4: raise FXPageError('일별 매매기준율 열 4개 미만')
    day=decode_date(cells[0])
    name=' '.join((cells[1] or '').split()).upper()
    if currency not in name:
        raise FXPageError(f'요청통화({currency})와 결과통화({name}) 불일치')
    amount=_unique_visible_number(cells[2], '매매기준율')
    if amount <= 0:
        raise FXPageError('매매기준율이 0 또는 음수 — 아직 미고시거나 데이터 오류')
    if day > date.today().isoformat():
        raise FXPageError('미래 고시일은 저장하지 않습니다')
    diff=decode_difference(cells[3],alt,classes)
    return FXQuote(day,currency,str(amount),str(diff),QUOTE_UNITS[currency])


def parse_table_records(records: list[dict], currency: str) -> list[FXQuote]:
    """날짜 시작 행만 선택. 날짜가 맞는 행의 파싱 실패는 무시하지 않고 중단."""
    result={}
    matched=0
    for raw in records:
        cells=raw.get('cells') or []
        if not cells or not DATE_RX.search(cells[0]):continue
        matched += 1
        item=parse_row(cells,currency=currency,alt=raw.get('alt',''),classes=raw.get('classes',''))
        if item.quote_date in result and item != result[item.quote_date]:
            raise FXPageError(f'{currency} {item.quote_date} 중복 자료 값 불일치')
        result[item.quote_date]=item
    if not matched:raise FXPageError(f'{currency}: 고시일이 포함된 표를 발견하지 못했습니다. DOM 또는 휴장일 여부 확인 필요')
    if not result:raise FXPageError(f'{currency}: 유효 고시 없음')
    return sorted(result.values(),key=lambda q:q.quote_date)


def _safe_url(url: str) -> bool:
    p=urlsplit(url)
    return p.scheme in ('http','https') and (p.hostname or '').lower() in ('smbs.biz','www.smbs.biz') and p.path.endswith('/ExRate/StdExRate.jsp')


def _search_form_context(driver, currency_select):
    """실제 DOM에서 select 조상 form을 찾는다. 임의 frm_SearchDate 하드코딩 금지."""
    from selenium.common.exceptions import NoSuchElementException
    try:return currency_select.find_element('xpath','ancestor::form[1]')
    except NoSuchElementException:return driver.find_element('tag name','body')


def _locate_search_control(context):
    """명확하게 식별되는 '조회/검색' 컨트롤만 사용, 마지막 링크로 추측 금지."""
    from selenium.webdriver.common.by import By
    candidates=[]
    for css in ("input[type='submit']", "input[type='image']", 'button', 'a', "img[alt]"):
        for el in context.find_elements(By.CSS_SELECTOR,css):
            try:
                if not el.is_displayed():continue
                label=' '.join((el.text or '',el.get_attribute('value') or '',el.get_attribute('alt') or '',el.get_attribute('title') or '')).strip()
                if re.search(r'(조회하기|검색하기|조회|검색)',label):
                    # If image sits within clickable element, click its parent instead.
                    if el.tag_name.lower()=='img':
                        parent=el.find_element(By.XPATH,'..')
                        if parent.tag_name.lower() in ('a','button'):
                            el=parent
                    if el.id not in {x.id for x in candidates}:
                        candidates.append(el)
            except Exception:continue
    if len(candidates)!=1:
        raise FXPageError(f'조회 버튼 식별 실패: 후보 {len(candidates)}개. 정확한 DOM 확인 필요')
    return candidates[0]


def collect_rates(*, start=None, end=None, headless=False, logger=print, driver=None) -> tuple[list[FXQuote],dict]:
    """Use verified caller-owned :9444 Chrome session, but only our temporary tab.

    Standalone calls MUST supply a preverified driver: never spawn an additional
    uncontrolled browser nor accidentally attach to ports 9222/9337.
    """
    if driver is None:
        raise FXPageError('환율 수집은 검증된 Chrome 9444 드라이버가 필요합니다. FMB 프로그램에서 실행하세요.')
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait, Select
    original_handle=driver.current_window_handle
    if original_handle not in driver.window_handles:
        raise FXPageError('기존 Chrome 탭 핸들을 확인할 수 없습니다')
    # The browser is shared, but only this newly-created tab is owned by FX.
    driver.switch_to.new_window('tab')
    fx_handle=driver.current_window_handle
    quotes=[];report={'started_at':datetime.now().isoformat(),'source':SMBS_URL,'codes':{},'warnings':[]}
    try:
        driver.set_page_load_timeout(25)
        driver.get(SMBS_URL)
        if not _safe_url(driver.current_url):
            raise FXPageError('SMBS 사이트 외 URL로 이동했습니다. 수집 중단')
        wait=WebDriverWait(driver,15)
        for code in FX_CODES:
            try:
                selector=wait.until(lambda d: d.find_element(By.CSS_SELECTOR,'select[name="tongwha_code"]'))
                wait.until(lambda _:selector.is_displayed())
                existing={o.get_attribute('value') for o in selector.find_elements(By.TAG_NAME,'option')}
                if code not in existing:
                    raise FXPageError(f'{code} 옵션이 DOM에 없습니다. DOM 생성 여부를 확인하세요.')
                form=_search_form_context(driver,selector)
                # Arbitrary start/end fields must not be silently guessed.
                if start is not None or end is not None:
                    fields=[el for el in form.find_elements(By.CSS_SELECTOR,'input[type="text"]') if el.is_displayed() and el.is_enabled()]
                    if len(fields)!=2 or not(start and end):
                        raise FXPageError(f'{code}: 기간 필드 2개를 확인할 수 없어 범위 조회 중단')
                    for field,val in zip(fields,(start,end)):
                        field.clear();field.send_keys(val)
                        if field.get_attribute('value').replace('.','').replace('-','')!=val.replace('.','').replace('-',''):
                            raise FXPageError('날짜 입력 검증 실패')
                Select(selector).select_by_value(code)
                # Some SMBS pages rerender the form when currency changes. Reacquire DOM.
                selector=wait.until(lambda d:d.find_element(By.CSS_SELECTOR,'select[name="tongwha_code"]'))
                if Select(selector).first_selected_option.get_attribute('value')!=code:
                    raise FXPageError('통화 선택 확인 실패')
                form=_search_form_context(driver,selector)
                search=_locate_search_control(form)
                search.click()
                # Do not trust networkidle / fixed sleep. Wait for matching published rows.
                def extract(d):
                    try:
                        entries=d.execute_script('''
                        const rows=[];
                        for (const tr of document.querySelectorAll('table tr')) {
                          const tds=[...tr.querySelectorAll(':scope > td')];
                          if(tds.length<4) continue;
                          const txt=td=>{
                            const nodes=[...td.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE)
                              .map(n=>(n.textContent||'').trim()).filter(Boolean);
                            const nested=td.querySelector('.won3');
                            return nodes.join(' ') || (nested ? nested.innerText.trim() : td.innerText.trim());
                          };
                          const alt=tds[3].querySelector('img[alt]')?.getAttribute('alt')||'';
                          const cls=tds[3].querySelector('.ico')?.className||'';
                          rows.push({cells:tds.map(txt),alt,classes:cls});
                        }
                        return rows;
                        ''')
                        if any(len(x['cells'])>=4 and code in x['cells'][1] and DATE_RX.search(x['cells'][0]) for x in entries):
                            return entries
                    except Exception:return False
                    return False
                records=wait.until(extract)
                parsed=parse_table_records(records,code)
                if start is not None:
                    lower=date.fromisoformat(start.replace('.','-'))
                    upper=date.fromisoformat(end.replace('.','-'))
                    if not any(lower.isoformat()<=r.quote_date<=upper.isoformat() for r in parsed):
                        raise FXPageError('입력한 조회기간에 해당하는 환율이 없습니다. 검색 동작/고시일 확인 필요')
                    parsed=[r for r in parsed if lower.isoformat()<=r.quote_date<=upper.isoformat()]
                quotes.extend(parsed)
                report['codes'][code]={'count':len(parsed),'first':parsed[0].quote_date,'last':parsed[-1].quote_date}
                logger(f'SMBS {code} {len(parsed)}건 ({parsed[0].quote_date} ~ {parsed[-1].quote_date})')
            except Exception as exc:
                report['warnings'].append(f'{code}: {type(exc).__name__}: {str(exc)[:220]}')
                logger(f'SMBS {code} 수집 보류: {type(exc).__name__}')
        if not quotes:
            report['warnings'].append('4개 통화 모두 수집 실패: 데이터 저장 및 Excel 갱신하지 않음')
        return quotes,report
    finally:
        # NEVER driver.quit(): would disconnect or close unrelated user tabs.
        # Close only the FX-created tab and restore the caller's original tab.
        try:
            if fx_handle in driver.window_handles:
                driver.switch_to.window(fx_handle)
                driver.close()
        finally:
            if original_handle in driver.window_handles:
                driver.switch_to.window(original_handle)


def save_rates(db_path: Path, quotes: list[FXQuote]) -> dict:
    """연도 제한 없이 UPSERT; 정정 시 변경 로그 별도 보관."""
    if not quotes:return {'inserted':0,'updated':0,'unchanged':0}
    db_path=Path(db_path)
    db_path.parent.mkdir(parents=True,exist_ok=True)
    counts={'inserted':0,'updated':0,'unchanged':0}
    with closing(sqlite3.connect(db_path,timeout=30)) as cx:
        cx.execute('PRAGMA busy_timeout=30000')
        cx.executescript('''
          CREATE TABLE IF NOT EXISTS fx_rates (
            source TEXT NOT NULL, currency TEXT NOT NULL, quote_date TEXT NOT NULL,
            quote_unit INTEGER NOT NULL, rate TEXT NOT NULL, difference TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            PRIMARY KEY(source,currency,quote_date,quote_unit)
          );
          CREATE TABLE IF NOT EXISTS fx_rate_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT,currency TEXT,quote_date TEXT,
            prior_rate TEXT,prior_difference TEXT,new_rate TEXT,new_difference TEXT,changed_at TEXT
          );
        ''')
        now=datetime.now().isoformat(timespec='seconds')
        for q in quotes:
            found=cx.execute('SELECT rate,difference FROM fx_rates WHERE source=? AND currency=? AND quote_date=? AND quote_unit=?',
                             (q.source,q.currency,q.quote_date,q.unit)).fetchone()
            if found and all(Decimal(str(a)) == Decimal(str(b)) for a,b in zip(found,(q.rate,q.difference))):
                counts['unchanged']+=1;continue
            if found:
                cx.execute('INSERT INTO fx_rate_revisions(source,currency,quote_date,prior_rate,prior_difference,new_rate,new_difference,changed_at) VALUES(?,?,?,?,?,?,?,?)',
                           (q.source,q.currency,q.quote_date,found[0],found[1],q.rate,q.difference,now))
                counts['updated']+=1
            else:counts['inserted']+=1
            cx.execute('INSERT INTO fx_rates(source,currency,quote_date,quote_unit,rate,difference,collected_at) VALUES(?,?,?,?,?,?,?) '
                       'ON CONFLICT(source,currency,quote_date,quote_unit) DO UPDATE SET rate=excluded.rate,difference=excluded.difference,collected_at=excluded.collected_at',
                       (q.source,q.currency,q.quote_date,q.unit,q.rate,q.difference,now))
        cx.commit()
    return counts


def load_rates(db_path: Path) -> list[FXQuote]:
    if not Path(db_path).exists():return []
    with closing(sqlite3.connect(db_path)) as cx:
        try:
            return [FXQuote(date_,code,rate,diff,unit,source) for source,code,date_,unit,rate,diff
                    in cx.execute('SELECT source,currency,quote_date,quote_unit,rate,difference FROM fx_rates ORDER BY quote_date,currency')]
        except sqlite3.OperationalError as exc:
            if 'no such table' in str(exc):return []
            raise


# Compact report labels are independent of the full Fastmarkets description.
# The authoritative mapping remains in 가격열설정; never infer EU/KR from a widget nickname.
FMB_SHORT_NAMES = {
    # Defined from actual Fastmarkets descriptions; location and benchmark matter.
    'MB-LI-0029': 'LC',                    # Li2CO3 battery grade CIF CJK
    'MB-LI-0033': 'LiOH',                  # LiOH.H2O battery grade CIF CJK
    'MB-CO-0005': 'Co',              # standard grade Rotterdam $/lb
    'MB-MN-0001': 'Mn(전해)',              # electrolytic flake (NOT MnSO4)
    'MB-BMS-0001': 'BM(NCM Ni) KR',       # nickel payable South Korea
    'MB-BMS-0002': 'BM(NCM Co) KR',
    'MB-BMS-0003': 'BM(NCM Li) KR',
    'MB-BMS-0004': 'BM(NCM Ni) EU',       # exw Europe
    'MB-BMS-0006': 'BM(LCO Co) EU',
    'MB-BMS-0010': 'BM(LCO Co) KR',
    'MB-BMS-0011': 'BM(LCO Li) KR',
    'MB-BMS-0012': 'BM(NCM 고Co) KR',     # inferred $/tonne, NOT % payable
}

def report_series_label(key: str) -> str:
    if key.startswith('FX_'):
        text=key.replace('FX_', '')
        if '_DIFF_KRW_per_' in text:
            cc, unit=text.split('_DIFF_KRW_per_',1)
            return f'{cc} 전일대비' + ('(100)' if unit=='100' else '')
        cc,unit=text.split('_KRW_per_',1)
        return cc + ('(100)' if unit=='100' else '')
    if key.startswith('FMB|'):
        _,code,unit,mode,field=key.split('|',4)
        base=FMB_SHORT_NAMES.get(code,code)
        mod='(전망)' if mode=='Forecast' else ('(월평균)' if mode=='Monthly Average' else '')
        unit_suffix=''  # Units retained in 가격열설정, no repeated wide English header.
        kind={'MID':'','LOW':'(하한)','HIGH':'(상한)'}.get(field,'('+field+')')
        return base+mod+kind+unit_suffix
    return key


def report_series_source(key: str) -> str:
    return 'SMBS' if key.startswith('FX_') else 'FMB'


def prepare_excel_series(fmb_prices, fx_quotes, *, issues=None):
    """Condense widget-specific observations into stable product/field columns.

    RawData retains every view. When two views claim different same-date price values,
    only trust a value demonstrably bounded by the very same view's low/high; otherwise
    quarantine that daily cell instead of silently guessing or creating duplicate columns.
    This is intentionally NOT a DB migration.
    """
    from collections import defaultdict, Counter
    issues=issues if issues is not None else []
    values=defaultdict(dict)
    candidates=defaultdict(list)
    for p in fmb_prices:
        if p.price_mode not in ('Actual','Unspecified','Forecast') or p.period_label:
            continue
        for field in ('mid','low','high'):
            val=getattr(p,field)
            if val is None:continue
            try:number=Decimal(str(val))
            except (InvalidOperation,ValueError):continue
            if not number.is_finite():continue
            key=f'FMB|{p.symbol}|{p.unit}|{p.price_mode}|{field.upper()}'
            bounded=False
            if p.low is not None and p.high is not None:
                try:
                    low=Decimal(str(p.low));high=Decimal(str(p.high))
                    bounded=low<=number<=high and low<=high
                except (InvalidOperation,ValueError):pass
            candidates[(p.date,key)].append((number,bounded,p.view_key))
    for (dt,key),samples in candidates.items():
        uniques={num for num,_,_ in samples}
        if len(uniques)==1:
            values[dt][key]=float(next(iter(uniques)));continue
        issues.append(f'{dt} {key}: 서로 다른 뷰 가격 충돌 {sorted(str(v) for v in uniques)}; 일별시세 반영 보류')
    fx_candidates=defaultdict(list)
    for q in fx_quotes:
        fx_candidates[(q.quote_date,q.currency,q.unit)].append(q)
    for (dt,currency,unit),samples in fx_candidates.items():
        key=f'FX_{currency}_KRW_per_{unit}'
        try:
            pairs={(Decimal(str(q.rate)),Decimal(str(q.difference))) for q in samples}
            finite=all(rate.is_finite() and diff.is_finite() for rate,diff in pairs)
        except (InvalidOperation,ValueError):pairs=set();finite=False
        if len(pairs)!=1 or not finite:
            sources=', '.join(sorted({q.source for q in samples}))
            issues.append(f'{dt} {key}: 환율 출처 충돌 또는 비정상 수치 ({sources}); 매매기준율·전일대비 반영 보류')
            continue
        rate,difference=next(iter(pairs))
        values[dt][key]=float(rate)
        values[dt][f'FX_{currency}_DIFF_KRW_per_{unit}']=float(difference)
    return values

def add_summary_sheets(wb, fmb_prices, fx_quotes):
    """Non-Windows plain-XLSX fallback; same Mid-only two-row report as COM.

    This is used for offline/plain workbooks only. Windows corporate DRM files
    must always use Excel COM from excel_secure.write_com_sheets.
    """
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from excel_secure import make_sheets, order_managed_columns, merge_external_columns

    prior_keys=[]; aliases={}; owned_names=set()
    if '가격열설정' in wb:
        for k, name, *_ in wb['가격열설정'].iter_rows(min_row=2,max_col=3,values_only=True):
            if isinstance(k,str) and k:
                prior_keys.append(k)
                owned_names.add(report_series_label(k))
                if isinstance(name,str) and name.strip():
                    aliases[k]=name.strip()
                    owned_names.add(name.strip())
    old_data={}
    for name in ('일별시세','월별시세','월별건수'):
        if name in wb:
            old_data[name]=[tuple(row) for row in wb[name].iter_rows(values_only=True)]

    sheets={name:rows for name,rows in make_sheets(fmb_prices,[],fx_quotes,aliases=aliases).items()
            if name in ('일별시세','월별시세','월별건수','가격열설정')}
    order_managed_columns(sheets,prior_keys,aliases)
    for name,rows in old_data.items():
        sheets[name]=merge_external_columns(sheets[name],rows,owned_names)
    for name in sheets:
        if name in wb:
            wb.remove(wb[name])
    for name,rows in sheets.items():
        ws=wb.create_sheet(name)
        for row in rows:
            ws.append(row)
        ws.freeze_panes=('B3' if name!='가격열설정' else 'B2')
        ws.sheet_view.showGridLines=False
        for cell in ws[1]:
            cell.font=Font(color='FFFFFF',bold=True)
            cell.fill=PatternFill('solid',fgColor='183B56')
        if name!='가격열설정':
            for cell in ws[2]:
                cell.fill=PatternFill('solid',fgColor='E5EBF2')
            for row in ws.iter_rows(min_row=3,min_col=2):
                for c in row:
                    if isinstance(c.value,(float,int)):
                        c.number_format='#,##0.00####'
        ws.column_dimensions['A'].width=20 if name=='가격열설정' else 16
        for col in range(2,ws.max_column+1):
            ws.column_dimensions[get_column_letter(col)].width=22 if name!='가격열설정' else 31
    return {'daily_dates':len(sheets['일별시세'])-2,
            'months':len(sheets['월별시세'])-2,
            'series':len(sheets['일별시세'][0])-1}
