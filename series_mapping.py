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
    if len(p)>2 and p[0]=='FMB' and p[1] in ('MB-CO-0005','MB-LI-0029','MB-LI-0033'):
        factor='× 2204.62262185' if p[1]=='MB-CO-0005' and unit.replace(' ','')=='$/lb' else '× 1000' if unit.replace(' ','')=='$/kg' else ''
        if factor:
            return f'{description_key(description)} | 원본 단위 {unit}; 일별·월별/보고용 USD/tonne ({factor}) | {mode}'
    return f'{description_key(description)} | 원본·보고 단위 {unit} | {mode}'
