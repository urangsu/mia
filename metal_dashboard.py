"""Read-only metal view model from a frozen ReportContext; no new DB reads."""
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import math
from urllib.parse import urlparse
from series_mapping import product_info

GROUPS=('리튬','니켈','코발트','망간','구리','블랙매스','미분류')
LME_METALS={'Nickel':('NI','니켈'),'Copper':('CU','구리'),'Cobalt':('CO','코발트')}


def _lme_series(sheets):
    """Read only the same frozen official rows as the report, never FMB aliases."""
    raw=sheets.get('LME_공식원본',());series={}
    for cells in raw[1:]:
        row=dict(zip(raw[0],cells))
        metal=row.get('metal');contract=row.get('contract');side=row.get('side')
        if metal not in LME_METALS or contract not in ('Cash','3-month') or side not in ('Ask','Bid'):continue
        code,group=LME_METALS[metal]
        instrument=f'LME_{code}_{"CASH" if contract=="Cash" else "3M"}_{side.upper()}'
        settlement=contract=='Cash' and side=='Ask'
        if (row.get('instrument_id')!=instrument or row.get('unit')!='USD/t' or
            row.get('currency')!='USD' or row.get('price_type')!='Official' or
            row.get('is_settlement') not in ((True,1) if settlement else (False,0))):continue
        try:
            source=urlparse(row.get('source_url') or '')
            if (source.scheme!='https' or source.hostname!='www.lme.com' or source.username or source.password or
                source.port not in (None,443) or source.path!='/Market-data/Reports-and-data/LME-Official-Prices'):continue
            day=date.fromisoformat(row.get('market_date') or '').isoformat()
        except (ValueError,TypeError):continue
        identity=f'LME|{instrument}|USD/t|Official|{side}'
        label=group+' '+contract+' '+side+' · '+('Official Settlement' if settlement else 'Official')
        entry=series.setdefault(identity,dict(id=identity,code=instrument,name=label,group=group,
            conditions='LME Official · '+contract+' · '+side+(' · Official Settlement' if settlement else '')+' · USD/t',
            unit='USD/t',mode='Official',source='LME',source_url=row['source_url'],view_key=contract+'|'+side,
            contract=contract,side=side,is_settlement=settlement,_points={},_facts={}))
        value=None;fact=None
        try:
            number=Decimal(str(row.get('value')))
            if not isinstance(row.get('value'),bool) and number.is_finite() and number>0:
                display=float(number)
                if math.isfinite(display) and display>0:value=display;fact=number
        except (InvalidOperation,ValueError,TypeError,OverflowError):pass
        point=dict(date=day,value=value,status='observed' if value is not None else 'missing_or_quarantined')
        prior=entry['_points'].get(day)
        if prior and (entry['_facts'][day]!=fact or prior['status']=='conflict'):
            point.update(value=None,status='conflict')
        entry['_points'][day]=point
        entry['_facts'][day]=fact
    result=[]
    for entry in series.values():
        entry['points']=sorted(entry.pop('_points').values(),key=lambda p:p['date'])
        entry.pop('_facts')
        result.append(entry)
    return result


def filter_points(points,*,months=None,start=None,end=None):
    def boundary(value,last=False):
        if not value:return None
        if len(value)==7:
            year,month=map(int,value.split('-'))
            return date(year,month,monthrange(year,month)[1] if last else 1).isoformat()
        return date.fromisoformat(value).isoformat()
    end=boundary(end,True) or max((p['date'] for p in points),default=None)
    start=boundary(start)
    if months and end and not start:
        d=date.fromisoformat(end);index=d.year*12+d.month-1-int(months)
        year,month=divmod(index,12);month+=1
        start=date(year,month,min(d.day,monthrange(year,month)[1])).isoformat()
    if start and end and start>end:raise ValueError('시작월은 종료월보다 늦을 수 없습니다.')
    return [p for p in points if (not start or p['date']>=start) and (not end or p['date']<=end)]


