from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

MA_MONTHS = 50
TREND_MONTHS = 24
MIN_UP_MONTHS = 18  # 18 of the 23 month-to-month MA50 changes must be >= 0


def yahoo_symbol(ticker: str) -> str:
    """Translate common US class-share notation (e.g. BRK.B) to Yahoo format."""
    return ticker.strip().upper().replace(".", "-")


def _close_series(data: pd.DataFrame, symbol: str, multi: bool) -> pd.Series:
    if data is None or data.empty:
        return pd.Series(dtype="float64")

    try:
        if isinstance(data.columns, pd.MultiIndex):
            # yfinance may return either (Price, Ticker) or (Ticker, Price).
            if "Close" in data.columns.get_level_values(0):
                s = data["Close"][symbol]
            elif "Close" in data.columns.get_level_values(1):
                s = data[symbol]["Close"]
            else:
                return pd.Series(dtype="float64")
        else:
            if "Close" not in data.columns:
                return pd.Series(dtype="float64")
            s = data["Close"]
        return pd.to_numeric(s, errors="coerce").dropna()
    except (KeyError, TypeError):
        return pd.Series(dtype="float64")


def analyze_monthly_ma50(close: pd.Series) -> dict[str, Any]:
    """Evaluate a true 50-month moving average over the last ~24 monthly observations."""
    close = close.dropna().sort_index()
    ma50 = close.rolling(MA_MONTHS, min_periods=MA_MONTHS).mean().dropna()

    # Need 24 months of MA50 values; that implies at least 73 monthly closes.
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

    # "Clear rising trend" = higher than ~24 months ago, positive fitted slope,
    # and rising/flat in at least 18 of 23 month-to-month changes.
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


def screen_tickers(tickers: list[str]) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Download monthly Yahoo data for all candidates in one request and screen them."""
    clean = [t.strip().upper() for t in tickers if t and t.strip()]
    if not clean:
        return {}, None

    mapping = {t: yahoo_symbol(t) for t in clean}
    symbols = list(dict.fromkeys(mapping.values()))

    try:
        data = yf.download(
            tickers=symbols,
            period="10y",
            interval="1mo",
            auto_adjust=True,
            actions=False,
            repair=True,
            group_by="column",
            threads=True,
            progress=False,
            timeout=20,
            multi_level_index=True,
        )
    except Exception as exc:
        return {}, f"Yahoo download failed: {exc}"

    results: dict[str, dict[str, Any]] = {}
    for ticker, symbol in mapping.items():
        close = _close_series(data, symbol, len(symbols) > 1)
        results[ticker] = analyze_monthly_ma50(close)

    return results, None
