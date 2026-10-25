# -*- coding: utf-8 -*-
"""Short, unambiguous market-series captions. Code is the permanent identity.

Descriptions are authoritative; user-facing captions are deliberately compact.
When an unknown description cannot be classified reliably, display its symbol
rather than inventing a benchmark or origin. Full source text stays in catalog.
"""
from __future__ import annotations
import re
from smbs_rates import FMB_SHORT_NAMES, report_series_label


def description_key(text):
    return re.sub(r'\s+', ' ', re.sub(r'^MB-[A-Z0-9-]+:\s*', '', str(text or ''), flags=re.I)).strip()


def compact_series_label(key: str, description: str = '') -> str:
    if not key.startswith('FMB|'):
        return report_series_label(key)
    parts=key.split('|')
    if len(parts)!=5:
        return key
    _, code, unit, mode, field=parts
    if code in FMB_SHORT_NAMES:
        name=FMB_SHORT_NAMES[code]
    else:
        d=description_key(description).lower()
        # Avoid claiming a specific geography/unit when metadata is incomplete.
        material=('LC' if 'lithium carbonate' in d else
                  'LiOH' if 'lithium hydroxide' in d else
                  'Co' if 'cobalt' in d and 'black mass' not in d else
                  'Ni' if 'nickel' in d and 'black mass' not in d else
                  'Mn' if 'manganese' in d and 'black mass' not in d else None)
        if 'black mass' in d:
            chem=('LCO' if re.search(r'\blco\b',d) else
                  'NCM' if re.search(r'\bncm\b',d) else 'BM')
            metal=(' Ni' if 'payable indicator, nickel' in d else
                   ' Co' if 'payable indicator, cobalt' in d else
                   ' Li' if 'payable indicator, lithium' in d else '')
            region=(' KR' if 'south korea' in d else
                    ' EU' if 'europe' in d else '')
            if not region:
                name=code
            else:
                name=f'BM({chem}{metal}){region}'
        elif material:
            name=material + ('(RTM)' if 'rotterdam' in d else '')
        else:
            name=code
    suffix=('(전망)' if mode.casefold()=='forecast' else
            '(월평균)' if mode.casefold()=='monthly average' else '')
    if field!='MID':
        suffix += {'LOW':'(하한)','HIGH':'(상한)'}.get(field, f'({field})')
    return name+suffix


def catalogue_description(key: str, description: str = '') -> str:
    if key.startswith('FX_'):
        return '서울외국환중개 매매기준율; '+key
    p=key.split('|')
    unit=p[2] if len(p)>2 else ''
    mode=p[3] if len(p)>3 else ''
    return f'{description_key(description)} | 단위 {unit} | {mode}'


def product_info(code, description, unit, mode):
    """Classify only the supplied description; never infer LME/grade from a code.

    This is a presentation catalogue, NOT a cross-provider price mapping. The
    verbatim normalized source description remains the contract specification.
    Existing compact Excel column aliases/keys intentionally remain untouched.
    """
    original=description_key(description);d=original.casefold()
    name='품목명 확인 필요';group='미분류'
    if 'black mass' in d:
        group='블랙매스';name='블랙매스'
        for chem in ('NCM','NCA','LCO'):
            if re.search(r'\b'+chem+r'\b',original,re.I):name+=' '+chem
        if 'payable' in d:
            name+=' Payable'
            name+=(' · Ni' if 'nickel' in d else ' · Co' if 'cobalt' in d else ' · Li' if 'lithium' in d else '')
    else:
        for phrase,group_name,title in (
            ('lithium carbonate','리튬','탄산리튬'),('lithium hydroxide','리튬','수산화리튬'),
            ('nickel sulfate','니켈','황산니켈'),('nickel sulphate','니켈','황산니켈'),
            ('cobalt sulfate','코발트','황산코발트'),('cobalt sulphate','코발트','황산코발트'),
            ('nickel','니켈','니켈'),('cobalt','코발트','코발트'),
            ('manganese','망간','망간'),('copper','구리','구리')):
            if phrase in d:group=group_name;name=title;break
        if 'battery grade' in d and group!='미분류':name='전지급 '+name
    return dict(code=code,name=name,group=group,
                conditions=' · '.join(v for v in (original,'FMB',str(unit or '단위 미확인'),str(mode or '구분 미확인')) if v))
