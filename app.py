
from __future__ import annotations

import csv
import html
import io
from typing import Any

import streamlit as st

from levli_logic import (
    diagnostic_row,
    history_filter,
    parse_approved_tickers,
    parse_finviz_csv,
    result_row,
    screen_rows,
)

st.set_page_config(page_title="Levli — Finviz v0.4", page_icon="⭐", layout="wide")


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
        <style>
        table th,table td{{border:1px solid #ddd;padding:7px;white-space:nowrap}}
        table th{{background:#f3f4f6;color:#111}}
        </style>""",
        unsafe_allow_html=True,
    )


st.title("Levli — Finviz v0.4")
st.caption("Finviz Only — 2Y history floor → Fundamentals → Monthly Uptrend approval → Levli Score")

st.info(
    "v0.4 לא מציגה מניה כ'עברה Levli' בלי אישור מגמת Monthly. "
    "בנוסף, מניה עם פחות משנתיים מאז ה-IPO נפסלת אוטומטית. "
    "כדי שזה יעבוד, ה-Finviz Custom Export חייב לכלול גם את העמודה IPO Date."
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
    st.warning("ב-Finviz: Custom → Customize → הוסף IPO Date → Export מחדש.")
    st.stop()

rows = list({r["Ticker"]: r for r in rows if r.get("Ticker")}.values())

history_ok, history_failed = history_filter(rows)
fund_passed, fund_failed = screen_rows(history_ok)

m1, m2, m3, m4 = st.columns(4)
m1.metric("ניירות שנקלטו", len(rows))
m2.metric("נפסלו: פחות מ-2Y", len(history_failed))
m3.metric("עברו היסטוריה + פונדמנטל", len(fund_passed))
m4.metric("נפסלו פונדמנטלית", len(fund_failed))

st.subheader("מועמדות לבדיקה בגרף Monthly")
st.caption(
    "אלה עדיין לא 'עברו Levli'. צריך לאשר ב-Finviz שהגרף החודשי מציג מגמת עלייה מובהקת "
    "עם SMA50 לאורך לפחות שנתיים."
)

candidate_rows = [result_row(r) for r in fund_passed]
table(
    candidate_rows,
    [
        "Ticker", "Company", "IPO Date", "History Years", "Levli Score",
        "P/E", "Forward P/E", "P/S", "Quick Ratio", "ROE %", "ROIC %",
        "Gross Margin %", "Profit Margin %", "EPS Growth %",
        "Forward EPS Growth %", "Price",
    ],
)

candidate_csv = io.StringIO()
candidate_cols = ["Ticker", "Company", "IPO Date", "History Years"]
writer = csv.DictWriter(candidate_csv, fieldnames=candidate_cols)
writer.writeheader()
for row in candidate_rows:
    writer.writerow({k: row.get(k) for k in candidate_cols})

st.download_button(
    "הורד רשימת מועמדות לבדיקה ב-Finviz Charts",
    data=candidate_csv.getvalue().encode("utf-8-sig"),
    file_name="levli_monthly_review_candidates.csv",
    mime="text/csv",
)

st.divider()
st.subheader("אישור מגמת Monthly")

approved_text = st.text_area(
    "הדבק כאן Tick​​ers שאישרת בגרף Monthly",
    placeholder="לדוגמה: NVDA, MSFT, PLTR",
    help="אפשר להפריד בפסיקים, רווחים או שורות.",
)

approved = parse_approved_tickers(approved_text)
candidate_map = {r["Ticker"]: r for r in fund_passed}

if not approved:
    st.warning(
        "עדיין אין רשימת 'עברו Levli'. "
        "הדבק כאן רק מניות שבדקת ב-Finviz Monthly ושיש להן מגמת עלייה מובהקת עם SMA50."
    )
else:
    final_rows = [candidate_map[t] for t in approved if t in candidate_map]
    ignored = sorted(approved - set(candidate_map))

    st.success(f"עברו Levli: {len(final_rows)} מניות.")
    if ignored:
        st.info(
            "Tickers שלא נכנסו כי אינם ברשימת המועמדות לאחר היסטוריה/פונדמנטל: "
            + ", ".join(ignored)
        )

    table(
        [result_row(r) for r in final_rows],
        [
            "Ticker", "Company", "IPO Date", "History Years", "Levli Score",
            "P/E", "Forward P/E", "P/S", "P/S Status", "Quick Ratio",
            "ROE %", "ROIC %", "Gross Margin %", "Profit Margin %",
            "EPS Growth %", "Forward EPS Growth %", "Growth Status", "Price",
        ],
    )

with st.expander("נפסלו בגלל פחות משנתיים היסטוריה"):
    table(
        [diagnostic_row(r, history_reason=True) for r in history_failed],
        ["Ticker", "Company", "IPO Date", "History Years", "Failed Criteria"],
    )

with st.expander("נפסלו פונדמנטלית והסיבה"):
    table(
        [diagnostic_row(r) for r in fund_failed],
        ["Ticker", "Company", "IPO Date", "History Years", "Failed Criteria"],
    )

st.caption(
    "חשוב: Finviz אינו מספק דרך Export היסטוריית מחיר גולמית שמאפשרת ל-Levli לחשב בעצמה "
    "את שיפוע SMA50 החודשי לאורך שנתיים. לכן v0.4 מונעת תוצאה מטעה: בלי אישור Monthly אין 'עברו Levli'."
)
