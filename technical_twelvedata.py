from __future__ import annotations

import math
import time
from typing import Any, Callable

import numpy as np
import pandas as pd
import requests

MA_MONTHS = 50
TREND_MONTHS = 24
MIN_UP_MONTHS = 18
OUTPUTSIZE = 80  # enough for a 50-month MA plus a 24-month trend window
API_URL = "https://api.twelvedata.com/time_series"


def td_symbol(ticker: str) -> str:
    """Normalize common US class-share notation for Twelve Data."""
    return ticker.strip().upper().replace("-", ".")


def analyze_monthly_ma50(close: pd.Series) -> dict[str, Any]:
    close = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    ma50 = close.rolling(MA_MONTHS, min_periods=MA_MONTHS).mean().dropna()

    if len(ma50) < TREND_MONTHS:
        return {
            "Technical Pass": False,
            "Technical Status": "אין מספיק היסטוריה ל-MA50 חודשי + 24 חודשי מגמה",
            "Monthly Points": int(len(close)),
            "MA50 Start": None,
            "MA50 Now": None,
            "MA50 Change %": None,
            "MA50 Up Months": None,
            "Monthly Close": float(close.iloc[-1]) if len(close) else None,
        }

    trend = ma50.iloc[-TREND_MONTHS:]
    x = np.arange(len(trend), dtype=float)
    slope = float(np.polyfit(x, trend.to_numpy(dtype=float), 1)[0])
    diffs = trend.diff().dropna()
    up_months = int((diffs >= 0).sum())
    start = float(trend.iloc[0])
    now = float(trend.iloc[-1])
    change_pct = ((now / start) - 1.0) * 100.0 if start else None
    last_close = float(close.iloc[-1])

    trend_ok = now > start and slope > 0 and up_months >= MIN_UP_MONTHS
    price_ok = last_close >= now
    passed = trend_ok and price_ok

    if not trend_ok:
        status = "MA50 חודשי אינו במגמת עלייה ברורה לאורך ~24 חודשים"
    elif not price_ok:
        status = "המגמה עולה, אך המחיר החודשי מתחת ל-MA50"
    else:
        status = "עבר: MA50 חודשי עולה ~24 חודשים והמחיר מעל/נוגע בממוצע"

    return {
        "Technical Pass": passed,
        "Technical Status": status,
        "Monthly Points": int(len(close)),
        "MA50 Start": start,
        "MA50 Now": now,
        "MA50 Change %": change_pct,
        "MA50 Up Months": up_months,
        "Monthly Close": last_close,
    }


def _series_from_payload(payload: dict[str, Any]) -> pd.Series:
    if not isinstance(payload, dict):
        return pd.Series(dtype="float64")
    values = payload.get("values")
    if not isinstance(values, list) or not values:
        return pd.Series(dtype="float64")

    points: list[tuple[pd.Timestamp, float]] = []
    for row in values:
        if not isinstance(row, dict):
            continue
        try:
            dt = pd.to_datetime(row.get("datetime"), errors="raise")
            close = float(row.get("close"))
            points.append((dt, close))
        except (TypeError, ValueError):
            continue
    if not points:
        return pd.Series(dtype="float64")
    return pd.Series({dt: close for dt, close in points}, dtype="float64").sort_index()


def _error_message(payload: Any, status_code: int | None = None) -> str:
    if isinstance(payload, dict):
        msg = payload.get("message") or payload.get("code") or payload.get("status")
        if msg:
            return str(msg)
    return f"HTTP {status_code}" if status_code else "תגובה לא צפויה מ-Twelve Data"


def test_connection(api_key: str, ticker: str = "AAPL") -> dict[str, Any]:
    if not api_key:
        return {"ok": False, "ticker": ticker, "points": 0, "error": "TWELVE_DATA_API_KEY חסר ב-Streamlit Secrets"}
    params = {
        "symbol": td_symbol(ticker),
        "interval": "1month",
        "outputsize": OUTPUTSIZE,
        "format": "JSON",
        "apikey": api_key,
    }
    try:
        r = requests.get(API_URL, params=params, timeout=30)
        payload = r.json()
    except requests.RequestException as exc:
        return {"ok": False, "ticker": ticker, "points": 0, "error": f"שגיאת רשת: {exc.__class__.__name__}"}
    except ValueError:
        return {"ok": False, "ticker": ticker, "points": 0, "error": "Twelve Data החזיר תשובה שאינה JSON"}

    s = _series_from_payload(payload)
    if r.ok and len(s):
        return {
            "ok": True,
            "ticker": ticker,
            "points": int(len(s)),
            "first": str(s.index.min().date()),
            "last": str(s.index.max().date()),
            "last_close": float(s.iloc[-1]),
        }
    return {"ok": False, "ticker": ticker, "points": 0, "error": _error_message(payload, r.status_code)}


