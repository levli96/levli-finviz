from __future__ import annotations
import pandas as pd
import yfinance as yf


def test_yahoo(ticker: str = 'AAPL') -> dict:
    out = {'ticker': ticker}
    try:
        data = yf.download(
            ticker,
            period='10y',
            interval='1mo',
            auto_adjust=True,
            actions=False,
            progress=False,
            threads=False,
            timeout=30,
        )
        out['rows'] = int(len(data))
        out['empty'] = bool(data.empty)
        out['columns'] = repr(data.columns.tolist())
        out['index_start'] = str(data.index.min()) if len(data) else None
        out['index_end'] = str(data.index.max()) if len(data) else None
        if not data.empty:
            if isinstance(data.columns, pd.MultiIndex):
                if 'Close' in data.columns.get_level_values(0):
                    close = data['Close']
                    if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
                elif 'Close' in data.columns.get_level_values(1):
                    close = data.xs('Close', axis=1, level=1).iloc[:, 0]
                else: close = pd.Series(dtype=float)
            else:
                close = data['Close'] if 'Close' in data.columns else pd.Series(dtype=float)
            close = pd.to_numeric(close, errors='coerce').dropna()
            out['close_points'] = int(len(close))
            out['last_close'] = float(close.iloc[-1]) if len(close) else None
        else:
            out['close_points'] = 0
            out['last_close'] = None
    except Exception as exc:
        out['exception_type'] = type(exc).__name__
        out['exception'] = str(exc)
    return out
