
from __future__ import annotations

import csv
import html
import io
import time
from typing import Any

import streamlit as st

from levli_logic import parse_finviz_csv, screen_rows, result_row, diagnostic_row

st.set_page_config(page_title="Levli Finviz", page_icon="⭐", layout="wide")

def fmt(v: Any, digits: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)

def render_html_table(rows: list[dict[str, Any]], columns: list[str]) -> None:
    if not rows:
        st.info("אין נתונים להצגה.")
        return
    head = "".join(f"<th>{html.escape(c)}</th>" for c in columns)
    body = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(fmt(row.get(c)))}</td>" for c in columns)
        body.append(f"<tr>{cells}</tr>")
    st.markdown(
        f"""
        <div style="overflow-x:auto;width:100%">
          <table style="border-collapse:collapse;width:100%;font-size:14px">
            <thead><tr>{head}</tr></thead>
            <tbody>{''.join(body)}</tbody>
          </table>
        </div>
        <style>
        table th, table td {{border:1px solid #ddd;padding:7px;text-align:left;white-space:nowrap}}
        table th {{background:#f3f4f6;color:#111;position:sticky;top:0}}
        </style>
        """,
        unsafe_allow_html=True,
    )

st.title("Levli — Finviz Test")
st.caption("Fundamental Quality Filter")

st.info(
    "גרסת ניסיון נפרדת מ־FMP. היא קוראת Export של Finviz Custom, "
    "מסננת לפי חוקי Levli ומחשבת Levli Score בכוכבים."
)

uploaded = st.file_uploader(
    "העלה קובץ CSV מ־Finviz",
    type=["csv"],
    accept_multiple_files=True,
    help="אפשר להעלות קובץ אחד או כמה קבצי Export. המערכת מאחדת ומסירה כפילויות לפי Ticker.",
)

confirmed_sma50 = st.checkbox(
    "אני מאשר שה־Export נוצר מ־Preset של Finviz עם Price above SMA50",
    value=True,
)

if not uploaded:
    st.stop()

if not confirmed_sma50:
    st.warning("Levli דורש Price > MA50. יש להפעיל ב־Finviz את Price above SMA50 לפני ה־Export.")
    st.stop()

started = time.perf_counter()
all_rows: list[dict[str, Any]] = []
source_files = 0

for f in uploaded:
    raw = f.getvalue().decode("utf-8-sig", errors="replace")
    rows = parse_finviz_csv(raw)
    all_rows.extend(rows)
    source_files += 1

# dedupe
dedup: dict[str, dict[str, Any]] = {}
for row in all_rows:
    ticker = str(row.get("Ticker", "")).strip().upper()
    if ticker:
        dedup[ticker] = row

rows = list(dedup.values())
passed, failed = screen_rows(rows)
elapsed = time.perf_counter() - started

m1, m2, m3, m4 = st.columns(4)
m1.metric("ניירות בקובץ", len(rows))
m2.metric("עברו פונדמנטלי", len(passed))
m3.metric("נפסלו", len(failed))
m4.metric("זמן עיבוד", f"{elapsed:.2f} שנ׳")

st.caption(
    "הערה: MA50 Rising עדיין לא נאכף בגרסה זו. הוא נשאר תנאי חובה ב־Levli "
    "ויוסף בשלב החיבור הטכני; לא הסרנו אותו מספר החוקים."
)

st.subheader("מניות שעברו את הסינון הפונדמנטלי")
passed_out = [result_row(r) for r in passed]
columns = [
    "Ticker","Company","Levli Score","P/E","Forward P/E","P/S","P/S Status",
    "Quick Ratio","ROE %","ROIC %","Gross Margin %","Profit Margin %",
    "EPS Growth %","Forward EPS Growth %","Growth Status","Price"
]
render_html_table(passed_out, columns)

# CSV download of passed results
buf = io.StringIO()
writer = csv.DictWriter(buf, fieldnames=columns)
writer.writeheader()
for row in passed_out:
    writer.writerow({k: row.get(k) for k in columns})

st.download_button(
    "הורד תוצאות CSV",
    data=buf.getvalue().encode("utf-8-sig"),
    file_name="levli_finviz_passed.csv",
    mime="text/csv",
)

with st.expander("מניות שנפסלו והסיבה", expanded=False):
    failed_out = [diagnostic_row(r) for r in failed]
    render_html_table(
        failed_out,
        ["Ticker","Company","Failed Criteria"]
    )

st.caption("Levli אינו המלצת השקעה. זהו מסנן פונדמנטלי למחקר נוסף.")
