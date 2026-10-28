"""Bind a workbook to an observed ECM open event, not merely its basename."""
from pathlib import Path
from datetime import datetime,timezone
import json,os

def workbook_inventory():
    if os.name!='nt':raise RuntimeError('ECM Workbook 식별은 Windows Excel에서 실행하세요.')
    import pythoncom,win32com.client
    pythoncom.CoInitialize()
    try:
        try:excel=win32com.client.GetActiveObject('Excel.Application')
        except Exception:return []
        rows=[]
        for i in range(1,excel.Workbooks.Count+1):
            wb=excel.Workbooks(i)
            rows.append({'name':str(wb.Name),'full_name':str(wb.FullName),
                'excel_hwnd':int(excel.Hwnd),'read_only':bool(wb.ReadOnly)})
        return rows
    finally:pythoncom.CoUninitialize()

def _key(item):return str(item['full_name']).casefold(),int(item['excel_hwnd'])

def select_observed(before,after,expected_name,local_path=None,prior=None):
    from ecm_names import file_matches
    before_keys={_key(x) for x in before}
    local=os.path.normcase(os.path.abspath(str(local_path))) if local_path else None
    candidates=[x for x in after if file_matches(x['name'],expected_name,allow_generated=True) and not x['read_only']
                and (not local or os.path.normcase(os.path.abspath(x['full_name']))!=local)]
    fresh=[x for x in candidates if _key(x) not in before_keys]
    if len(fresh)==1:return dict(fresh[0],origin='observed_ecm_open')
    if not fresh and prior:
        known=[x for x in candidates if _key(x)==_key(prior) and prior.get('origin')=='observed_ecm_open']
        if len(known)==1:return dict(known[0],origin='observed_ecm_open')
    raise RuntimeError('ECM에서 새로 열린 쓰기 가능한 통합문서를 유일하게 식별하지 못했습니다. 같은 이름의 로컬 사본을 닫고 ECM에서 다시 여세요. 여러 Excel 인스턴스도 확인하세요.')

def bind_open(folder,expected_name,local_path,open_action):
    from FastmarketsCollector_v3_4 import atomic_text
    path=Path(folder)/'ecm_document_binding.json'
    prior=None
    try:prior=json.loads(path.read_text('utf8'))
    except (OSError,ValueError):pass
    before=workbook_inventory()
    open_action()
    after=workbook_inventory()
    bound=select_observed(before,after,expected_name,local_path,prior)
    bound['observed_at']=datetime.now(timezone.utc).isoformat()
    with atomic_text(path) as fp:json.dump(bound,fp,ensure_ascii=False,indent=2)
    return bound
