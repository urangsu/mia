# -*- coding: utf-8 -*-
"""Conservative ECM workbook sync: date rows, source/series columns, cell edits.

Excel COM edits the *already opened* target workbook. Never downloads, overwrites,
replaces, unprotects, or silently changes a DRM/ECM document. Server check-in is
NOT inferred from an Excel.Save() success.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json, hashlib
from contextlib import contextmanager

class ECMBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class Edit:
    date: str
    key: str
    header: str
    source: str
    row: int
    col: int
    previous: object
    incoming: float | None
    decision: str # fill, correction, quarantine (withdraw a conflicting fact)


def date_key(value, date1904=False):
    if isinstance(value, datetime): return value.date().isoformat()
    if isinstance(value, date): return value.isoformat()
    if isinstance(value,(int,float)) and 10000<float(value)<90000:
        epoch=datetime(1904,1,1) if date1904 else datetime(1899,12,30)
        return (epoch+timedelta(days=float(value))).date().isoformat()
    text=str(value or '').strip()
    for fmt in ('%Y-%m-%d','%Y.%m.%d','%Y/%m/%d','%Y%m%d'):
        try:return datetime.strptime(text,fmt).date().isoformat()
        except ValueError:pass
    raise ECMBlocked(f'날짜 인식 불가: {text[:50]!r}; 연도가 빠진 날짜는 매칭 불가')


def _decimal(v):
    if v is None or v=='':return None
    try:
        n=Decimal(str(v).replace(',',''))
        if not n.is_finite():raise InvalidOperation()
        return n
    except (InvalidOperation,ValueError):
        return None


def _build_catalogue(rows, origin):
    """Catalog columns: series id / visible name / full source text."""
    d={}
    for row in rows[1:]:
        if len(row)<2:continue
        k=str(row[0] or '').strip();display=str(row[1] or '').strip()
        if not k or not display:continue
        if k in d:raise ECMBlocked(f'{origin} 가격열설정에 중복 key: {k}')
        d[k]=display
    return d


def _lookup(header1, header2, catalog, origin):
    """Per-run lookup; no hard-coded physical column numbers."""
    pairs={};seen=set()
    for idx,(h,s) in enumerate(zip(header1[1:],header2[1:]),2):
        name=str(h or '').strip();source=str(s or '').strip().upper()
        if not name and not source:continue
        if (name,source) in seen:
            raise ECMBlocked(f'{origin} 헤더가 두 번 나타납니다: {name!r}/{source!r}; 위치 임의 결정 차단')
        seen.add((name,source));pairs[(name,source)]=idx
    out={}
    for key,name in catalog.items():
        source=series_source(key)
        if (name,source) in pairs:
            out[key]=pairs[(name,source)]
    return out


def series_source(key):
    return 'SMBS' if key.startswith('FX_') else 'NAVER' if key.startswith('NAVER|') else 'FDR' if key.startswith('FDR|') else 'FMB'


def build_plan(source_rows, source_catalog_rows, target_rows, target_catalog_rows,
               *, date1904=False, allow_missing_columns=True, max_edits=100000, period_type="daily",
               clear_cells=()):
    """Pure planner for testability and determinism. No external spreadsheet writes.

    Content layout: row1 name, row2 origin, row3+ date and numeric values.
    Target user columns are never modified. Missing managed keys may be appended.
    Correction candidates require explicit approval before *any* write.
    """
    if len(source_rows)<2 or len(target_rows)<2:
        raise ECMBlocked('원본/ECM의 헤더 1·2행을 읽지 못했습니다.')
    title='기준월' if period_type=='monthly' else '고시일'
    if str(source_rows[0][0]).strip()!=title or str(target_rows[0][0]).strip()!=title:
        raise ECMBlocked(f'A1 {title} 형식을 확인할 수 없습니다. 무단 새 양식 생성 금지')
    def normalize(v):
        if period_type=='monthly':
            t=str(v or '').strip()
            if not __import__('re').fullmatch(r'\d{4}-(?:0[1-9]|1[0-2])', t):
                raise ECMBlocked(f'월별 기준월 오류: {t[:35]}')
            return t
        return date_key(v,date1904)
    src_catalog=_build_catalogue(source_catalog_rows,'원본')
    dest_catalog=_build_catalogue(target_catalog_rows,'ECM')
    src_keys=_lookup(source_rows[0],source_rows[1],src_catalog,'원본')
    dst_keys=_lookup(target_rows[0],target_rows[1],dest_catalog,'ECM')
    clears={(normalize(day),key) for day,key in clear_cells}
    # A changed/missing ECM caption in the catalogue is ambiguous, not permission
    # to append a duplicate series with identical underlying identity.
    for key in dest_catalog:
        if key in src_keys and key not in dst_keys:
            raise ECMBlocked(f'ECM에서 등록 종목 {key}의 1·2행 헤더가 가격열설정과 다릅니다. 명칭/출처 확인 후 재시도')
    reserved={(str(c or '').strip(),str(target_rows[1][i] or '').strip().upper())
              for i,c in enumerate(target_rows[0]) if i<len(target_rows[1])}
    appended=[]
    width=max(len(target_rows[0]),len(target_rows[1]))
    for key in src_keys:
        if key in dst_keys:continue
        if not allow_missing_columns:
            raise ECMBlocked(f'ECM에 신규 품목 {key} 열이 없습니다 (자동추가 설정 꺼짐)')
        name=src_catalog[key];source=series_source(key)
        if (name,source) in reserved:
            raise ECMBlocked(f'ECM의 {name}/{source}는 다른 코드로 등록됐을 수 있습니다. 자동추가 차단')
        width+=1
        dst_keys[key]=width
        appended.append({'key':key,'col':width,'name':name,'source':source,
                         'description': next((str(r[2]) for r in source_catalog_rows[1:] if r and r[0]==key and len(r)>2),'')})
        reserved.add((name,source))
    date_to_row={}
    for i,row in enumerate(target_rows[2:],3):
        if not row or row[0] is None or str(row[0]).strip()=='':continue
        day=normalize(row[0])
        if day in date_to_row:raise ECMBlocked(f'ECM A열 날짜 {day}가 중복입니다: {date_to_row[day]}행 및 {i}행')
        date_to_row[day]=i
    date_to_src={}
    for row in source_rows[2:]:
        if not row or row[0] is None:continue
        day=date_key(row[0]) if period_type=='daily' else normalize(row[0])
        if day in date_to_src:raise ECMBlocked(f'수집용 시세표에 날짜 {day}가 중복입니다.')
        date_to_src[day]=row
    new_dates=[];edits=[];unchanged=0;skipped=0;corrections=0;cleared=0
    next_row=max(len(target_rows),2)
    for day,source in sorted(date_to_src.items()):
        if day in date_to_row:
            row_idx=date_to_row[day]
            existing=target_rows[row_idx-1]
        else:
            next_row+=1;row_idx=next_row;date_to_row[day]=row_idx
            existing=()
            new_dates.append({'date':day,'row':row_idx})
        for key,src_col in src_keys.items():
            incoming=_decimal(source[src_col-1] if len(source)>=src_col else None)
            withdraw=incoming is None and (day,key) in clears
            if incoming is None and not withdraw:
                skipped+=1;continue
            dst_col=dst_keys[key]
            old=existing[dst_col-1] if len(existing)>=dst_col else None
            prior=_decimal(old)
            if old is not None and old!='' and prior is None:
                raise ECMBlocked(f'ECM {day} / {key}: 숫자가 아닌 기존 데이터가 있어 덮어쓰기 차단')
            if prior == incoming:
                unchanged+=1;continue
            decision='quarantine' if withdraw else 'fill' if prior is None else 'correction'
            if withdraw:cleared+=1
            elif prior is not None:corrections+=1
            edits.append(Edit(day,key,src_catalog[key],
                               series_source(key),
                              row_idx,dst_col,float(prior) if prior is not None else None,
                              float(incoming) if incoming is not None else None,decision))
            if len(edits)>max_edits:raise ECMBlocked('한 번에 쓰려는 셀이 상한을 초과했습니다. 날짜 범위를 검토하세요.')
    return {'edits':[asdict(e) for e in edits], 'new_dates':new_dates, 'new_columns':appended,
            'stats':{'new_columns':len(appended),'new_dates':len(new_dates),'fill':len(edits)-corrections-cleared,
                     'correction':corrections,'cleared':cleared,'unchanged':unchanged,'missing_source':skipped},
            'src_count':len(date_to_src),'target_count':len(target_rows)-2}


def plan_fingerprint(plan):
    data=json.dumps(plan,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return hashlib.sha256(data.encode('utf8')).hexdigest()


def _read_matrix(ws, minrows=2, maxrows=100000, maxcols=800):
    col=int(ws.Cells(1,ws.Columns.Count).End(-4159).Column)
    row=int(ws.Cells(ws.Rows.Count,1).End(-4162).Row)
    if col>maxcols or row>maxrows:
        raise ECMBlocked(f'ECM 범위 초과: {row}행/{col}열; 전체 편집 중단')
    col=max(1,col);row=max(minrows,row)
    data=ws.Range(ws.Cells(1,1),ws.Cells(row,col)).Value2
    if not isinstance(data,(list,tuple)):return [[data]]
    return [list(r) if isinstance(r,(list,tuple)) else [r] for r in data]


@contextmanager
def _attached_excel(expected_basename,local_path=None,target_fullname=None):
    import sys
    if sys.platform!='win32':raise ECMBlocked('ECM 자동 편집은 Excel 설치된 Windows에서만 사용합니다.')
    try:
        import pythoncom
        import win32com.client as win32
    except ImportError as ex:raise ECMBlocked('Excel COM 연결에는 pywin32가 필요합니다.') from ex
    pythoncom.CoInitialize()
    excel=None
    try:
        # No DispatchEx: ECM opened the instance and retains file locks/DRM.
        try:excel=win32.GetActiveObject('Excel.Application')
        except Exception as exc:
            raise ECMBlocked('ECM 문서가 데스크톱 Microsoft Excel에서 열려 있지 않습니다. 브라우저 미리보기만 열린 경우 자동 반영 불가') from exc
        expected=expected_basename.lower().removesuffix('.xlsx')+'.xlsx'
        books=[]
        for i in range(1,excel.Workbooks.Count+1):
            wb=excel.Workbooks(i)
            try:
                full=str(wb.FullName)
                if wb.Name.lower()==expected and (not target_fullname or full.casefold()==target_fullname.casefold()):
                    if local_path and str(Path(full).resolve()).casefold()==str(Path(local_path).resolve()).casefold():
                        continue
                    books.append(wb)
            except Exception:continue
        if len(books)!=1:
            raise ECMBlocked(f'실행 중인 Excel에서 {expected_basename!r} 대상 통합문서를 유일하게 확인하지 못했습니다 ({len(books)}개). 로컬 시세표와 ECM 파일을 혼동하지 않도록 중단')
        wb=books[0]
        if wb.ReadOnly:raise ECMBlocked('ECM 파일이 읽기 전용입니다. ECM 체크아웃/편집 권한을 확인하세요.')
        if not wb.FullName:raise ECMBlocked('ECM 대상 문서의 파일 경로가 확인되지 않습니다.')
        yield wb
    finally:
        # Do not quit/close Excel: user/ECM owns it.
        pythoncom.CoUninitialize()


def _read_catalog(wb):
    try:return _read_matrix(wb.Worksheets('가격열설정'))
    except Exception as exc:raise ECMBlocked('ECM 파일에 가격열설정 시트가 없습니다. 수집기가 생성한 완전한 파일을 업로드하세요.') from exc


def _snapshot_from_db(folder, *, with_quarantine=False):
    from report_model import build_context,make_workbook_sheets
    sheets=make_workbook_sheets(build_context(Path(folder)))
    result=(sheets['일별요약'],sheets['가격열설정'])
    if with_quarantine:
        from excel_secure import quarantined_cells
        return result+(quarantined_cells(sheets,'일별요약'),)
    return result


def prepare_ecm_plan(folder, expected_basename, *, local_path=None, target_fullname=None,
                     target_sheet='일별요약', target_hwnd=None, log=print):
    source, source_catalog, clears=_snapshot_from_db(folder,with_quarantine=True)
    with _attached_excel(expected_basename,local_path,target_fullname) as wb:
        if target_hwnd is not None and int(wb.Application.Hwnd)!=int(target_hwnd):
            raise ECMBlocked('ECM 열기 이후 Excel 프로세스가 변경되었습니다. 다시 확인하세요.')
        try:ws=wb.Worksheets(target_sheet)
        except Exception as exc:raise ECMBlocked(f'ECM 통합문서에 {target_sheet} 시트가 없습니다. 올린 Excel 파일을 확인하세요.') from exc
        dest=_read_matrix(ws);catalog=_read_catalog(wb)
        plan=build_plan(source,source_catalog,dest,catalog,date1904=bool(wb.Date1904),clear_cells=clears)
        plan['workbook_name']=str(wb.Name);plan['workbook_path']=str(wb.FullName)
        plan['sheet']=target_sheet
        if target_hwnd is not None:plan['excel_hwnd']=int(target_hwnd)
        plan['fingerprint']=plan_fingerprint({k:v for k,v in plan.items() if k!='fingerprint'})
        log(f'ECM 미리보기: 날짜 +{plan["stats"]["new_dates"]}, 종목 +{plan["stats"]["new_columns"]}, '
            f'빈 셀 {plan["stats"]["fill"]}, 정정 후보 {plan["stats"]["correction"]}, '
            f'충돌 보류·기존값 비우기 {plan["stats"]["cleared"]}, 기존 동일 {plan["stats"]["unchanged"]}')
        return plan


def apply_ecm_plan(folder, expected_basename, approved_plan, *, local_path=None, log=print):
    full=approved_plan['workbook_path'];sheet=approved_plan['sheet']
    source,source_catalog,clears=_snapshot_from_db(folder,with_quarantine=True)
    with _attached_excel(expected_basename,local_path,full) as wb:
        if 'excel_hwnd' in approved_plan and int(wb.Application.Hwnd)!=int(approved_plan['excel_hwnd']):
            raise ECMBlocked('승인 이후 Excel 프로세스가 변경되어 반영을 차단했습니다.')
        ws=wb.Worksheets(sheet)
        if ws.ProtectContents:raise ECMBlocked(f'{sheet} 시트가 보호돼 있어 자동입력이 불가합니다.')
        current=build_plan(source,source_catalog,_read_matrix(ws),_read_catalog(wb),date1904=bool(wb.Date1904),clear_cells=clears)
        current['workbook_name']=str(wb.Name);current['workbook_path']=str(wb.FullName);current['sheet']=sheet
        if 'excel_hwnd' in approved_plan:current['excel_hwnd']=int(wb.Application.Hwnd)
        sig=plan_fingerprint(current)
        if sig!=approved_plan['fingerprint']:
            raise ECMBlocked('미리보기 이후 원본 DB 또는 ECM 내용이 달라졌습니다. 다시 미리보기를 실행하세요.')
        if not current['edits'] and not current['new_dates'] and not current['new_columns']:
            return {'status':'UNCHANGED','applied':0,'created_rows':0,'created_cols':0,
                    'server_verified':False,'workbook':str(wb.Name),'sheet':sheet}
        # Guard formula and pre-existing formatting/other data BEFORE first edit.
        for e in current['edits']:
            cell=ws.Cells(e['row'],e['col'])
            if bool(cell.HasFormula):raise ECMBlocked(f'ECM 수식 보호: {cell.Address}, {e["key"]}')
        # Check that future rows/columns are truly vacant, not just missing
        # header text. Aborts rather than overwriting any unregistered user data.
        scan_cols=min(max(ws.UsedRange.Column+ws.UsedRange.Columns.Count-1,1),800)
        scan_rows=min(max(ws.UsedRange.Row+ws.UsedRange.Rows.Count-1,2),100000)
        for info in current['new_dates']:
            r=info['row']
            if r<=scan_rows and ws.Application.WorksheetFunction.CountA(
                    ws.Range(ws.Cells(r,1),ws.Cells(r,scan_cols))):
                raise ECMBlocked(f'새 날짜 {info["date"]}를 입력할 {r}행에 사용자 데이터/수식이 있습니다. 입력 차단')
        for info in current['new_columns']:
            c=info['col']
            if c<=scan_cols and ws.Application.WorksheetFunction.CountA(
                    ws.Range(ws.Cells(1,c),ws.Cells(scan_rows,c))):
                raise ECMBlocked(f'신규 품목 {info["name"]}을 입력할 {c}열에 사용자 데이터/수식이 있습니다. 입력 차단')
        history=[]
        def put(cell, value):
            old=cell.Value2
            history.append((cell,old))
            cell.Value2=value
        try:
            if current['new_columns']:
                catalog_ws=wb.Worksheets('가격열설정')
                cat_last=int(catalog_ws.Cells(catalog_ws.Rows.Count,1).End(-4162).Row)
                for entry in current['new_columns']:
                    if entry['col']>16384:raise ECMBlocked('Excel 열 상한 초과')
                    col=entry['col']
                    put(ws.Cells(1,col),entry['name']);put(ws.Cells(2,col),entry['source'])
                    cat_last+=1
                    put(catalog_ws.Cells(cat_last,1),entry['key'])
                    put(catalog_ws.Cells(cat_last,2),entry['name'])
                    put(catalog_ws.Cells(cat_last,3),entry['description'])
            for entry in current['new_dates']:
                put(ws.Cells(entry['row'],1),entry['date'])
            from com_updates import put_blocks
            put_blocks(ws,current['edits'],history)
            # COM .Save is preferred to Ctrl+S, but does NOT prove ECM check-in.
            wb.Save()
            for e in current['edits']:
                v=ws.Cells(e['row'],e['col']).Value2
                valid=v in (None,'') if e['incoming'] is None else _decimal(v)==_decimal(e['incoming'])
                if not valid:
                    raise ECMBlocked(f'Excel 저장 후 셀 재검증 실패: {e["row"]}행 {e["col"]}열')
        except Exception as exc:
            rollback_errors=0
            for cell,old in reversed(history):
                try:cell.Value2=old
                except Exception:rollback_errors+=1
            raise ECMBlocked(
                f'ECM 저장/검증 실패: {exc}; 메모리 롤백 실패 {rollback_errors}셀. '
                '이미 디스크 저장이 일부 완료됐을 가능성을 배제할 수 없으므로 ECM에서 직접 확인하세요.') from exc
        log(f'ECM Excel Save 및 셀 검증 완료 ({len(current["edits"])}셀). 서버 반영/체크인 여부는 ECM에서 별도 확인 필요')
        return {'status':'LOCAL_SAVED_SERVER_UNVERIFIED','applied':len(current['edits']),
                'created_rows':len(current['new_dates']),'created_cols':len(current['new_columns']),
                'workbook':str(wb.Name),'sheet':sheet,'server_verified':False}



def write_json(path,content):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(content,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    tmp.replace(path)
