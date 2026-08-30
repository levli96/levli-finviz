from __future__ import annotations

import html
from typing import Any

import streamlit as st

from levli_logic import diagnostic_row, parse_finviz_csv, result_row, screen_rows
from technical_yahoo import screen_tickers
from yahoo_diagnostic import test_yahoo

st.set_page_config(page_title="Levli — v0.5.1", page_icon="⭐", layout="wide")


def fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def table(rows: list[dict[str, Any]], cols: list[str]) -> None:
    if not rows:
        st.info("אין נתונים להצגה.")
        return
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(fmt(r.get(c)))}</td>" for c in cols) + "</tr>"
        for r in rows
    )
    st.markdown(
        f'''<div style="overflow-x:auto"><table style="border-collapse:collapse;width:100%;font-size:14px">
        <thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>
        <style>table th,table td{{border:1px solid #ddd;padding:7px;white-space:nowrap}}
        table th{{background:#f3f4f6;color:#111}}</style>''',
        unsafe_allow_html=True,
    )


st.title("Levli — v0.5.1")
st.caption("Yahoo diagnostic → Finviz fundamentals → MA50 Monthly trend (~24 months) → Levli Score")

st.info(
    "v0.5 מורידה אוטומטית מ-Yahoo היסטוריית מחיר חודשית רק למניות שעברו את הסינון הפונדמנטלי. "
    "היא מחשבת MA50 חודשי אמיתי ובודקת את המגמה שלו ב-24 נקודות חודשיות אחרונות."
)

st.subheader("בדיקת חיבור Yahoo — AAPL")
if st.button("בדוק Yahoo עם AAPL"):
    with st.spinner("בודק חיבור ישיר ל-Yahoo..."):
        diag = test_yahoo("AAPL")
    st.session_state["yahoo_diag"] = diag

if "yahoo_diag" in st.session_state:
    diag = st.session_state["yahoo_diag"]
    if diag.get("rows", 0) > 0 and diag.get("close_points", 0) > 0:
        st.success(f"Yahoo עובד: התקבלו {diag.get('rows')} שורות עבור AAPL.")
    else:
        st.error("Yahoo לא החזיר נתוני AAPL. פרטי האבחון מופיעים למטה.")
    st.json(diag)

uploaded = st.file_uploader("העלה Finviz Custom CSV", type=["csv"], accept_multiple_files=True)
if not uploaded:
    st.stop()

rows: list[dict[str, Any]] = []
try:
    for f in uploaded:
        rows += parse_finviz_csv(f.getvalue().decode("utf-8-sig", errors="replace"))
except ValueError as exc:
    st.error(str(exc))
    st.stop()

rows = list({r["Ticker"]: r for r in rows if r.get("Ticker")}.values())
fund_passed, fund_failed = screen_rows(rows)

m1, m2, m3 = st.columns(3)
m1.metric("ניירות שנקלטו", len(rows))
m2.metric("עברו פונדמנטלי", len(fund_passed))
m3.metric("נפסלו פונדמנטלית", len(fund_failed))

st.subheader("בדיקת MA50 Monthly אוטומטית")
st.caption(
    "הגדרת v0.5 למגמה ברורה: MA50 היום גבוה מתחילת חלון 24 החודשים, שיפוע לינארי חיובי, "
    "ולפחות 18 מתוך 23 השינויים החודשיים ב-MA50 אינם שליליים. בנוסף המחיר החודשי האחרון חייב להיות מעל/נוגע ב-MA50."
)

if st.button("הרץ בדיקת Yahoo + MA50 Monthly", type="primary"):
    with st.spinner("מוריד נתונים חודשיים מ-Yahoo ומחשב MA50..."):
        tech, error = screen_tickers([r["Ticker"] for r in fund_passed])

    if error:
        st.error(error)
        st.stop()

    passed, failed, no_data = [], [], []
    for row in fund_passed:
        t = row["Ticker"]
        info = tech.get(t)
        if not info:
            info = {"Technical Pass": False, "Technical Status": "לא התקבלו נתונים מ-Yahoo"}
        merged = {**row, **info}
        if not info.get("Monthly Points"):
            no_data.append(merged)
        elif info.get("Technical Pass"):
            passed.append(merged)
        else:
            failed.append(merged)

    st.session_state["tech_results"] = (passed, failed, no_data)

if "tech_results" in st.session_state:
    passed, failed, no_data = st.session_state["tech_results"]
    a, b, c = st.columns(3)
    a.metric("עברו Levli", len(passed))
    b.metric("נפסלו טכנית", len(failed))
    c.metric("ללא נתוני Yahoo", len(no_data))

    st.subheader("⭐ עברו Levli")
    final_rows = []
    for r in passed:
        x = result_row(r)
        x.update({k: r.get(k) for k in ["MA50 Start", "MA50 Now", "MA50 Change %", "MA50 Up Months", "Monthly Close", "Technical Status"]})
        final_rows.append(x)
    table(final_rows, [
        "Ticker", "Company", "Levli Score", "MA50 Start", "MA50 Now", "MA50 Change %",
        "MA50 Up Months", "Monthly Close", "P/E", "Forward P/E", "P/S", "Quick Ratio",
        "ROE %", "ROIC %", "Gross Margin %", "Profit Margin %", "EPS Growth %",
        "Forward EPS Growth %", "Growth Status",
    ])

    with st.expander("נפסלו בבדיקת MA50 Monthly"):
        table(failed, ["Ticker", "Company", "Technical Status", "Monthly Points", "MA50 Start", "MA50 Now", "MA50 Change %", "MA50 Up Months", "Monthly Close"])

    if no_data:
        with st.expander("לא התקבלו מספיק נתונים מ-Yahoo"):
            table(no_data, ["Ticker", "Company", "Technical Status", "Monthly Points"])

with st.expander("נפסלו פונדמנטלית והסיבה"):
    table([diagnostic_row(r) for r in fund_failed], ["Ticker", "Company", "Failed Criteria"])

st.caption(
    "מקור המחירים הטכניים: Yahoo Finance באמצעות yfinance. Finviz נשאר מקור הסינון הפונדמנטלי. "
    "אין צורך ב-API key נוסף."
)
