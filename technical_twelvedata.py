from __future__ import annotations

import math
import time
from typing import Any, Callable

import numpy as np
import pandas as pd
import requests

# Monthly stage
MA_MONTHS = 50
TREND_MONTHS = 24
MIN_UP_MONTHS = 18
MONTHLY_OUTPUTSIZE = 80

# Daily stage
DAILY_SMA_DAYS = 50
DAILY_TREND_DAYS = 252  # approximately one trading year
DAILY_OUTPUTSIZE = 330  # 50-day SMA warm-up + one-year analysis window + margin
MIN_DAILY_CROSSINGS = 5
CROSS_CONFIRM_DAYS = 2

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


def _confirmed_crossings(diff: pd.Series, confirm_days: int = CROSS_CONFIRM_DAYS) -> int:
    """Count confirmed price/SMA crossings.

    A side change is counted only after `confirm_days` consecutive closes on the
    new side of SMA50. This avoids counting a one-day touch/noise as a crossing.
    Equality is treated as above/touching the SMA50.
    """
    diff = pd.to_numeric(diff, errors="coerce").dropna()
    if len(diff) < confirm_days:
        return 0

    above = diff >= 0
    last_state: bool | None = None
    crossings = 0

    for i in range(confirm_days - 1, len(above)):
        window = above.iloc[i - confirm_days + 1 : i + 1]
        if bool(window.all()):
            state = True
        elif bool((~window).all()):
            state = False
        else:
            continue

        if last_state is None:
            last_state = state
        elif state != last_state:
            crossings += 1
            last_state = state

    return crossings


