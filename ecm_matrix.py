"""Photo-compatible ECM matrix planner: headers1/3, dates ABC, body starts5.

No COM/writes here. No row/column insertion, TODAY updates, inferred VAT,
forward fills, or ambiguous product selection. Existing two-header layout stays separate.
"""
from datetime import date
from decimal import Decimal
import hashlib
import json
import re
from ecm_excel_sync import ECMBlocked,_decimal,date_key,series_source


def _norm(value):
    return re.sub(r'[\s_()·/\-]','',str(value or '')).casefold()


def is_photo_matrix(rows):
    return len(rows)>=3 and [_norm(v) for v in rows[2][:3]]==['연도','월','일']


def _source(row):
    text=_norm(row)
    for source in ('fmb','lme','smm','gfex'):
        if source in text:return source.upper()
    return None


def _candidates(name,detail,source,catalog):
    text=_norm(str(name or '')+' '+str(detail or ''))
    if source=='SMM':
        code=('SMM-Li-LC-001' if '탄산리튬' in text else 'SMM-NI-NC-001_NI_EQ_2232' if '니켈' in text
              else 'SMM-CO-CM-001' if '코발트' in text else None)
        return [key for key in catalog if key.startswith('SMM|'+str(code)+'|')] if code else []
    if source=='LME':
        metal='NI' if '니켈' in text else 'CU' if '구리' in text else 'CO' if '코발트' in text else None
        contract='3M' if any(word in text for word in ('3개월','3month','3m')) else 'CASH'
        return [key for key in catalog if key.startswith('LME|LME_'+str(metal)+'_'+contract+'_ASK|')]
    if source!='FMB':return []
    product=next((aliases for token,aliases in (
        ('탄산리튬',('carbonate','탄산리튬')),('수산화리튬',('hydroxide','수산화리튬')),
        ('니켈',('nickel','니켈')),('코발트',('cobalt','코발트')),('망간',('manganese','망간')),
        ('구리',('copper','구리')),('bmpayable',('payable',)),('블랙매스',('blackmass','블랙매스')))
        if token in text),None)
    if product is None:return []
    result=[]
    for key,label in catalog.items():
        parts=key.split('|');words=_norm(label)
        if len(parts)<5 or parts[0]!='FMB' or parts[3]=='Forecast' or parts[-1]!='MID':continue
        if not any(word in words for word in product):continue
        if 'cif' in _norm(source) and 'cif' not in words:continue
        if 'payable' in text:
            if 'payable' not in words:continue
            if 'lco' in text and 'lco' not in words:continue
            if ('ncm' in text or 'nca' in text) and not any(token in words for token in ('ncm','nca')):continue
        result.append(key)
    return result


def _column_letter(index):
    name=''
    while index:index,rem=divmod(index-1,26);name=chr(65+rem)+name
    return name