def dashboard_data(context):
    sheets=context._sheets;raw=sheets.get('RawData',());series={};observed=defaultdict(int)
    # The daily view already applies cross-view conflict quarantine. Do not plot
    # a raw cached Mid that the shared numerical report has withheld.
    daily=sheets.get('일별시세',());catalog=sheets.get('가격열설정',())
    keys=[r[0] for r in catalog[1:]]
    validated={(row[0],key):row[i+1] for row in daily[2:] for i,key in enumerate(keys) if i+1<len(row)}
    for row in raw[1:]:
        p=dict(zip(raw[0],row))
        if p['period_label'] or p['price_mode'] not in ('Actual','Forecast','Unspecified'):continue
        code=p['symbol'];key=f"FMB|{code}|{p['unit']}|{p['price_mode']}|MID"
        identity=(key,p['view_key']);info=product_info(code,p['description'],p['unit'],p['price_mode'])
        entry=series.setdefault(identity,dict(info,id=repr(identity),unit=p['unit'],mode=p['price_mode'],
            source='FMB',source_url=p['source'],view_key=p['view_key'],_points={}))
        value=validated.get((p['date'],key))
        if not isinstance(value,(int,float)) or not math.isfinite(value):value=None
        try:raw_value=float(p['mid'])
        except (ValueError,TypeError,OverflowError):raw_value=None
        # The shared value may veto a conflicting view, never fill its gap.
        if raw_value is None or not math.isfinite(raw_value) or raw_value!=value:value=None
        point=dict(date=p['date'],value=value,status='observed' if value is not None else 'missing_or_quarantined')
        prior=entry['_points'].get(p['date'])
        if prior and prior['value']!=value:point.update(value=None,status='conflict')
        entry['_points'][p['date']]=point
    result=[]
    for entry in series.values():
        entry['points']=sorted(entry.pop('_points').values(),key=lambda p:p['date'])
        observed[entry['group']]+=1;result.append(entry)
    lme=_lme_series(sheets);result.extend(lme)
    def order(entry):
        if entry['source']=='LME':
            return (GROUPS.index(entry['group']),0,0 if entry['side']=='Ask' else 1,
                    0 if entry['contract']=='Cash' else 1,entry['name'])
        return (GROUPS.index(entry['group']),1,entry['name'],entry['unit'],entry['mode'],entry['view_key'])
    result.sort(key=order)
    coverage=[dict(source='FMB',product=g,status='captured' if observed[g] else 'missing',count=observed[g],
                   reason='저장 관측; 전체 작업공간 검증은 별도' if observed[g] else '현재 워크스페이스 저장 관측 없음') for g in GROUPS[:-1]]
    for _,group in LME_METALS.values():
        valid=[s for s in lme if s['group']==group and any(p['value'] is not None for p in s['points'])]
        asks={s['contract'] for s in valid if s['side']=='Ask'}
        coverage.append(dict(source='LME',product=group+' Official Cash/3-month · Ask/Bid',
            status='captured' if len(asks)==2 else 'partial' if valid else 'missing',count=len(valid),
            reason=('저장된 LME Official 계약·호가별 관측; Cash Ask만 Settlement, Bid/Ask 평균 없음' if len(asks)==2 else
                    '일부 계약·호가만 저장됨; 누락 가격을 다른 출처로 대체하지 않음' if valid else
                    '공개 Official 수집 경로 구현; 저장 관측 없음 또는 유효한 계약·단위·가격 근거 없음')))
    coverage.extend(dict(source=s,product=p,status='unsupported',count=0,reason='허용 경로·계약·수집 근거 미확보; 타 출처로 대체하지 않음')
                    for s,p in (('SMM','VAT 포함/제외'),('GFEX','탄산리튬 계약월별 선물')))
    return dict(snapshot_id=context.snapshot_id,series=result,coverage=coverage)
