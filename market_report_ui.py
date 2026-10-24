"""Read-only grouped presentation derived from the SAME frozen report snapshot.

No downloads, browser access, or price creation; charts omit unverified/missing
rows and never join price series with different units on a shared scale.
"""
from __future__ import annotations

import math
from datetime import date

from market_catalog import GROUPS, identify_series, friendly_product


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def dashboard_payload(context):
    """Serializable report UI, constructed without mutating context or source sheets."""
    specs = [
        {"id": group, "title": title, "sources": list(sources), "series": [],
         "status": "수집 데이터 없음"}
        for group, title, sources in GROUPS
    ]
    groups = {item["id"]: item for item in specs}
    sheets = context._sheets
    daily = tuple(sheets.get("일별시세", ()))
    catalogue = tuple(sheets.get("가격열설정", ()))
    meta = {}
    for item in catalogue[1:]:
        if len(item) >= 3 and isinstance(item[0], str):
            meta[str(item[0])] = str(item[2] or "")
    # Daily row1 labels, row2 source, row3+ validated distinct source dates.
    # Column identity uses catalogue order, not display labels that can change.
    series_keys = [str(row[0]) for row in catalogue[1:] if row and row[0]]
    if len(daily) >= 2:
        limit = min(len(series_keys), len(daily[0]) - 1, len(daily[1]) - 1)
        for column in range(1, limit + 1):
            key = series_keys[column - 1]
            group_id, title, source, unit, code = identify_series(key, meta.get(key, ""))
            if not key.startswith(("FMB|", "FX_", "NAVER|")):
                continue
            observations = {}
            for row in daily[2:]:
                if len(row) <= column:
                    continue
                day = str(row[0] or "")
                try:
                    date.fromisoformat(day)
                except ValueError:
                    continue
                value = _number(row[column])
                if value is None:
                    continue
                # Validated daily column is one fact per date; keep that identity.
                observations[day] = value
            points = [{"date": day, "value": observations[day]}
                      for day in sorted(observations)]
            groups[group_id]["series"].append({
                "key": key, "code": code, "name": title, "source": source,
                "unit": unit, "points": points,
                "as_of": points[-1]["date"] if points else "",
                "latest": points[-1]["value"] if points else None,
                "status": "검증 관측" if points else "검증된 자료 없음",
            })
            if points:
                groups[group_id]["status"] = "검증 관측"
            elif groups[group_id]["status"] != "검증 관측":
                groups[group_id]["status"] = "검증된 자료 없음"

    # Ranked equity snapshots are not historical per-stock closing-price series.
    cap = context.tables.get("보고용_시총", ())
    rankings = []
    for row in cap[1:] if cap else ():
        if len(row) < 8:
            continue
        rank, name, code, day, value, unit, status, source = row[:8]
        if value is not None and status in ("final", "stale"):
            rankings.append({
                "rank": rank, "name": str(name), "code": str(code),
                "date": str(day), "value": _number(value),
                "unit": str(unit), "status": str(status), "source": str(source),
            })
    # Top 10 is from one confirmed date, with the POSCO additional row unranked.
    return {
        "groups": specs,
        "rankings_kr": rankings,
        "rankings_us": [],
        "as_of": context.as_of,
        "snapshot_id": context.snapshot_id,
        "source_gaps": [
            "LME 독립 수집 단계 없음 — NAVER 니켈 시세를 공식 LME 정산가격으로 대체하지 않음",
            "GFEX·SMM·중국은행 개별 원천 미연결: 가격은 공란 유지",
            "미국 개별 주식·ETF 순위는 검증된 저장 소스가 없어 아직 표시하지 않음",
        ],
    }