def analyze_daily_sma50(close: pd.Series) -> dict[str, Any]:
    close = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    sma50 = close.rolling(DAILY_SMA_DAYS, min_periods=DAILY_SMA_DAYS).mean()
    frame = pd.DataFrame({"Close": close, "SMA50": sma50}).dropna()

    if len(frame) < DAILY_TREND_DAYS:
        return {
            "Daily Pass": False,
            "Daily Status": "אין מספיק היסטוריה ל-SMA50 יומי + כשנת מסחר אחת",
            "Daily Points": int(len(close)),
            "Daily SMA50 Start": None,
            "Daily SMA50 Now": None,
            "Daily SMA50 Change %": None,
            "Daily Close": float(close.iloc[-1]) if len(close) else None,
            "Daily Distance %": None,
            "Daily Crossings": None,
            "Days Above SMA50 %": None,
        }

    trend = frame.iloc[-DAILY_TREND_DAYS:].copy()
    sma = trend["SMA50"]
    x = np.arange(len(sma), dtype=float)
    slope = float(np.polyfit(x, sma.to_numpy(dtype=float), 1)[0])
    start = float(sma.iloc[0])
    now = float(sma.iloc[-1])
    last_close = float(trend["Close"].iloc[-1])
    change_pct = ((now / start) - 1.0) * 100.0 if start else None
    distance_pct = ((last_close / now) - 1.0) * 100.0 if now else None
    diff = trend["Close"] - trend["SMA50"]
    crossings = _confirmed_crossings(diff)
    days_above_pct = float((diff >= 0).mean() * 100.0)

    trend_ok = now > start and slope > 0
    price_ok = last_close >= now
    crossings_ok = crossings >= MIN_DAILY_CROSSINGS
    passed = trend_ok and price_ok and crossings_ok

    if not trend_ok:
        status = "SMA50 יומי אינו במגמת עלייה לאורך ~שנת מסחר"
    elif not price_ok:
        status = "SMA50 היומי עולה, אך המחיר הנוכחי מתחת ל-SMA50"
    elif not crossings_ok:
        status = f"פחות מ-{MIN_DAILY_CROSSINGS} חציות מאושרות של המחיר מול SMA50 בשנה"
    else:
        status = f"עבר: SMA50 יומי עולה ~שנה, המחיר מעל/נוגע בו, ו-{crossings} חציות מאושרות"

    return {
        "Daily Pass": passed,
        "Daily Status": status,
        "Daily Points": int(len(close)),
        "Daily SMA50 Start": start,
        "Daily SMA50 Now": now,
        "Daily SMA50 Change %": change_pct,
        "Daily Close": last_close,
        "Daily Distance %": distance_pct,
        "Daily Crossings": crossings,
        "Days Above SMA50 %": days_above_pct,
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
        "outputsize": MONTHLY_OUTPUTSIZE,
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


def _fetch_batch(
    api_key: str,
    originals: list[str],
    interval: str,
    outputsize: int,
) -> tuple[dict[str, pd.Series], str | None, bool]:
    mapping = {t: td_symbol(t) for t in originals}
    symbols = list(dict.fromkeys(mapping.values()))
    params = {
        "symbol": ",".join(symbols),
        "interval": interval,
        "outputsize": outputsize,
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

    if r.status_code == 429:
        return {}, _error_message(payload, r.status_code), True

    out: dict[str, pd.Series] = {}
    if len(symbols) == 1:
        out[originals[0]] = _series_from_payload(payload)
        if not r.ok and not len(out[originals[0]]):
            return out, _error_message(payload, r.status_code), False
        return out, None, False

    for original, sym in mapping.items():
        sub = payload.get(sym, {}) if isinstance(payload, dict) else {}
        out[original] = _series_from_payload(sub)

    if not r.ok:
        return out, _error_message(payload, r.status_code), False
    return out, None, False


def _screen_tickers_generic(
    tickers: list[str],
    api_key: str,
    interval: str,
    outputsize: int,
    analyzer: Callable[[pd.Series], dict[str, Any]],
    empty_result: dict[str, Any],
    credits_per_minute: int = 8,
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[dict[str, dict[str, Any]], str | None]:
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

        series_map, err, rate_limited = _fetch_batch(api_key, batch, interval, outputsize)
        if rate_limited:
            if progress:
                progress(bi, total_batches, "ממתין לאיפוס מכסת Twelve Data…")
            time.sleep(61)
            series_map, err, rate_limited = _fetch_batch(api_key, batch, interval, outputsize)

        if err and not series_map:
            return results, f"Twelve Data: {err}"

        for ticker in batch:
            close = series_map.get(ticker, pd.Series(dtype="float64"))
            results[ticker] = analyzer(close) if len(close) else dict(empty_result)

        if bi < total_batches - 1:
            if progress:
                progress(bi + 1, total_batches, "ממתין למכסה של הדקה הבאה…")
            time.sleep(61)

    if progress:
        progress(total_batches, total_batches, "הבדיקה הסתיימה")
    return results, None


def screen_tickers(
    tickers: list[str],
    api_key: str,
    credits_per_minute: int = 8,
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Monthly Levli stage."""
    return _screen_tickers_generic(
        tickers=tickers,
        api_key=api_key,
        interval="1month",
        outputsize=MONTHLY_OUTPUTSIZE,
        analyzer=analyze_monthly_ma50,
        empty_result={
            "Technical Pass": False,
            "Technical Status": "לא התקבלו נתוני מחיר מ-Twelve Data",
            "Monthly Points": 0,
            "MA50 Start": None,
            "MA50 Now": None,
            "MA50 Change %": None,
            "MA50 Up Months": None,
            "Monthly Close": None,
        },
        credits_per_minute=credits_per_minute,
        progress=progress,
    )


def screen_daily_tickers(
    tickers: list[str],
    api_key: str,
    credits_per_minute: int = 8,
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Daily Levli stage: rising SMA50 over ~1 trading year + current price >= SMA50 + >=5 confirmed crossings."""
    return _screen_tickers_generic(
        tickers=tickers,
        api_key=api_key,
        interval="1day",
        outputsize=DAILY_OUTPUTSIZE,
        analyzer=analyze_daily_sma50,
        empty_result={
            "Daily Pass": False,
            "Daily Status": "לא התקבלו נתונים יומיים מ-Twelve Data",
            "Daily Points": 0,
            "Daily SMA50 Start": None,
            "Daily SMA50 Now": None,
            "Daily SMA50 Change %": None,
            "Daily Close": None,
            "Daily Distance %": None,
            "Daily Crossings": None,
            "Days Above SMA50 %": None,
        },
        credits_per_minute=credits_per_minute,
        progress=progress,
    )
