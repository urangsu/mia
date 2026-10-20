# -*- coding: utf-8 -*-
"""DRM-friendly export: Excel COM owns encrypted workbooks (never openpyxl on Windows).
Only designated managed sheets are updated; user sheets are not read or rewritten.
A temporary workbook in the same folder is validated in Excel before atomic replacement.
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import os
import tempfile
import zipfile
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
import re

MANAGED=('RawData','Daily','Latest','일별시세','일별요약','월별시세','월별건수','가격열설정','환율원본','수집현황',
         '워크스페이스원본','보고용_금속시세','보고용_환율','보고용_시장지표','증시_시총스냅샷','보고용_시총','보고용_종합',
         'NAVER_시총원본','NAVER_지표원본','LME_원본','보고용_최근5일','보고용_3개월평균','보고용_문구','보고서_메타','보류셀')

class SecureExcelError(RuntimeError):pass


def quarantined_cells(sheets, tab):
    """Explicit invalidations only; ordinary missing history never clears cells."""
    return [(row[1],row[2]) for row in sheets.get('보류셀',[])[1:]
            if len(row)>=3 and row[0]==tab]


def is_plain_xlsx(path):
    # Used for diagnostics only. A non-ZIP .xlsx may be a company DRM-wrapped file.
    return zipfile.is_zipfile(path)


def safe_cell(value):
    """Make outside strings inert; Excel COM should never execute collected text."""
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str):
        return "'" + value if value[:1] in ("=", "+", "-", "@") else value
    return value


NUMERIC_COLUMNS = {
    'Daily': {'low','mid','high','change_pct'},
    'Latest': {'low','mid','high','change_pct'},
    '환율원본': {'매매기준율','전일대비'},
}


def excel_value(sheet, column, value):
    """Numeric price facts remain numeric in Excel, raw source text stays verbatim."""
    if value is None:
        return None
    if (column in NUMERIC_COLUMNS.get(sheet, set()) or
            sheet in ('일별시세','일별요약','월별시세','월별건수') and column not in ('고시일','기준월','출처')):
        if value == '':
            return None
        if isinstance(value, bool):
            raise SecureExcelError(f'{sheet}/{column}: 숫자 필드의 bool 값')
        try:
            number = Decimal(str(value))
            if not number.is_finite():
                raise ValueError('non-finite')
            return float(number)
        except (InvalidOperation,ValueError,TypeError) as exc:
            raise SecureExcelError(f'{sheet}/{column}: 유효하지 않은 가격 {str(value)[:40]!r}') from exc
    return safe_cell(value)


def _safe_excel_sheet(wb, name):
    try:return wb.Worksheets(name)
    except Exception:return wb.Worksheets.Add(After=wb.Worksheets(wb.Worksheets.Count))



def _date_key(value):
    """Normalize existing Excel date labels for preservation across rebuilds."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)) and 20000 < value < 120000:
        from datetime import timedelta
        return (datetime(1899,12,30)+timedelta(days=value)).date().isoformat()
    return str(value or '').strip()[:10]


