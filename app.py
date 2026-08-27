from __future__ import annotations

import html
from typing import Any

import streamlit as st

from levli_logic import diagnostic_row, parse_finviz_csv, result_row, screen_rows

st.set_page_config(page_title="Levli — Finviz v0.3", page_icon="⭐", layout="wide")


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
        f"""<div style="overflow-x:auto"><table style="border-collapse:collapse;width:100%;font-size:14px">
        <thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>
        <style>table th,table td{{border:1px solid #ddd;padding:7px;white-space:nowrap}}table th{{background:#f3f4f6;color:#111}}</style>""",
        unsafe_allow_html=True,
    )


st.title("Levli — Finviz v0.3")
st.caption("Finviz Only — Technical pre-screen in Finviz → Fundamentals → Levli Score")

st.info(
    "העלה CSV מתצוגת Custom של ה-Preset ב-Finviz. "
    "הקובץ אמור להגיע לאחר הסינון הטכני ב-Finviz: "
    "Price Monthly ≥ SMA50 Monthly, SMA20 Monthly ≥ SMA50 Monthly, ו-Price Daily > SMA50 Daily."
)

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
m1.metric("ניירות שנקלטו מ-Finviz", len(rows))
m2.metric("עברו פונדמנטלי", len(fund_passed))
m3.metric("נפסלו פונדמנטלי", len(fund_failed))

st.success("Finviz Only: אין צורך ב-FMP API Key ואין בדיקת מחיר נוספת מחוץ ל-Finviz.")

st.subheader("מניות שעברו Levli")
table(
    [result_row(r) for r in fund_passed],
    [
        "Ticker", "Company", "Levli Score", "P/E", "Forward P/E", "P/S", "P/S Status",
        "Quick Ratio", "ROE %", "ROIC %", "Gross Margin %", "Profit Margin %",
        "EPS Growth %", "Forward EPS Growth %", "Growth Status", "Price",
    ],
)

with st.expander("נפסלו פונדמנטלית והסיבה"):
    table([diagnostic_row(r) for r in fund_failed], ["Ticker", "Company", "Failed Criteria"])
