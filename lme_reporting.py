# -*- coding: utf-8 -*-
"""LME workbook projection and reproducible daily metal-report tables.

All functions are pure: they use immutable SQLite observations already selected
by report_model, never re-fetch remote pages or rewrite original FMB units.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from math import isfinite

LME_SPECS = (
    ("LME|NI|CASH|USD/t", "LME Ni", "USD/tonne", "cash_usd_t", "NI"),
    ("LME|CU|CASH|USD/t", "LME Cu", "USD/tonne", "cash_usd_t", "CU"),
    ("LME|NI|3M|USD/t", "LME Ni(3M)", "USD/tonne", "three_month_usd_t", "NI"),
    ("LME|CU|3M|USD/t", "LME Cu(3M)", "USD/tonne", "three_month_usd_t", "CU"),
    ("LME|NI|STOCK|tonne", "LME Ni재고", "tonne", "stock_t", "NI"),
    ("LME|CU|STOCK|tonne", "LME Cu재고", "tonne", "stock_t", "CU"),
)

def _number(v):
    try:
        x=float(v)
        return x if isfinite(x) else None
    except (TypeError, ValueError):
        return None

def add_lme_sheets(sheets, observations, *, selected=None):
    """Append LME columns to the existing daily/monthly views without changing positions."""
    observations=[r for r in observations if r.get("source")=="WESTMETALL"]
    selected=set(selected) if selected is not None else None
    specs=[s for s in LME_SPECS if selected is None or
        s[0] in selected or s[4] in selected or s[1] in selected]
    sheets["LME_원본"]=[("고시일","금속","Cash USD/tonne","3개월 USD/tonne","재고 tonne","출처","URL","수집시각")]+[
        (r["price_date"],r["metal"],_number(r["cash_usd_t"]),_number(r["three_month_usd_t"]),
        _number(r["stock_t"]),r["source"],r["source_url"],r.get("captured_at",""))
        for r in sorted(observations,key=lambda r:(r["price_date"],r["metal"]))]
    if not observations or not specs:
        return
    by_date=defaultdict(dict)
    for r in observations:
        dt=r["price_date"]
        try:date.fromisoformat(dt)
        except ValueError:continue
        for key,label,unit,field,metal in specs:
            if r["metal"]==metal:
                val=_number(r.get(field))
                if val is not None:by_date[dt][key]=val
    sheets["가격열설정"].extend((key,label,f"WESTMETALL LME {unit}; source={key}")
        for key,label,unit,field,metal in specs)
    def extend_daily(name):
        old=sheets[name]
        keys=[k for k,_,_,_,_ in specs]
        dates=sorted(set(r[0] for r in old[2:])|set(by_date))
        oldmap={r[0]:tuple(r[1:]) for r in old[2:]}
        empty=(None,)*(len(old[0])-1)
        header=tuple(old[0])+tuple(s[1] for s in specs)
        sources=tuple(old[1])+tuple("WESTMETALL" for _ in specs)
        sheets[name]=[header,sources]+[tuple([dt]+list(oldmap.get(dt,empty))+
            [by_date[dt].get(k) for k in keys]) for dt in dates]
    for name in ("일별시세","일별요약"):
        extend_daily(name)
    by_month=defaultdict(lambda:defaultdict(list))
    for day,keys in by_date.items():
        for k,v in keys.items():by_month[day[:7]][k].append(v)
    for name,counts in (("월별시세",False),("월별건수",True)):
        old=sheets[name]
        oldmap={r[0]:tuple(r[1:]) for r in old[2:]}
        empty=(None,)*(len(old[0])-1)
        months=sorted(set(oldmap)|set(by_month))
        sheets[name]=[tuple(old[0])+tuple(s[1] for s in specs),
            tuple(old[1])+tuple("WESTMETALL" for _ in specs)]+[
            tuple([month]+list(oldmap.get(month,empty))+
                [(len(by_month[month][s[0]]) if counts else
                  sum(by_month[month][s[0]])/len(by_month[month][s[0]]))
                 if by_month[month][s[0]] else (0 if counts else None) for s in specs])
            for month in months]

def report_unit(key,raw_unit=""):
    if key.startswith("FMB|"):
        code=key.split("|")[1]
        if code in ("MB-CO-0005","MB-LI-0029","MB-LI-0033") and (
            raw_unit.replace(" ","").lower() in ("$/lb","$/kg","usd/lb","usd/kg")):
            return "USD/tonne"
    return raw_unit

def _targets(catalog):
    """Stable public report selection. SMM is absent until a verified source exists."""
    target=[]
    for key,name,full in catalog[1:]:
        if key.startswith("FMB|"):
            code=key.split("|")[1]
            mode=key.split("|")[3]
            if mode not in ("Actual","Unspecified") or not key.endswith("|MID"):
                continue
            if code in ("MB-LI-0029","MB-LI-0033","MB-CO-0005","MB-BMS-0012"):
                unit="USD/tonne"
            else:continue
        elif key in ("LME|NI|CASH|USD/t","LME|CU|CASH|USD/t"):
            unit="USD/tonne"
        elif key=="FX_USD_KRW_per_1":
            unit="KRW/USD"
        else:continue
        target.append((key,name,unit))
    return target

def build_business_tables(sheets,report_end=None):
    """Most recent five *published* days, previous comparable day, three calendar months."""
    daily=sheets["일별시세"]
    catalog=sheets["가격열설정"]
    names=[r[1] for r in catalog[1:]]
    targets=_targets(catalog)
    by_name={r[0]:{n:v for n,v in zip(daily[0][1:],r[1:])} for r in daily[2:] if
        not report_end or r[0]<=report_end}
    all_days=sorted((dt for dt,vals in by_name.items() if
        any(_number(vals.get(name)) is not None for _,name,_ in targets)))
    recent=all_days[-5:]
    recent_cols=recent+[""]*(5-len(recent))
    three_months=sorted({d[:7] for d in all_days})[-3:]
    three_cols=three_months+[""]*(3-len(three_months))
    table=[tuple(["품목","출처","단위"]+recent_cols+["전 고시 대비","증감률(%)"])]
    monthly=[tuple(["품목","출처","단위"]+three_cols)]
    sentences=[("품목","자동 문구","비교 고시일","상태")]
    for key,name,unit in targets:
        orig="FMB" if key.startswith("FMB|") else "WESTMETALL" if key.startswith("LME|") else "SMBS"
        samples=sorted((dt,_number(row.get(name))) for dt,row in by_name.items()
            if _number(row.get(name)) is not None)
        previous,current=(samples[-2:] if len(samples)>=2 else ([(None,None)]+samples) if samples else [(None,None),(None,None)])
        d0,v0=previous;d1,v1=current
        change=v1-v0 if v0 is not None and v1 is not None else None
        pct=(change/v0*100) if change is not None and v0 else None
        values={dt:v for dt,v in samples}
        table.append(tuple([name,orig,unit]+[values.get(d) for d in recent_cols]+[
            round(change,4) if change is not None else None,
            round(pct,4) if pct is not None else None]))
        rowmonths=defaultdict(list)
        for dt,v in samples:rowmonths[dt[:7]].append(v)
        monthly.append(tuple([name,orig,unit]+[
            sum(rowmonths[m])/len(rowmonths[m]) if rowmonths[m] else None
            for m in three_cols]))
        if v1 is None:
            msg="미고시";status="missing"
        elif change is None:
            msg=f"{orig} {name} : {v1:,.2f} {unit} (비교 고시자료 없음)"
            status="no_previous"
        else:
            arrow="△" if change<0 else "+" if change>0 else "-"
            delta=f"{arrow}{abs(change):,.2f}" if change else "-"
            p=f"{arrow}{abs(pct):.2f}%" if pct else "-"
            msg=f"{orig} {name} : {v1:,.2f} {unit} (전 고시 比 {delta} / {p})"
            status="complete"
        sentences.append((name,msg,d0 or "",status))
    return {"보고용_최근5일":table,"보고용_3개월평균":monthly,"보고용_문구":sentences}
