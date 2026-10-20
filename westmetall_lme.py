# -*- coding: utf-8 -*-
"""Westmetall public LME daily Cash, 3-month and warehouse stock collection.

Only public HTML with documented on-page figures; no Fastmarkets private API.
Do not infer an LME date from the collector's clock. Each observation carries
its own published date, physical units and source URL.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import re
import sqlite3
import urllib.request

SOURCE = "WESTMETALL"
BASE_URL = "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_{}_cash"
METALS = {"NI": "Ni", "CU": "Cu"}
DATE_RE = re.compile(r"^\s*(\d{1,2})\.\s*([A-Za-z]+)\s+(\d{4})\s*$")
MONTHS = {m.lower(): i for i, m in enumerate(
    ("January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"), 1)}
NUMBER_RE = re.compile(r"^-?\d{1,3}(?:,\d{3})*(?:\.\d+)?$|^-?\d+(?:\.\d+)?$")


class WestmetallError(RuntimeError):
    pass


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.in_row = False
        self.cell_depth = 0
        self.cells = []
        self.buf = []
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "tr":
            self.in_row = True
            self.cells = []
        elif self.in_row and tag in ("td", "th"):
            self.cell_depth += 1
            if self.cell_depth == 1:
                self.buf = []
    def handle_data(self, data):
        if self.in_row and self.cell_depth:
            self.buf.append(data)
    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.in_row and tag in ("td", "th") and self.cell_depth:
            self.cell_depth -= 1
            if not self.cell_depth:
                self.cells.append(re.sub(r"\s+", " ", "".join(self.buf)).strip())
        elif tag == "tr" and self.in_row:
            if self.cells:
                self.rows.append(tuple(self.cells))
            self.in_row = False
            self.cell_depth = 0


def _num(value):
    value = str(value).strip().replace("\u2212", "-").replace(" ", "")
    if not NUMBER_RE.fullmatch(value):
        return None
    try:
        num = Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None
    return num if num.is_finite() else None


def _date(raw):
    match = DATE_RE.fullmatch(str(raw))
    if not match:
        return None
    day, month, year = match.groups()
    idx = MONTHS.get(month.lower())
    if not idx:
        return None
    try:
        return date(int(year), idx, int(day)).isoformat()
    except ValueError:
        return None


def parse_table(html, metal, source_url="", cutoff=None):
    """Parse explicitly dated four-column LME rows; reject mixed metals/layout."""
    metal = metal.upper()
    if metal not in METALS:
        raise ValueError("unsupported metal")
    parser = _Rows()
    parser.feed(html)
    # A valid source includes a labelled 3-column data header; a 4-number
    # unrelated table must never be accepted as LME prices.
    headers = " ".join(" ".join(row) for row in parser.rows if
        any("Cash-Settlement" in c or "Cash Settlement" in c for c in row)).lower()
    if not headers or METALS[metal].lower() not in headers or "stock" not in headers or "month" not in headers:
        raise WestmetallError(f"{metal}: LME Cash/3-month/stock table header not verified")
    observations = []
    for row in parser.rows:
        if len(row) < 4:
            continue
        quoted = _date(row[0])
        if not quoted or (cutoff and quoted < cutoff):
            continue
        cash, forward, stock = (_num(row[i]) for i in (1, 2, 3))
        if any(x is None or x <= 0 for x in (cash, forward, stock)):
            continue
        if quoted > date.today().isoformat():
            continue
        observations.append(dict(metal=metal, price_date=quoted,
            cash_usd_t=float(cash), three_month_usd_t=float(forward),
            stock_t=float(stock), source=SOURCE, source_url=source_url))
    if not observations:
        raise WestmetallError(f"{metal}: valid dated LME rows absent; layout/date check required")
    # One observation per source/date/metal, never silently accept conflicts.
    distinct = {}
    for row in observations:
        key = row["price_date"]
        if key in distinct and row != distinct[key]:
            raise WestmetallError(f"{metal}: conflicting LME observations for {key}")
        distinct[key] = row
    return [distinct[d] for d in sorted(distinct)]


def init_schema(cx):
    cx.execute("""CREATE TABLE IF NOT EXISTS lme_quotes (
        source TEXT NOT NULL, metal TEXT NOT NULL, price_date TEXT NOT NULL,
        cash_usd_t REAL NOT NULL, three_month_usd_t REAL NOT NULL, stock_t REAL NOT NULL,
        source_url TEXT NOT NULL, captured_at TEXT NOT NULL,
        PRIMARY KEY(source,metal,price_date))""")
    cx.execute("""CREATE TABLE IF NOT EXISTS lme_revision_history (
        source TEXT,metal TEXT,price_date TEXT,previous_cash REAL,previous_three_month REAL,
        previous_stock REAL,revised_cash REAL,revised_three_month REAL,revised_stock REAL,
        changed_at TEXT NOT NULL)""")


def persist(cx, rows):
    init_schema(cx)
    result = {"inserted": 0, "updated": 0, "unchanged": 0}
    now = datetime.now(timezone.utc).isoformat()
    with cx:
        for r in rows:
            previous = cx.execute("""SELECT cash_usd_t,three_month_usd_t,stock_t
                FROM lme_quotes WHERE source=? AND metal=? AND price_date=?""",
                (r["source"], r["metal"], r["price_date"])).fetchone()
            current = tuple(Decimal(str(r[k])) for k in
                ("cash_usd_t", "three_month_usd_t", "stock_t"))
            if previous:
                old = tuple(Decimal(str(v)) for v in previous)
                if old == current:
                    result["unchanged"] += 1
                    continue
                cx.execute("""INSERT INTO lme_revision_history VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (r["source"],r["metal"],r["price_date"],*map(float,old),*map(float,current),now))
                result["updated"] += 1
            else:
                result["inserted"] += 1
            cx.execute("""INSERT INTO lme_quotes
                (source,metal,price_date,cash_usd_t,three_month_usd_t,stock_t,source_url,captured_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(source,metal,price_date) DO UPDATE SET
                cash_usd_t=excluded.cash_usd_t,three_month_usd_t=excluded.three_month_usd_t,
                stock_t=excluded.stock_t,source_url=excluded.source_url,captured_at=excluded.captured_at""",
                (r["source"],r["metal"],r["price_date"],*map(float,current),r["source_url"],now))
    return result


def collect_and_save(db_path, lookback_days=35, *, fetcher=None, logger=print):
    """Run independently of Selenium; no paid API, login, cookies or hidden calls."""
    from datetime import timedelta
    from pathlib import Path
    cutoff = (date.today() - timedelta(days=max(0, int(lookback_days)))).isoformat() if lookback_days else None
    def default_fetch(url):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; PriceCollector/1.0)"})
        with urllib.request.urlopen(req, timeout=20) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise WestmetallError("HTML exceeds 2 MB")
        return data.decode("utf-8", "replace")
    fetch = fetcher or default_fetch
    rows = []
    warnings = []
    for metal in METALS:
        url = BASE_URL.format(metal)
        try:
            parsed = parse_table(fetch(url),metal,url,cutoff=cutoff)
            rows.extend(parsed)
            logger(f"LME {metal}: {len(parsed)} rows, latest {parsed[-1]['price_date']}")
        except Exception as exc:
            warnings.append(f"LME {metal}: {type(exc).__name__}: {exc}")
    result = {"collected": len(rows), "warnings": warnings,
              "status": "failed" if not rows else "partial" if warnings else "complete"}
    if rows:
        with sqlite3.connect(str(Path(db_path)), timeout=30) as cx:
            result.update(persist(cx,rows))
    return result
