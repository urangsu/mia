# -*- coding: utf-8 -*-
"""Human-readable market catalogue. This is a display taxonomy, NOT a new price source.

Series codes are immutable identities. Never infer an exchange/benchmark from an
unverified description, and never synthesize prices for unavailable sources.
"""
from __future__ import annotations
import re

GROUPS = (
    ("lithium_carbonate", "전지급 탄산리튬 (Li₂CO₃)", ("Fastmarkets CIF", "GFEX 선물", "SMM 함세가", "SMM 세전가")),
    ("lithium_hydroxide", "전지급 수산화리튬 (LiOH)", ("Fastmarkets CIF", "SMM 함세가", "SMM 세전가")),
    ("nickel", "니켈 (Ni)", ("LME", "SMM", "Fastmarkets")),
    ("nickel_sulfate", "황산니켈 (Nickel Sulfate)", ("LME Ni × 22.3% (검증 후 파생)", "SMM 황산니켈 환산 함세", "SMM 황산니켈 환산 세전")),
    ("cobalt", "코발트 (Co)", ("LME", "Fastmarkets")),
    ("cobalt_sulfate", "황산코발트 (Cobalt Sulfate)", ("LME Co × 20.9% (검증 후 파생)", "FMB Co × 20.9% (검증 후 파생)", "SMM 황산코발트 환산 함세", "SMM 황산코발트 환산 세전")),
    ("manganese", "망간 (Mn)", ("SMM 함세", "SMM 세전", "Fastmarkets")),
    ("copper", "구리 (Cu)", ("LME", "SMM", "Fastmarkets")),
    ("bm_ncm", "Black Mass (NCM/NCA)", ("Fastmarkets CIF",)),
    ("bm_lco_payable", "Black Mass Payable (LCO · Co)", ("Fastmarkets % payable",)),
    ("bm_ncm_payable", "Black Mass Payable (NCM · Ni/Co)", ("Fastmarkets % payable",)),
    ("fx", "환율", ("서울외국환중개", "중국은행")),
    ("kr_market", "국내 증시", ("KOSPI", "KOSDAQ", "시가총액 순위")),
    ("us_market", "미국·글로벌 증시", ("S&P 500", "NASDAQ", "미국 주식·ETF", "NYSE/NASDAQ/AMEX")),
    ("other", "그 밖의 수집 시리즈", ()),
)

# Verified display labels; never substitute a different commodity for these codes.
KNOWN_FMB = {
    "MB-LI-0029": ("lithium_carbonate", "전지급 탄산리튬 · Fastmarkets CIF"),
    "MB-LI-0033": ("lithium_hydroxide", "전지급 수산화리튬 · Fastmarkets CIF"),
    "MB-CO-0005": ("cobalt", "코발트 · Fastmarkets Rotterdam"),
    "MB-MN-0001": ("manganese", "전해망간 플레이크 · Fastmarkets"),
    "MB-BMS-0001": ("bm_ncm_payable", "NCM Black Mass 니켈 Payable · 한국"),
    "MB-BMS-0002": ("bm_ncm_payable", "NCM Black Mass 코발트 Payable · 한국"),
    "MB-BMS-0003": ("bm_ncm_payable", "NCM Black Mass 리튬 Payable · 한국"),
    "MB-BMS-0004": ("bm_ncm_payable", "NCM Black Mass 니켈 Payable · 유럽"),
    "MB-BMS-0006": ("bm_lco_payable", "LCO Black Mass 코발트 Payable · 유럽"),
    "MB-BMS-0010": ("bm_lco_payable", "LCO Black Mass 코발트 Payable · 한국"),
    "MB-BMS-0011": ("bm_lco_payable", "LCO Black Mass 리튬 Payable · 한국"),
    "MB-BMS-0012": ("bm_ncm", "고코발트 NCM Black Mass 추정가격 · 한국"),
}
MARKET_NAMES = {
    "KOSPI": "코스피", "KOSDAQ": "코스닥", "SP500": "S&P 500",
    "NASDAQ": "나스닥 종합", "US10Y": "미국 국채 10년",
    "KR10Y": "한국 국채 10년", "GOLD": "국제 금", "WTI": "WTI 원유",
}
FX_NAMES = {"USD": "미국 달러", "CNH": "중국 위안(역외)", "JPY": "일본 엔", "EUR": "유로"}

def _normal(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()

def describe_fmb(code, description=""):
    code = str(code or "").upper()
    if code in KNOWN_FMB:
        return KNOWN_FMB[code]
    desc = re.sub(r"^MB-[A-Z0-9-]+:\s*", "", _normal(description), flags=re.I)
    d = desc.lower()
    if not d:
        return "other", "미분류 Fastmarkets 시세 (품목 확인 필요)"
    if "black mass" in d:
        if "payable" in d:
            group = "bm_lco_payable" if re.search(r"\blco\b", d) else "bm_ncm_payable"
        else:
            group = "bm_ncm"
    elif "lithium carbonate" in d:
        group = "lithium_carbonate"
    elif "lithium hydroxide" in d:
        group = "lithium_hydroxide"
    elif "nickel sulphate" in d or "nickel sulfate" in d:
        group = "nickel_sulfate"
    elif "cobalt sulphate" in d or "cobalt sulfate" in d:
        group = "cobalt_sulfate"
    elif "nickel" in d:
        group = "nickel"
    elif "cobalt" in d:
        group = "cobalt"
    elif "manganese" in d:
        group = "manganese"
    elif "copper" in d:
        group = "copper"
    else:
        group = "other"
    return group, desc[:110]

def identify_series(key, description=""):
    key = str(key or "")
    if key.startswith("FMB|"):
        parts = key.split("|")
        if len(parts) != 5:
            return "other", "확인되지 않은 금속 시세", "FMB", "", key
        _, code, unit, mode, field = parts
        group, name = describe_fmb(code, description)
        qualifier = (" · 전망" if mode == "Forecast" else
                     " · 월평균" if mode == "Monthly Average" else "")
        return group, name + qualifier + (" · " + field if field != "MID" else ""), "FMB", unit, code
    if key.startswith("FX_"):
        match = re.fullmatch(r"FX_([A-Z]{3})_KRW_per_(\d+)", key)
        if match:
            code, amount = match.groups()
            return "fx", FX_NAMES.get(code, code) + (" (100단위)" if amount == "100" else ""), "SMBS", "KRW", code
    if key.startswith("NAVER|"):
        parts = key.split("|")
        if len(parts) >= 3:
            code = parts[1]
            group = "us_market" if code in ("SP500", "NASDAQ", "US10Y") else "kr_market" if code in ("KOSPI", "KOSDAQ", "KR10Y") else "other"
            return group, MARKET_NAMES.get(code, "확인 필요: " + code), "NAVER", parts[2], code
    return "other", "미분류 시리즈 (출처 확인 필요)", "미확인", "", key

def friendly_product(code, description=""):
    return describe_fmb(code, description)[1]
