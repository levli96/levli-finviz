
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Any, Optional

MIN_QUICK_RATIO = 1.0
MIN_ROE = 12.0
MIN_ROIC = 9.0
MIN_GROSS_MARGIN = 38.0
MIN_PROFIT_MARGIN = 7.0
MIN_HISTORY_DAYS = 730

EXCELLENT_ROE = 30.0
EXCELLENT_GROSS_MARGIN = 45.0
EXCELLENT_PROFIT_MARGIN = 20.0
CHEAP_PS = 2.0
REASONABLE_PS = 8.0

REQUIRED_COLUMNS = {
    "Ticker",
    "Company",
    "Industry",
    "Price",
    "P/E",
    "Forward P/E",
    "P/S",
    "Return on Equity",
    "Return on Invested Capital",
    "Gross Margin",
    "Profit Margin",
    "EPS Growth This Year",
    "EPS Growth Next Year",
    "Quick Ratio",
}


def to_float(value: Any) -> Optional[float]:
    if value in (None, "", "-", "N/A", "nan"):
        return None
    s = str(value).strip().replace(",", "")
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_date(value: Any) -> Optional[date]:
    if value in (None, "", "-", "N/A", "nan"):
        return None
    s = str(value).strip()
    formats = (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%b-%d-%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_finviz_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("קובץ CSV ללא כותרות.")
    missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames))
    if missing:
        raise ValueError("חסרות עמודות ב־Finviz Export: " + ", ".join(missing))

    out: list[dict[str, Any]] = []
    today = date.today()

    for raw in reader:
        ticker = str(raw.get("Ticker", "")).strip().upper()
        if not ticker:
            continue

        ipo = parse_date(raw.get("IPO Date"))
        history_days = (today - ipo).days if ipo else None
        history_years = history_days / 365.25 if history_days is not None else None

        row = {
            "Ticker": ticker,
            "Company": str(raw.get("Company", "")).strip(),
            "Industry": str(raw.get("Industry", "")).strip() or "—",
            "IPO Date": ipo.isoformat() if ipo else "—",
            "History Days": history_days,
            "History Years": history_years,
            "Price": to_float(raw.get("Price")),
            "P/E": to_float(raw.get("P/E")),
            "Forward P/E": to_float(raw.get("Forward P/E")),
            "P/S": to_float(raw.get("P/S")),
            "Quick Ratio": to_float(raw.get("Quick Ratio")),
            "ROE %": to_float(raw.get("Return on Equity")),
            "ROIC %": to_float(raw.get("Return on Invested Capital")),
            "Gross Margin %": to_float(raw.get("Gross Margin")),
            "Profit Margin %": to_float(raw.get("Profit Margin")),
            "EPS Growth %": to_float(raw.get("EPS Growth This Year")),
            "Forward EPS Growth %": to_float(raw.get("EPS Growth Next Year")),
        }
        row["P/S Status"] = ps_status(row)
        row["Growth Status"] = growth_status(row["EPS Growth %"], row["Forward EPS Growth %"])
        row["Levli Score"] = levli_stars(row)
        out.append(row)

    return out