def merge_external_columns(new_rows, old_rows, catalog_names):
    """Append only user-owned columns to a managed two-header time-series sheet.

    Match values to dates/months, not old Excel row indexes. Names present in
    가격열설정 are program-owned and not preserved as user additions. The prior
    version's whole-row 출처 column and FMB LOW/HIGH columns are always dropped.
    """
    if not old_rows or len(old_rows)<2 or not new_rows:
        return new_rows
    old_head=list(old_rows[0]); old_source=list(old_rows[1])
    owned=set(catalog_names)|set(new_rows[0][1:])|{'출처'}
    # Defensive handling when migrating older workbooks without a catalog.
    def old_managed(title, source):
        return title in owned or (source=='FMB' and (str(title).endswith('(하한)') or str(title).endswith('(상한)')))
    additions=[]
    for i in range(1,len(old_head)):
        title=old_head[i]
        if not isinstance(title,str) or not title.strip():
            continue
        src=old_source[i] if i<len(old_source) else ''
        if old_managed(title,src):
            continue
        # Preserve extra columns as independent source/type pairs; avoid collisions.
        if any((title,src)==(a[0],a[1]) for a in additions):
            continue
        values={}
        for old in old_rows[2:]:
            if len(old)>i and old[0] is not None:
                v=old[i]
                if v is not None and v!='':
                    values[_date_key(old[0])]=v
        additions.append((title,src,values))
    if not additions:
        return new_rows
    out=[]
    for rid,row in enumerate(new_rows):
        if rid==0:
            out.append(tuple(row)+tuple(c[0] for c in additions))
        elif rid==1:
            out.append(tuple(row)+tuple(c[1] for c in additions))
        else:
            dt=_date_key(row[0]);out.append(tuple(row)+tuple(c[2].get(dt) for c in additions))
    return out


def order_managed_columns(sheets, prior_keys, user_alias):
    """Keep old managed series order when new codes appear (append newly found codes)."""
    spec=sheets.get('가격열설정',[])
    if not spec:
        return
    specs={r[0]:r for r in spec[1:]}
    # One-time migration from v3.5.1 (with LOW/HIGH) adopts the new clean
    # metals-first order; subsequent exports keep the user's established order.
    if any(k.endswith('|LOW') or k.endswith('|HIGH') for k in prior_keys):
        prior_keys=[]
    ordered=[key for key in prior_keys if key in specs]+[key for key in specs if key not in prior_keys]
    if not ordered:
        return
    renamed=[];used=set()
    for key in ordered:
        old=specs[key];name=user_alias.get(key,old[1]);stem=name;n=2
        while name in used:
            name=f'{stem}_{n}';n+=1
        used.add(name);renamed.append((key,name,old[2]))
    original_index={r[0]:i+1 for i,r in enumerate(spec[1:])}
    for sheet in ('일별시세','일별요약','월별시세','월별건수'):
        if sheet not in sheets:
            continue
        rows=sheets[sheet]
        indices=[original_index[key] for key in ordered]
        sheets[sheet]=[tuple([r[0]]+[renamed[j][1] if i==0 else r[idx] for j,idx in enumerate(indices)]) if i!=1
             else tuple(['']+[__import__('ecm_excel_sync').series_source(ordered[j]) for j in range(len(indices))])
             for i,r in enumerate(rows)]
    sheets['가격열설정']=[spec[0]]+renamed


def guard_expansion(ws,plan):
    """A blank header is not proof that the underlying user cells are empty."""
    used=ws.UsedRange
    cols=int(used.Column+used.Columns.Count-1);rows=int(used.Row+used.Rows.Count-1)
    if cols>16384 or rows>1048576:raise SecureExcelError('Excel 범위가 한도를 초과합니다.')
    for info in plan['new_columns']:
        col=info['col']
        if col<=cols and ws.Application.WorksheetFunction.CountA(ws.Range(ws.Cells(1,col),ws.Cells(rows,col))):
            raise SecureExcelError(f'새 품목 {col}열에 사용자 데이터/수식이 있어 확장 차단')
    for info in plan['new_dates']:
        row=info['row']
        if row<=rows and ws.Application.WorksheetFunction.CountA(ws.Range(ws.Cells(row,1),ws.Cells(row,cols))):
            raise SecureExcelError(f'새 날짜 {row}행에 사용자 데이터/수식이 있어 확장 차단')

def _com_rows(ws, maxrows=200000, maxcols=1024):
    """Bounded Excel COM read for preserving user-owned columns only."""
    lastcol=int(ws.Cells(1,ws.Columns.Count).End(-4159).Column) # xlToLeft
    lastrow=int(ws.Cells(ws.Rows.Count,1).End(-4162).Row) # xlUp
    if lastcol>maxcols or lastrow>maxrows:
        raise SecureExcelError('기존 시세표가 보존 가능한 최대 범위를 초과했습니다. 원본 보존 후 수동 검토 필요')
    if lastrow<2 or lastcol<2:return []
    vals=ws.Range(ws.Cells(1,1),ws.Cells(lastrow,lastcol)).Value2
    return [tuple(v) if isinstance(v,(tuple,list)) else (v,) for v in vals]