def _fetch_batch(api_key: str, originals: list[str]) -> tuple[dict[str, pd.Series], str | None, bool]:
    mapping = {t: td_symbol(t) for t in originals}
    symbols = list(dict.fromkeys(mapping.values()))
    params = {
        "symbol": ",".join(symbols),
        "interval": "1month",
        "outputsize": OUTPUTSIZE,
        "format": "JSON",
        "apikey": api_key,
    }
    try:
        r = requests.get(API_URL, params=params, timeout=45)
        payload = r.json()
    except requests.RequestException as exc:
        return {}, f"שגיאת רשת: {exc.__class__.__name__}", False
    except ValueError:
        return {}, "Twelve Data החזיר תשובה שאינה JSON", False

    # 429: caller may wait for quota reset and retry once.
    if r.status_code == 429:
        return {}, _error_message(payload, r.status_code), True

    out: dict[str, pd.Series] = {}
    if len(symbols) == 1:
        out[originals[0]] = _series_from_payload(payload)
        if not r.ok and not len(out[originals[0]]):
            return out, _error_message(payload, r.status_code), False
        return out, None, False

    # Multi-symbol response is keyed by symbol.
    for original, sym in mapping.items():
        sub = payload.get(sym, {}) if isinstance(payload, dict) else {}
        out[original] = _series_from_payload(sub)

    if not r.ok:
        return out, _error_message(payload, r.status_code), False
    return out, None, False


def screen_tickers(
    tickers: list[str],
    api_key: str,
    credits_per_minute: int = 8,
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Fetch monthly prices in Twelve Data batches, respecting the user's per-minute credit limit.

    Basic/free defaults to 8 credits/minute. Each /time_series symbol costs 1 credit.
    """
    clean = list(dict.fromkeys(t.strip().upper() for t in tickers if t and t.strip()))
    if not clean:
        return {}, None
    if not api_key:
        return {}, "TWELVE_DATA_API_KEY חסר ב-Streamlit Secrets"

    batch_size = max(1, int(credits_per_minute or 8))
    total_batches = math.ceil(len(clean) / batch_size)
    results: dict[str, dict[str, Any]] = {}

    for bi in range(total_batches):
        batch = clean[bi * batch_size : (bi + 1) * batch_size]
        if progress:
            progress(bi, total_batches, f"מוריד קבוצה {bi + 1}/{total_batches} ({len(batch)} מניות)")

        series_map, err, rate_limited = _fetch_batch(api_key, batch)
        if rate_limited:
            if progress:
                progress(bi, total_batches, "ממתין לאיפוס מכסת Twelve Data…")
            time.sleep(61)
            series_map, err, rate_limited = _fetch_batch(api_key, batch)

        if err and not series_map:
            return results, f"Twelve Data: {err}"

        for ticker in batch:
            close = series_map.get(ticker, pd.Series(dtype="float64"))
            if len(close):
                results[ticker] = analyze_monthly_ma50(close)
            else:
                results[ticker] = {
                    "Technical Pass": False,
                    "Technical Status": "לא התקבלו נתוני מחיר מ-Twelve Data",
                    "Monthly Points": 0,
                    "MA50 Start": None,
                    "MA50 Now": None,
                    "MA50 Change %": None,
                    "MA50 Up Months": None,
                    "Monthly Close": None,
                }

        # On Basic/free, wait for the next minute before consuming another full quota.
        if bi < total_batches - 1:
            if progress:
                progress(bi + 1, total_batches, "ממתין למכסה של הדקה הבאה…")
            time.sleep(61)

    if progress:
        progress(total_batches, total_batches, "הבדיקה הסתיימה")
    return results, None