def history_filter(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    passed, failed = [], []
    for row in rows:
        ok = (
            row.get("History Days") is not None
            and row["History Days"] >= MIN_HISTORY_DAYS
        )
        row["_history_ok"] = ok
        if ok:
            passed.append(row)
        else:
            failed.append(row)
    return passed, failed


def ps_status(row: dict[str, Any]) -> str:
    ps = row.get("P/S")
    eps_growth = row.get("EPS Growth %")
    fwd_growth = row.get("Forward EPS Growth %")
    if ps is None:
        return "אין מידע"
    if ps < CHEAP_PS:
        return "זול וטוב"
    if ps <= REASONABLE_PS:
        return "סביר"
    strong_growth = (
        (eps_growth is not None and eps_growth > 30)
        or (fwd_growth is not None and fwd_growth > 30)
    )
    return "מוצדק רק בצמיחה חזקה" if strong_growth else "יקר ללא צמיחה חזקה"


def growth_status(eps_growth: Optional[float], forward_growth: Optional[float]) -> str:
    if eps_growth is None or forward_growth is None:
        return "אין מספיק מידע"
    if eps_growth <= 10:
        return "תקין" if forward_growth <= 16 else "תחזית אופטימית"
    if eps_growth <= 30:
        return "טוב" if forward_growth <= 30 else "תחזית אופטימית"
    if forward_growth < 25:
        return "האטה משמעותית צפויה"
    if forward_growth <= 46:
        return "מצוין"
    return "תחזית אופטימית"


def mandatory_checks(row: dict[str, Any]) -> dict[str, bool]:
    return {
        "P/E > Forward P/E": (
            row.get("P/E") is not None
            and row.get("Forward P/E") is not None
            and row["P/E"] > row["Forward P/E"]
        ),
        "Quick Ratio > 1": (
            row.get("Quick Ratio") if row.get("Quick Ratio") is not None else -999
        ) > MIN_QUICK_RATIO,
        "ROE ≥ 12%": (
            row.get("ROE %") if row.get("ROE %") is not None else -999
        ) >= MIN_ROE,
        "ROIC ≥ 9%": (
            row.get("ROIC %") if row.get("ROIC %") is not None else -999
        ) >= MIN_ROIC,
        "Gross Margin ≥ 38%": (
            row.get("Gross Margin %") if row.get("Gross Margin %") is not None else -999
        ) >= MIN_GROSS_MARGIN,
        "Profit Margin ≥ 7%": (
            row.get("Profit Margin %") if row.get("Profit Margin %") is not None else -999
        ) >= MIN_PROFIT_MARGIN,
    }


def levli_stars(row: dict[str, Any]) -> str:
    """1–5 stars, based only on fundamental quality bonuses.

    Monthly/Daily technical filters are pass/fail gates and do not affect the score.
    """
    count = 0
    count += int((row.get("ROE %") or -999) > EXCELLENT_ROE)
    count += int((row.get("Gross Margin %") or -999) > EXCELLENT_GROSS_MARGIN)
    count += int((row.get("Profit Margin %") or -999) > EXCELLENT_PROFIT_MARGIN)
    count += int(row.get("P/S") is not None and row["P/S"] < CHEAP_PS)
    count += int(row.get("Growth Status") == "מצוין")
    return "⭐" * min(5, max(count, 1))


def screen_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    passed, failed = [], []
    for row in rows:
        checks = mandatory_checks(row)
        row["_checks"] = checks
        if all(checks.values()):
            passed.append(row)
        else:
            failed.append(row)
    passed.sort(
        key=lambda r: (len(r.get("Levli Score", "")), r.get("Ticker", "")),
        reverse=True,
    )
    return passed, failed


def parse_approved_tickers(text: str) -> set[str]:
    if not text.strip():
        return set()
    parts = re.split(r"[\s,;]+", text.upper().strip())
    return {p for p in parts if p}


def result_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "Ticker": row.get("Ticker"),
        "Company": row.get("Company"),
        "Industry": row.get("Industry"),
        "IPO Date": row.get("IPO Date"),
        "History Years": row.get("History Years"),
        "Levli Score": row.get("Levli Score"),
        "P/E": row.get("P/E"),
        "Forward P/E": row.get("Forward P/E"),
        "P/S": row.get("P/S"),
        "P/S Status": row.get("P/S Status"),
        "Quick Ratio": row.get("Quick Ratio"),
        "ROE %": row.get("ROE %"),
        "ROIC %": row.get("ROIC %"),
        "Gross Margin %": row.get("Gross Margin %"),
        "Profit Margin %": row.get("Profit Margin %"),
        "EPS Growth %": row.get("EPS Growth %"),
        "Forward EPS Growth %": row.get("Forward EPS Growth %"),
        "Growth Status": row.get("Growth Status"),
        "Price": row.get("Price"),
    }


def diagnostic_row(row: dict[str, Any], history_reason: bool = False) -> dict[str, Any]:
    if history_reason:
        failed = ["פחות משנתיים היסטוריית מסחר / IPO Date חסר"]
    else:
        checks = row.get("_checks") or mandatory_checks(row)
        failed = [name for name, passed in checks.items() if not passed]

    return {
        "Ticker": row.get("Ticker"),
        "Company": row.get("Company"),
        "Industry": row.get("Industry"),
        "IPO Date": row.get("IPO Date"),
        "History Years": row.get("History Years"),
        "Failed Criteria": ", ".join(failed) if failed else "—",
    }