def _optional_visual(operation, description: str, logger=None):
    """Formatting is presentation only. Corporate DRM may disallow NumberFormat.

    Cell writes, SaveCopyAs/SaveAs, and integrity verification remain fatal.
    """
    try:
        operation()
        return True
    except Exception as exc:
        if logger:
            logger(f'Excel 선택 서식 생략 [{description}]: {type(exc).__name__}: {str(exc)[:160]}')
        return False


def write_com_sheets(path:Path, sheets:dict[str,list[tuple]], *, active='일별요약', logger=None):
    """Save back through isolated Excel COM. No openpyxl on corporate Windows.

    Existing encrypted workbook is opened by Excel itself, never unwrapped manually.
    Never overwrite target unless temporary workbook can be re-opened with Excel.
    """
    if os.name!='nt':raise SecureExcelError('Excel COM은 Windows Excel 설치 환경에서만 실행 가능합니다.')
    try:
        import pythoncom
        import win32com.client as win32
    except ImportError as exc:
        raise SecureExcelError('사내 보안 Excel 처리에는 pywin32가 필요합니다: py -m pip install pywin32') from exc
    path=Path(path).resolve()
    from export_cache import unchanged,record
    if unchanged(path,sheets):
        if logger:logger('Excel 변경 없음: 데이터/파일 해시 일치, COM 쓰기·저장 생략')
        return path
    if path.suffix.lower()!='.xlsx':raise SecureExcelError('자동 누적 파일은 .xlsx만 지원하며 .xlsm 원본은 수정하지 않습니다.')
    path.parent.mkdir(parents=True,exist_ok=True)
    existing_file=path.exists()
    originally_protected=existing_file and not is_plain_xlsx(path)
    if logger:
        logger(f'누적 Excel 대상: {path} ({"기존 파일 갱신" if existing_file else "파일이 없어 신규 생성"})')
    if path.exists() and path.stat().st_size==0:
        raise SecureExcelError('기존 Excel 파일 크기가 0입니다. 덮어쓰지 않고 중단합니다.')
    fd, tempname=tempfile.mkstemp(prefix='fm_stage_',suffix='.xlsx',dir=path.parent)
    os.close(fd)
    tmp=Path(tempname)
    tmp.unlink(missing_ok=True)
    pythoncom.CoInitialize()
    excel=None;wb=None;verify=None
    try:
        excel=win32.DispatchEx('Excel.Application')
        excel.Visible=False;excel.DisplayAlerts=False;excel.EnableEvents=False
        try:excel.AutomationSecurity=3 # disable macros on open
        except Exception:pass
        if path.exists():
            try:
                wb=excel.Workbooks.Open(str(path),UpdateLinks=0,ReadOnly=False,IgnoreReadOnlyRecommended=True)
            except Exception as open_error:
                fingerprint=('일반 XLSX ZIP 형식' if is_plain_xlsx(path) else '비표준 XLSX/회사 DRM 가능성')
                raise SecureExcelError(
                    f'원본 Excel Open 실패: {path.name} ({path.stat().st_size:,} bytes, {fingerprint}). '
                    'DRM/파일 잠금/경로/손상 여부를 Excel에서 직접 열어 확인하세요. '
                    '기존 파일은 변경하지 않았습니다. '
                    '별도 신규 Excel 검증은 --export-fresh를 사용하세요. '
                    f'원본 예외: {str(open_error)[:240]}') from open_error
            if wb.ReadOnly:raise SecureExcelError('Excel 파일이 읽기전용으로 열렸습니다. 사용자 편집중/보안 정책을 확인하세요.')
        else:wb=excel.Workbooks.Add()
        # Read the existing program-owned catalog BEFORE overwriting it.
        # User-owned columns in the daily/monthly view are matched by date
        # and restored to the right of the current managed series.
        previous_keys=[];user_alias={};old_catalog_titles=set()
        try:
            old=wb.Worksheets('가격열설정')
        except Exception:
            old=None
        if old is not None:
            maxr=min(int(old.UsedRange.Rows.Count),10000)
            for r in range(2,maxr+1):
                k=old.Cells(r,1).Value
                v=old.Cells(r,2).Value
                if isinstance(k,str) and k:
                    previous_keys.append(k)
                    # After a user renames LC -> LC_new, the old 'LC' is still
                    # an application-managed column, not a third-party addition.
                    from smbs_rates import report_series_label
                    old_catalog_titles.add(report_series_label(k))
                    if isinstance(v,str) and v.strip():
                        user_alias[k]=v.strip()
                        old_catalog_titles.add(v.strip())
        existing_report={}
        for tab in ('일별시세','일별요약','월별시세','월별건수'):
            if tab not in sheets:continue
            try:
                prev=wb.Worksheets(tab)
            except Exception:
                continue
            existing_report[tab]=_com_rows(prev)
        order_managed_columns(sheets,previous_keys,user_alias)
        # An existing managed daily/monthly view is updated IN PLACE.
        # This preserves user-added columns, formulas, formatting and physical order.
        # Entire-sheet Clear() is used ONLY for non-report raw/audit tabs and new tabs.
        report_plans={}
        old_catalog_rows=_com_rows(old) if old is not None else None
        for tab, oldrows in existing_report.items():
            if not old_catalog_rows:
                raise SecureExcelError(f'{tab}: 기존 가격열설정이 없어 사용자 열을 안전하게 구분할 수 없습니다. 원본을 보존합니다.')
            from ecm_excel_sync import build_plan, ECMBlocked
            try:
                report_plans[tab]=build_plan(sheets[tab],sheets['가격열설정'],
                    oldrows,old_catalog_rows,date1904=bool(wb.Date1904),
                    period_type='monthly' if tab.startswith('월별') else 'daily',
                    clear_cells=quarantined_cells(sheets,tab))
            except ECMBlocked as exc:
                raise SecureExcelError(f'{tab}: 기존 열/일자 매핑 불명확. 원본 미변경: {exc}') from exc
            if logger:
                st=report_plans[tab]['stats']
                logger(f'{tab} 증분 갱신 계획: 날짜/월 +{st["new_dates"]}, 종목 +{st["new_columns"]}, '
                       f'빈셀 +{st["fill"]}, 가격수정 {st["correction"]}, 동일 {st["unchanged"]}')
        for name, rows in sheets.items():
            if name not in MANAGED:raise SecureExcelError(f'관리 대상이 아닌 시트 갱신 차단: {name}')
            try:ws=wb.Worksheets(name)
            except Exception:
                ws=wb.Worksheets.Add(After=wb.Worksheets(wb.Worksheets.Count));ws.Name=name
            if ws.ProtectContents:raise SecureExcelError(f'{name} 시트가 보호돼 있습니다. 원본을 변경하지 않았습니다.')
            if name in report_plans:
                plan=report_plans[name]
                guard_expansion(ws,plan)
                # Confirm no formulas exist in any cell scheduled for replacement.
                for e in plan['edits']:
                    if bool(ws.Cells(e['row'],e['col']).HasFormula):
                        raise SecureExcelError(f'{name}: 사용자 수식 {e["row"]}행 {e["col"]}열 보호; 저장 중단')
                for info in plan['new_columns']:
                    ws.Cells(1,info['col']).Value2=info['name']
                    ws.Cells(2,info['col']).Value2=info['source']
                for info in plan['new_dates']:
                    ws.Cells(info['row'],1).Value2=info['date']
                from com_updates import put_blocks
                put_blocks(ws,plan['edits'])
                # Do not change user column order, references, or number formats.
                # The staging workbook is re-opened and checked before replacement.
                continue
            # Previous versions used Excel ListObjects in managed sheets. Remove only their
            # table wrappers before replacing cells to avoid stale structured-reference ranges.
            try:
                while ws.ListObjects.Count:
                    ws.ListObjects(1).Unlist()
            except Exception as exc:
                raise SecureExcelError(f'{name}: 기존 Excel 표(Table) 해제 실패. 원본은 보존됩니다.') from exc
            # Do not remove user sheets / VBA / externally managed sheets.
            ws.Cells.Clear()
            if not rows:continue
            ncol=len(rows[0])
            if ncol>16384 or len(rows)>1048576:
                raise SecureExcelError(f'{name}: Excel 최대 크기를 초과했습니다. DB는 보존하며 연도별 보기/추출을 검토하세요.')
            # A whole-column NumberFormat operation can be forbidden by a corporate
            # Excel security add-in. Never abort a valid data write for formatting.
            _optional_visual(lambda: setattr(ws.Columns(1), 'NumberFormat',
                '@' if name in ('RawData','가격열설정') else 'General'),
                f'{name} A열 표시형식', logger)
            owned_catalog={r[1] for r in sheets.get('가격열설정',[])[1:]}
            for start in range(0,len(rows),500):
                block=rows[start:start+500]
                if any(len(x)!=ncol for x in block):raise SecureExcelError(f'{name}: 열 수 불일치')
                header_rows=2 if name in ('일별시세','일별요약','월별시세','월별건수') else 1
                vals=tuple(tuple(safe_cell(v) if start+i<header_rows or
                                     (name in ('일별시세','일별요약','월별시세','월별건수') and
                                      j>0 and rows[0][j] not in owned_catalog) else
                                     excel_value(name,str(rows[0][j]),v)
                                 for j,v in enumerate(row)) for i,row in enumerate(block))
                target=ws.Range(ws.Cells(start+1,1),ws.Cells(start+len(block),ncol))
                target.Value2=vals
            hdr=ws.Range(ws.Cells(1,1),ws.Cells(1,ncol))
            _optional_visual(lambda: setattr(hdr.Font, 'Bold', True), f'{name} 헤더 굵게',logger)
            _optional_visual(lambda: setattr(hdr.Interior, 'Color', 0x563B18), f'{name} 헤더 배경',logger)
            _optional_visual(lambda: setattr(hdr.Font, 'Color', 0xFFFFFF), f'{name} 헤더 글자색',logger)
            if name not in ('일별시세','일별요약','월별시세','월별건수'):
                try:ws.Range(ws.Cells(1,1),ws.Cells(1,ncol)).AutoFilter()
                except Exception:pass
            else:
                source_header=ws.Range(ws.Cells(2,1),ws.Cells(2,ncol))
                _optional_visual(lambda: setattr(source_header.Font,'Color',0x404040),f'{name} 출처 글자색',logger)
                _optional_visual(lambda: setattr(source_header.Interior,'Color',0xF2EBE5),f'{name} 출처 배경',logger)
            try:ws.Application.ActiveWindow.FreezePanes=False
            except Exception:pass
            _optional_visual(lambda: setattr(ws.Columns(1),'ColumnWidth',18),f'{name} A열 폭',logger)
            if name in ('Daily','Latest','환율원본','일별시세','월별시세') and len(rows)>1:
                try:
                    row0=3 if name in ('일별시세','일별요약','월별시세') else 2
                    col0=2
                    if len(rows)>=row0 and ncol>=col0:
                        ws.Range(ws.Cells(row0,col0),ws.Cells(len(rows),ncol)).NumberFormat='#,##0.00####'
                except Exception as exc:
                    if logger:logger(f'Excel 선택 서식 생략 [{name} 숫자 표시]: {type(exc).__name__}: {str(exc)[:160]}')
            for col in range(2,min(ncol+1,120)):
                _optional_visual(lambda c=col: setattr(ws.Columns(c),'ColumnWidth',19 if name!='RawData' else 24),
                    f'{name} {col}열 폭',logger)
            if name in ('일별시세','일별요약','월별시세','월별건수'):
                try:
                    ws.Activate()
                    ws.Range('B3').Select()
                    excel.ActiveWindow.FreezePanes=True
                except Exception:pass
        try:wb.Worksheets(active).Activate()
        except Exception:pass
        # SaveCopyAs retains the currently opened corporate workbook format more
        # faithfully than SaveAs(FileFormat=51), which can strip a DRM wrapper.
        # We still reject any plaintext replacement for a protected source.
        if originally_protected:
            wb.SaveCopyAs(str(tmp))
        else:
            wb.SaveAs(str(tmp),FileFormat=51)
        wb.Close(SaveChanges=False);wb=None
        verify=excel.Workbooks.Open(str(tmp),UpdateLinks=0,ReadOnly=True)
        for name in sheets:
            ws=verify.Worksheets(name)
            if ws.Cells(1,1).Value is None:raise SecureExcelError(f'Excel 재검증 실패: {name} 헤더 누락')
            rows=sheets[name]
            if name in report_plans:
                plan=report_plans[name]
                for info in plan['new_columns']:
                    actual_head=ws.Cells(1,info['col']).Value2
                    if actual_head!=info['name']:
                        raise SecureExcelError(f'Excel 재검증 실패: {name} 신규 열 헤더 {info["name"]!r}')
                for info in plan['new_dates']:
                    actual_day=ws.Cells(info['row'],1).Value2
                    if (str(actual_day)[:7] if name.startswith('월별') else _date_key(actual_day))!=info['date']:
                        raise SecureExcelError(f'Excel 재검증 실패: {name} 신규 일자/기준월 {info["date"]!r}')
                for e in plan['edits']:
                    actual=ws.Cells(e['row'],e['col']).Value2
                    if e['incoming'] is None:
                        match=actual in (None,'')
                    else:
                        try:match=abs(float(actual)-float(e['incoming']))<=max(1e-8,abs(float(e['incoming']))*1e-9)
                        except (TypeError,ValueError):match=False
                    if not match:raise SecureExcelError(f'Excel 재검증 실패: {name} {e["row"]}행/{e["col"]}열 값 불일치')
                continue
            if rows and len(rows)>2 and name in ('일별시세','일별요약','월별시세','월별건수'):
                # Validate the actual last date/period, not just an existing header.
                actual=ws.Cells(len(rows),1).Value2
                expected=str(rows[-1][0] or '')
                # Excel COM Value2 returns date-formatted cells as serial days,
                # even if the source was an ISO string; e.g. 46314 == 2026-10-19.
                actual_date=_date_key(actual)
                if name in ('월별시세','월별건수'):
                    valid=(actual_date[:7]==expected[:7])
                else:
                    valid=(actual_date==expected)
                if not valid:
                    raise SecureExcelError(f'Excel 재검증 실패: {name} 마지막 날짜 불일치 ({actual!r} -> {actual_date!r} != {expected!r})')
                # Value check: an Excel sheet with only correct dates but lost
                # price values is not a successful export.
                candidates=[(i,j,v) for i,r in enumerate(rows[2:],3) for j,v in enumerate(r[1:],2)
                            if isinstance(v,(int,float)) and not isinstance(v,bool)]
                if candidates:
                    i,j,v=candidates[-1]
                    stored=ws.Cells(i,j).Value2
                    try:
                        matches=abs(float(stored)-float(v))<=max(1e-8,abs(float(v))*1e-9)
                    except (ValueError,TypeError):matches=False
                    if not matches:
                        raise SecureExcelError(f'Excel 재검증 실패: {name} 가격 누락/변경 (행{i},열{j}; {stored!r} != {v!r})')
        verify.Close(SaveChanges=False);verify=None
        # Never silently replace a DRM wrapper with an unprotected plain XLSX.
        if originally_protected and is_plain_xlsx(tmp):
            raise SecureExcelError('보안 원본의 임시 Excel이 일반 XLSX로 저장됐습니다. 보안 해제를 막기 위해 원본 교체를 중단했습니다. 회사 보안 Excel 저장 정책을 확인하세요.')
        os.replace(tmp,path)
        try:record(path,sheets)
        except OSError as exc:
            if logger:logger(f'Excel 변경없음 캐시 저장 생략: {type(exc).__name__}')
        if logger:logger(f'Excel COM 보안 저장 성공: {path}')
        return path
    except Exception as exc:
        if isinstance(exc,SecureExcelError):raise
        raise SecureExcelError(f'Excel COM 데이터/저장 단계 실패 ({type(exc).__name__}): {str(exc)[:300]}. 기존 DB/Excel 보존') from exc
    finally:
        if verify is not None:
            try:verify.Close(SaveChanges=False)
            except Exception:pass
        if wb is not None:
            try:wb.Close(SaveChanges=False)
            except Exception:pass
        if excel is not None:
            try:excel.Quit()
            except Exception:pass
        pythoncom.CoUninitialize()
        tmp.unlink(missing_ok=True)


