"""SMM snapshot projection and user-defined Ni equivalent, no database reads."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
import math
from smm_public import COLUMNS,TARGETS,checked_row,nickel_equivalent

NI_EQ='SMM-NI-NC-001_NI_EQ_2232'


def projections(rows):
    result=[]
    for row in rows:
        row=checked_row(row)
        name,group,_,_=TARGETS[row['code']]
        value=float(Decimal(row['value'])) if row['value'] is not None else None
        if value is not None and not math.isfinite(value):raise ValueError('SMM display value overflow')
        common=dict(date=row['market_date'],source='SMM',source_url=row['assessment_url'],group=group,
            conditions='SMM 공개 홈페이지 평균 · USD 표시 · VAT 기준 미확인',view_key='public_homepage_average')
        result.append(dict(common,code=row['code'],name=name,unit='USD/t',mode='Actual',value=value))
        if row['code']=='SMM-NI-NC-001':
            equivalent=float(Decimal(nickel_equivalent(row['value']))) if value is not None else None
            result.append(dict(common,code=NI_EQ,name='황산니켈 · 니켈 환산 (22.32%)',unit='USD/t Ni',mode='Derived',value=equivalent,
                conditions=common['conditions']+' · 원시세 / 0.2232 · 사용자 지정 함량, 니켈 현물시세 아님'))
    return result


def series_from_rows(rows):
    grouped={}
    for item in projections(rows):
        key='SMM|'+item['code']+'|'+item['unit']+'|'+item['mode']+'|AVG'
        entry=grouped.setdefault(key,dict(item,id=key,points=[]))
        entry['points'].append(dict(date=item['date'],value=item['value'],status='observed' if item['value'] is not None else 'conflict'))
    for entry in grouped.values():
        entry.pop('date');entry.pop('value');entry['points'].sort(key=lambda p:p['date'])
    return list(grouped.values())


def add_to_snapshot(rows,sheets,tables):
    """Only the caller's transaction-filtered rows enter any output."""
    if not rows:return
    sheets['SMM_시세원본']=[COLUMNS]+[tuple(r[k] for k in COLUMNS) for r in rows]
    points=projections(rows);latest={}
    for point in sorted(points,key=lambda p:p['date']):latest[point['code']]=point
    tables['보고용_SMM']=[('품목명','고시일','Mid','단위','구분','출처','코드','그룹','원본 조건')]+[
        (p['name'],p['date'],p['value'],p['unit'],p['mode'],p['source_url'],p['code'],p['group'],p['conditions']) for p in latest.values()]
    keys=sorted({'SMM|'+p['code']+'|'+p['unit']+'|'+p['mode']+'|AVG' for p in points})
    names={('SMM|'+p['code']+'|'+p['unit']+'|'+p['mode']+'|AVG'):p['name'] for p in points}
    daily=defaultdict(dict)
    for p in points:daily[p['date']]['SMM|'+p['code']+'|'+p['unit']+'|'+p['mode']+'|AVG']=p['value']
    catalog=sheets.setdefault('가격열설정',[('키','품목','설명')])
    catalog.extend((key,names[key],'SMM · 공개 평균 / 파생 환산 별도') for key in keys)
    old=sheets.get('일별시세',[('고시일',),('출처',)])
    width=len(old[0])-1;previous={r[0]:list(r[1:]) for r in old[2:]}
    all_days=sorted(set(previous)|set(daily))
    headers=[tuple(old[0])+tuple(names[k] for k in keys),tuple(old[1])+tuple('SMM' for k in keys)]
    result=headers+[tuple([day]+previous.get(day,[None]*width)+[daily[day].get(k) for k in keys]) for day in all_days]
    sheets['일별시세']=result;sheets['일별요약']=list(result)
    accumulated=defaultdict(lambda:defaultdict(list))
    for row in result[2:]:
        for i,v in enumerate(row[1:]):
            if isinstance(v,(int,float)):accumulated[row[0][:7]][i].append(v)
    for name,count in (('월별시세',False),('월별건수',True)):
        sheets[name]=[('기준월',)+result[0][1:],result[1]]+[
            tuple([month]+[(len(accumulated[month][i]) if count else sum(accumulated[month][i])/len(accumulated[month][i]))
                if accumulated[month][i] else (0 if count else None) for i in range(len(result[0])-1)])
            for month in sorted({r[0][:7] for r in result[2:]})]
    for day,values in daily.items():
        for key,value in values.items():
            if value is None:
                held=sheets.setdefault('보류셀',[('시트','날짜','키','사유')])
                for tab in ('일별시세','일별요약'):held.append((tab,day,key,'SMM 공개 행 충돌'))
                column=width+keys.index(key)
                if not accumulated[day[:7]][column]:held.append(('월별시세',day[:7],key,'SMM 충돌 후 검증된 월별 표본 없음'))