def build_matrix_plan(source_rows,source_catalog,target_rows,*,column_map=None,clear_cells=()):
    if not is_photo_matrix(target_rows):raise ECMBlocked('사진 양식은 A3=연도, B3=월, C3=일이어야 합니다.')
    if len(source_rows)<2:raise ECMBlocked('저장 원자료의 날짜/품목 헤더가 없습니다.')
    catalog={str(r[0]):' '.join(str(v) for v in r[1:] if v is not None) for r in source_catalog[1:]}
    keys=[str(r[0]) for r in source_catalog[1:]]
    if len(keys)!=len(set(keys)):raise ECMBlocked('원자료 가격열설정 key 중복')
    mapping={};warnings=[];unmapped=[];width=max(len(r) for r in target_rows[:3]);column_map=column_map or {}
    for col in range(4,width+1):
        letter=_column_letter(col)
        header=[r[col-1] if col<=len(r) else None for r in target_rows[:3]]
        name,detail,origin=header;source=_source(origin);label=' / '.join(str(v) for v in header if v)
        if not label:continue
        vat=_norm(origin)
        if source=='SMM' and any(token in vat for token in ('증x','증치세제외','vat제외','vatexcluded','부가세제외')):
            candidates=[];reason='증치세 제외 열: 사용자 요청으로 이번 입력에서 제외 (기존 셀 유지)'
        else:
            currency=next((code for tokens,code in ((('달러','usd'),'USD'),(('위안','cnh','cny'),'CNH'),(('유로','eur'),'EUR'),(('엔화','jpy'),'JPY'))
                if any(token in _norm(name) for token in tokens)),None)
            if currency:
                candidates=[key for key in catalog if key=='FX_'+currency+'_KRW_per_'+('100' if currency=='JPY' else '1')]
            else:candidates=_candidates(name,detail,source,catalog)
            if source=='FMB' and 'cif' in _norm(origin):
                candidates=[key for key in candidates if 'cif' in catalog[key].casefold()]
            explicit=column_map.get(letter)
            if explicit:
                if explicit not in candidates:raise ECMBlocked(letter+'열 수동 연결이 머리글/출처 후보와 다릅니다.')
                candidates=[explicit]
            reason='연결 후보 '+str(len(candidates))+'개: '+', '.join(candidates)
        if len(candidates)==1:mapping[col]=dict(key=candidates[0],header=label,source=series_source(candidates[0]))
        else:
            unmapped.append(dict(column=letter,header=label,reason=reason));warnings.append(letter+'열 '+label+': '+reason)
    if not mapping:raise ECMBlocked('자동 연결 가능한 금속/환율 열이 없습니다. '+'; '.join(warnings))
    dates={}
    for rownum,row in enumerate(target_rows[4:],5):
        values=list(row[:3])
        if not any(v not in (None,'') for v in values):continue
        try:
            if len(values)!=3 or any(isinstance(v,bool) or Decimal(str(v))!=int(Decimal(str(v))) for v in values):raise ValueError()
            day=date(*(int(Decimal(str(v))) for v in values)).isoformat()
        except (ValueError,TypeError,ArithmeticError):raise ECMBlocked(str(rownum)+'행 ABC 날짜가 유효하지 않습니다.')
        if day in dates:raise ECMBlocked('5행 이후 날짜 중복: '+day+' ('+str(dates[day])+', '+str(rownum)+'행)')
        dates[day]=rownum
    edits=[];unchanged=missing=0;clears=set(clear_cells);seen=set()
    for row in source_rows[2:]:
        day=date_key(row[0])
        if day in seen:raise ECMBlocked('저장 원자료 날짜 중복: '+day)
        seen.add(day)
        if day not in dates:
            warnings.append(day+': 대상 날짜 행 없음, 행을 추가하지 않음');continue
        rownum=dates[day]
        for col,entry in mapping.items():
            index=keys.index(entry['key'])+1
            value=_decimal(row[index]) if index<len(row) else None
            old=target_rows[rownum-1][col-1] if col<=len(target_rows[rownum-1]) else None
            previous=_decimal(old)
            clear=value is None and (day,entry['key']) in clears
            if value is None and not clear:missing+=1;continue
            if old not in (None,'') and previous is None:raise ECMBlocked(f'{rownum}행 {col}열 수식/사용자 텍스트 보호')
            if (value==previous and old not in (None,'')) or (clear and old in (None,'')):
                unchanged+=1;continue
            decision='quarantine' if clear else 'fill' if old in (None,'') else 'correction'
            edits.append(dict(date=day,key=entry['key'],header=entry['header'],source=entry['source'],row=rownum,col=col,
                previous=float(previous) if previous is not None else None,incoming=float(value) if value is not None else None,decision=decision))
    digest=lambda value:hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()
    return dict(layout='photo_abc_5',column_map=column_map,mapping={str(k):v for k,v in mapping.items()},
        warnings=warnings,unmapped_columns=unmapped,new_dates=[],new_columns=[],edits=edits,
        source_digest=digest(source_rows),target_digest=digest(target_rows),catalog_digest=digest(source_catalog),
        stats=dict(new_dates=0,new_columns=0,fill=sum(e['decision']=='fill' for e in edits),
            correction=sum(e['decision']=='correction' for e in edits),cleared=sum(e['decision']=='quarantine' for e in edits),
            unchanged=unchanged,missing_source=missing),src_count=len(seen),target_count=len(dates))
