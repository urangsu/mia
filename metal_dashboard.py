"""Read-only metal view model from a frozen ReportContext; no new DB reads."""
from calendar import monthrange
from collections import defaultdict
from datetime import date
import math
from series_mapping import product_info

GROUPS=('리튬','니켈','코발트','망간','구리','블랙매스','미분류')


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
    result.sort(key=lambda s:(GROUPS.index(s['group']),s['name'],s['unit'],s['mode'],s['view_key']))
    coverage=[dict(source='FMB',product=g,status='captured' if observed[g] else 'missing',count=observed[g],
                   reason='저장 관측; 전체 작업공간 검증은 별도' if observed[g] else '현재 워크스페이스 저장 관측 없음') for g in GROUPS[:-1]]
    coverage.extend(dict(source=s,product=p,status='unsupported',count=0,reason='허용 경로·계약·수집 근거 미확보; 타 출처로 대체하지 않음')
                    for s,p in (('LME','니켈 Cash/3M·구리·코발트'),('SMM','VAT 포함/제외'),('GFEX','탄산리튬 계약월별 선물')))
    return dict(snapshot_id=context.snapshot_id,series=result,coverage=coverage)