def make_sheets(prices, latest, fx_quotes, aliases=None):
    from collections import defaultdict
    from smbs_rates import prepare_excel_series,FX_CODES,QUOTE_UNITS,report_series_label,report_series_source
    aliases=aliases or {}
    from series_mapping import compact_series_label, catalogue_description
    descriptions={p.symbol:p.description for p in reversed(prices) if p.description}
    sheet={}
    cols=['symbol','date','low','mid','high','change_pct','unit','description','widget','price_mode','source','view_key','period_label']
    sheet['RawData']=[tuple(cols)]+[tuple(getattr(p,c) for c in cols) for p in prices]
    sheet['Daily']=[('date','symbol','description','low','mid','high','unit','change_pct','price_mode','widget','source')]+[
        (p.date,p.symbol,p.description,p.low,p.mid,p.high,p.unit,p.change_pct,p.price_mode,p.widget,p.source)
        for p in prices if p.price_mode in ('Actual','Unspecified') and not p.period_label]
    sheet['Latest']=[('symbol','description','date','low','mid','high','unit','change_pct','price_mode','freshness','widget','source')]+[
        tuple(r.get(k) for k in ('symbol','description','date','low','mid','high','unit','change_pct','price_mode','freshness','widget','source')) for r in latest]
    issues=[];quarantined=[]
    records=prepare_excel_series(prices,fx_quotes,issues=issues,quarantined=quarantined)
    available={k for r in records.values() for k in r}
    # Preserve series identity even if every observation is currently withheld.
    available.update(k for _,k,_ in quarantined)
    # The reporting view has exactly one price column (MID) per FMB series.
    # LOW/HIGH stay in SQLite and RawData, never in the daily/monthly report.
    fixed=[f'FX_{c}_KRW_per_{QUOTE_UNITS[c]}' for c in FX_CODES if f'FX_{c}_KRW_per_{QUOTE_UNITS[c]}' in available]
    # Business-readable order: lithium → cobalt → nickel/manganese → black mass → FX.
    # Forecast precedes actual for the same metal, then new unknown codes follow.
    code_priority=('MB-LI-0029','MB-LI-0033','MB-CO-0005','MB-NI-0001',
                   'MB-MN-0001','MB-BMS-0002','MB-BMS-0012','MB-BMS-0010')
    def sort_fmb(k):
        _,code,unit,mode,kind=k.split('|',4)
        return ((code_priority.index(code) if code in code_priority else len(code_priority)),
                code, (0 if mode=='Forecast' else 1 if mode=='Actual' else 2),unit)
    keys=sorted((k for k in available if k.startswith('FMB|') and k.endswith('|MID')),
                key=sort_fmb)+fixed
    labels={}
    used=set()
    for key in keys:
        name=aliases.get(key) or compact_series_label(key, descriptions.get(key.split('|')[1], '') if key.startswith('FMB|') else '')
        root=name;num=2
        while name in used:
            name=f'{root}_{num}';num+=1
        used.add(name);labels[key]=name
    sheet['가격열설정']=[('시리즈 키(수정 금지)','짧은 표시명','단위·원본 기준')]+[
        (k,labels[k], catalogue_description(k,descriptions.get(k.split('|')[1], '') if k.startswith('FMB|') else '')) for k in keys]
    def two_headers(time_key):
        return [tuple([time_key]+[labels[k] for k in keys]),
                tuple(['']+[report_series_source(k) for k in keys])]
    report_dates=sorted({dt for dt,items in records.items() if any(k in items for k in keys)} |
                        {dt for dt,k,_ in quarantined if k in keys})
    sheet['일별시세']=two_headers('고시일')+[
        tuple([dt]+[records.get(dt,{}).get(k) for k in keys]) for dt in report_dates]
    acc=defaultdict(lambda:defaultdict(list))
    for dt in report_dates:
        for k,v in records.get(dt,{}).items():
            if k in keys and '_DIFF_KRW_per_' not in k:acc[dt[:7]][k].append(v)
    # Compatible existing daily sheet + user-requested always-created daily summary.
    # Both are regenerated from the SAME validated DB facts, not queried separately.
    sheet['일별요약']=[tuple(r) for r in sheet['일별시세']]
    sheet['월별시세']=two_headers('기준월')+[
        tuple([dt]+[(sum(acc[dt][k])/len(acc[dt][k])) if acc[dt].get(k) else None for k in keys])
        for dt in sorted({day[:7] for day in report_dates})]
    sheet['월별건수']=two_headers('기준월')+[
        tuple([dt]+[len(acc[dt][k]) if acc[dt].get(k) else 0 for k in keys])
        for dt in sorted({day[:7] for day in report_dates})]
    sheet['보류셀']=[('시트','기준일·월','시리즈 키','사유')]
    invalid={(dt,k,reason) for dt,k,reason in quarantined if k in keys}
    for dt,k,reason in sorted(invalid):
        for tab in ('일별시세','일별요약'):
            sheet['보류셀'].append((tab,dt,k,reason))
    for month,k in sorted({(dt[:7],k) for dt,k,_ in invalid}):
        if not acc[month].get(k):
            sheet['보류셀'].append(('월별시세',month,k,'검증된 월별 표본 없음: 가격 충돌'))
    sheet['환율원본']=[('고시일','통화','매매기준율','전일대비','기준통화수량','출처')]+[
        (q.quote_date,q.currency,float(q.rate),float(q.difference),q.unit,q.source) for q in fx_quotes]
    max_date=max(records, default='')
    fmb_dates={p.date for p in prices if p.price_mode in ('Actual','Unspecified') and not p.period_label}
    fx_dates={q.quote_date for q in fx_quotes}
    sheet['수집현황']=[('구분','전체 기록수','고시일수','최근 고시일','진단 상태'),
         ('FMB',len(prices),len(fmb_dates),max(fmb_dates,default=''), '고시일 기준 누적; 실제 수집완전성은 last_diagnostic.json 확인'),
         ('SMBS',len(fx_quotes),len(fx_dates),max(fx_dates,default=''), '날짜·통화 중복방지; 통화별 실패는 fx_last_diagnostic.json 확인'),
         ('통합 일별',len(report_dates),len(report_dates),max(report_dates,default=''), '휴장일 미고시 자료는 채우지 않음'),
         ('가격 충돌',len(issues),0,'','; '.join(issues[:5]) or '검증 완료; 충돌 없음')]
    return sheet
