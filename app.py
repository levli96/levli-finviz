from __future__ import annotations

import html
from typing import Any

import streamlit as st

from levli_logic import diagnostic_row, parse_finviz_csv, result_row, screen_rows
from technical_twelvedata import screen_tickers, test_connection

st.set_page_config(page_title="Levli — v0.6", page_icon="⭐", layout="wide")


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


def get_api_key() -> str:
    try:
        return str(st.secrets.get("TWELVE_DATA_API_KEY", "")).strip()
    except Exception:
        return ""


st.title("Levli — v0.6")
st.caption("Finviz fundamentals → Twelve Data monthly history → true MA50 Monthly trend (~24 months) → Levli Score")
st.info(
    "v0.6 מחליפה את Yahoo ב-Twelve Data. הסינון הפונדמנטלי וכללי MA50 של Levli לא השתנו. "
    "ה-API key נקרא רק מ-Streamlit Secrets ואינו נשמר בקוד."
)

api_key = get_api_key()
st.subheader("בדיקת חיבור Twelve Data — AAPL")
if st.button("בדוק Twelve Data עם AAPL"):
    with st.spinner("בודק חיבור ל-Twelve Data…"):
        diag = test_connection(api_key, "AAPL")
    st.session_state["td_diag"] = diag

if "td_diag" in st.session_state:
    diag = st.session_state["td_diag"]
    if diag.get("ok"):
        st.success(f"Twelve Data עובד: התקבלו {diag.get('points')} נקודות חודשיות עבור AAPL.")
    else:
        st.error(f"בדיקת Twelve Data נכשלה: {diag.get('error', 'שגיאה לא ידועה')}")
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
    "מגמה ברורה ב-v0.6: MA50 היום גבוה מתחילת חלון 24 החודשים, שיפוע לינארי חיובי, "
    "ולפחות 18 מתוך 23 השינויים החודשיים ב-MA50 אינם שליליים. בנוסף המחיר החודשי האחרון חייב להיות מעל/נוגע ב-MA50."
)

credits = 8
try:
    credits = max(1, int(st.secrets.get("TWELVE_DATA_CREDITS_PER_MINUTE", 8)))
except Exception:
    credits = 8

estimated_minutes = max(0, (len(fund_passed) - 1) // credits)
st.warning(
    f"מכסת Twelve Data מוגדרת ל-{credits} מניות בדקה. עבור {len(fund_passed)} מועמדות, "
    f"סריקה מלאה עשויה לקחת בערך {estimated_minutes} דקות. אל תסגור את החלון בזמן הסריקה."
)

if st.button("הרץ בדיקת Twelve Data + MA50 Monthly", type="primary"):
    if not api_key:
        st.error("TWELVE_DATA_API_KEY לא נמצא ב-Streamlit Secrets.")
        st.stop()

    progress_bar = st.progress(0)
    status_box = st.empty()

    def update_progress(done: int, total: int, msg: str) -> None:
        pct = 0 if total <= 0 else min(100, int(done / total * 100))
        progress_bar.progress(pct)
        status_box.info(msg)

    with st.spinner("מוריד נתונים חודשיים ומחשב MA50…"):
        tech, error = screen_tickers(
            [r["Ticker"] for r in fund_passed],
            api_key=api_key,
            credits_per_minute=credits,
            progress=update_progress,
        )

    if error:
        st.error(error)
        st.stop()

    passed, failed, no_data = [], [], []
    for row in fund_passed:
        t = row["Ticker"]
        info = tech.get(t) or {
            "Technical Pass": False,
            "Technical Status": "לא התקבלו נתונים מ-Twelve Data",
            "Monthly Points": 0,
        }
        merged = {**row, **info}
        if not info.get("Monthly Points"):
            no_data.append(merged)
        elif info.get("Technical Pass"):
            passed.append(merged)
        else:
            failed.append(merged)

    st.session_state["tech_results_v06"] = (passed, failed, no_data)
    progress_bar.progress(100)
    status_box.success("בדיקת Twelve Data הסתיימה.")

if "tech_results_v06" in st.session_state:
    passed, failed, no_data = st.session_state["tech_results_v06"]
    a, b, c = st.columns(3)
    a.metric("עברו Levli", len(passed))
    b.metric("נפסלו טכנית", len(failed))
    c.metric("ללא נתוני Twelve Data", len(no_data))

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
        with st.expander("לא התקבלו מספיק נתונים מ-Twelve Data"):
            table(no_data, ["Ticker", "Company", "Technical Status", "Monthly Points"])

with st.expander("נפסלו פונדמנטלית והסיבה"):
    table([diagnostic_row(r) for r in fund_failed], ["Ticker", "Company", "Failed Criteria"])

st.caption(
    "מקור המחירים הטכניים: Twelve Data. Finviz נשאר מקור הסינון הפונדמנטלי. "
    "המפתח נשמר ב-Streamlit Secrets בלבד."
)
