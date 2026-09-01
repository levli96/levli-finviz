from __future__ import annotations

import io
import requests
import pandas as pd


class FinvizAPIError(RuntimeError):
    pass


def download_finviz_csv(export_url: str, api_token: str) -> pd.DataFrame:
    """
    מוריד את תוצאות ה-Screener ישירות מ-Finviz Elite ומחזיר DataFrame.
    """

    export_url = str(export_url).strip()
    api_token = str(api_token).strip()

    if not export_url:
        raise FinvizAPIError("חסר Finviz Export URL")

    if not api_token:
        raise FinvizAPIError("חסר FINVIZ_API_TOKEN")

    separator = "&" if "?" in export_url else "?"
    url = f"{export_url}{separator}auth={api_token}"

    try:
        response = requests.get(
            url,
            timeout=30,
            allow_redirects=True,
            headers={"User-Agent": "Levli/1.0"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FinvizAPIError(f"שגיאת חיבור ל-Finviz: {exc}") from exc

    text = response.text.strip()

    if not text:
        raise FinvizAPIError("Finviz החזיר קובץ ריק")

    try:
        df = pd.read_csv(io.StringIO(text))
    except Exception as exc:
        raise FinvizAPIError(f"לא ניתן לקרוא את קובץ Finviz: {exc}") from exc

    if df.empty:
        raise FinvizAPIError("Finviz החזיר טבלה ללא מניות")

    return df
