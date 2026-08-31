from __future__ import annotations

import html
from typing import Any

import streamlit as st

from levli_logic import diagnostic_row, parse_finviz_csv, result_row, screen_rows
from technical_twelvedata import screen_daily_tickers, screen_tickers, test_connection

st.set_page_config(page_title="Levli — v0.8", page_icon="⭐", layout="wide")


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


def get_credits() -> int:
    try:
        return max(1, int(st.secrets.get("TWELVE_DATA_CREDITS_PER_MINUTE", 8)))
    except Exception:
        return 8


st.title("Levli — v0.8")
st.caption("Finviz fundamentals → MA50 Monthly (~24m) → SMA50 Daily (~1y + crossings) → Levli Score")
st.info(
    "v0.8 מוסיפה Industry ומדרגת את הרשימה הסופית לפי Levli Score של 1–5 כוכבים. "
    "כללי הסינון Monthly ו-Daily נשארו ללא שינוי; הנתונים הטכניים אינם משפיעים על מספר הכוכבים."
)

api_key = get_api_key()
credits = get_credits()

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

# ---------------- Monthly stage ----------------
st.subheader("שלב 1 — MA50 Monthly")
st.caption(
    "MA50 היום גבוה מתחילת חלון 24 החודשים, שיפוע לינארי חיובי, לפחות 18 מתוך 23 השינויים "
    "החודשיים ב-MA50 אינם שליליים, והמחיר החודשי האחרון מעל/נוגע ב-MA50."
)

monthly_est = max(0, (len(fund_passed) - 1) // credits)
st.warning(
    f"מכסת Twelve Data מוגדרת ל-{credits} מניות בדקה. עבור {len(fund_passed)} מועמדות, "
    f"השלב החודשי עשוי לקחת בערך {monthly_est} דקות."
)

if st.button("הרץ שלב 1 — Twelve Data + MA50 Monthly", type="primary"):
    if not api_key:
        st.error("TWELVE_DATA_API_KEY לא נמצא ב-Streamlit Secrets.")
        st.stop()

    progress_bar = st.progress(0)
    status_box = st.empty()

    def update_monthly(done: int, total: int, msg: str) -> None:
        pct = 0 if total <= 0 else min(100, int(done / total * 100))
        progress_bar.progress(pct)
        status_box.info(msg)

    with st.spinner("מוריד נתונים חודשיים ומחשב MA50…"):
        tech, error = screen_tickers(
            [r["Ticker"] for r in fund_passed],
            api_key=api_key,
            credits_per_minute=credits,
            progress=update_monthly,
        )

    if error:
        st.error(error)
        st.stop()

    monthly_passed, monthly_failed, monthly_no_data = [], [], []
    for row in fund_passed:
        t = row["Ticker"]
        info = tech.get(t) or {
            "Technical Pass": False,
            "Technical Status": "לא התקבלו נתונים מ-Twelve Data",
            "Monthly Points": 0,
        }
        merged = {**row, **info}
        if not info.get("Monthly Points"):
            monthly_no_data.append(merged)
        elif info.get("Technical Pass"):
            monthly_passed.append(merged)
        else:
            monthly_failed.append(merged)

    st.session_state["monthly_results_v08"] = (monthly_passed, monthly_failed, monthly_no_data)
    st.session_state.pop("daily_results_v08", None)
    progress_bar.progress(100)
    status_box.success("שלב 1 הסתיים.")

if "monthly_results_v08" in st.session_state:
    monthly_passed, monthly_failed, monthly_no_data = st.session_state["monthly_results_v08"]
    a, b, c = st.columns(3)
    a.metric("עברו Monthly", len(monthly_passed))
    b.metric("נפסלו Monthly", len(monthly_failed))
    c.metric("ללא נתונים חודשיים", len(monthly_no_data))

    with st.expander("הצג את המניות שעברו Monthly"):
        table(monthly_passed, [
            "Ticker", "Company", "Industry", "MA50 Start", "MA50 Now", "MA50 Change %",
            "MA50 Up Months", "Monthly Close", "Technical Status",
        ])

    # ---------------- Daily stage ----------------
    st.subheader("שלב 2 — SMA50 Daily")
    st.caption(
        "נבדקות רק המניות שעברו Monthly. החלון הוא כ-252 ימי מסחר. "
        "SMA50 חייב להיות גבוה יותר מאשר בתחילת החלון ובשיפוע לינארי חיובי; "
        "המחיר הנוכחי חייב להיות מעל/נוגע ב-SMA50; ונדרשות לפחות 5 חציות מאושרות. "
        "חציה נספרת רק אחרי 2 ימי מסחר רצופים בצד החדש של SMA50 כדי לצמצם רעש."
    )

    daily_est = max(0, (len(monthly_passed) - 1) // credits)
    st.warning(
        f"שלב Daily ירוץ על {len(monthly_passed)} מניות בלבד. במכסה של {credits} מניות בדקה, "
        f"הוא עשוי לקחת בערך {daily_est} דקות."
    )

    if st.button("הרץ שלב 2 — SMA50 Daily + לפחות 5 חציות", type="primary"):
        progress_bar_d = st.progress(0)
        status_box_d = st.empty()

        def update_daily(done: int, total: int, msg: str) -> None:
            pct = 0 if total <= 0 else min(100, int(done / total * 100))
            progress_bar_d.progress(pct)
            status_box_d.info(msg)

        with st.spinner("מוריד נתונים יומיים ומחשב SMA50…"):
            daily_tech, error = screen_daily_tickers(
                [r["Ticker"] for r in monthly_passed],
                api_key=api_key,
                credits_per_minute=credits,
                progress=update_daily,
            )

        if error:
            st.error(error)
            st.stop()

        final_passed, daily_failed, daily_no_data = [], [], []
        for row in monthly_passed:
            t = row["Ticker"]
            info = daily_tech.get(t) or {
                "Daily Pass": False,
                "Daily Status": "לא התקבלו נתונים יומיים מ-Twelve Data",
                "Daily Points": 0,
            }
            merged = {**row, **info}
            if not info.get("Daily Points"):
                daily_no_data.append(merged)
            elif info.get("Daily Pass"):
                final_passed.append(merged)
            else:
                daily_failed.append(merged)

        st.session_state["daily_results_v08"] = (final_passed, daily_failed, daily_no_data)
        progress_bar_d.progress(100)
        status_box_d.success("שלב 2 הסתיים.")

    if "daily_results_v08" in st.session_state:
        final_passed, daily_failed, daily_no_data = st.session_state["daily_results_v08"]
        x, y, z = st.columns(3)
        x.metric("⭐ עברו Levli סופי", len(final_passed))
        y.metric("נפסלו Daily", len(daily_failed))
        z.metric("ללא נתונים יומיים", len(daily_no_data))

        st.subheader("אבחון שלב Daily — כל 87 המניות")
        diagnostic_daily = sorted(
            final_passed + daily_failed + daily_no_data,
            key=lambda r: (-(r.get("Daily Crossings") or -1), str(r.get("Ticker", ""))),
        )
        table(diagnostic_daily, [
            "Ticker", "Company", "Industry", "Daily Pass", "Daily Status", "Daily Points",
            "Daily SMA50 Start", "Daily SMA50 Now", "Daily SMA50 Change %",
            "Daily Close", "Daily Distance %", "Daily Crossings", "Days Above SMA50 %",
        ])
        st.caption("טבלת האבחון מציגה גם מניות שנפסלו, כדי לראות בדיוק איזה תנאי הפיל כל מניה וכמה חציות נספרו.")

        st.subheader("⭐ עברו Levli — Monthly + Daily")
        final_rows = []
        for r in final_passed:
            out = result_row(r)
            out.update({
                "Daily SMA50 Now": r.get("Daily SMA50 Now"),
                "Daily Close": r.get("Daily Close"),
                "Daily Distance %": r.get("Daily Distance %"),
                "Daily SMA50 Change %": r.get("Daily SMA50 Change %"),
                "Daily Crossings": r.get("Daily Crossings"),
                "Days Above SMA50 %": r.get("Days Above SMA50 %"),
                "MA50 Change %": r.get("MA50 Change %"),
                "MA50 Up Months": r.get("MA50 Up Months"),
            })
            final_rows.append(out)

        final_rows.sort(
            key=lambda r: (len(r.get("Levli Score", "")), str(r.get("Ticker", ""))),
            reverse=True,
        )

        table(final_rows, [
            "Ticker", "Company", "Industry", "Levli Score",
            "Daily Close", "Daily SMA50 Now", "Daily Distance %", "Daily SMA50 Change %",
            "Daily Crossings", "Days Above SMA50 %",
            "MA50 Change %", "MA50 Up Months",
            "P/E", "Forward P/E", "P/S", "Quick Ratio", "ROE %", "ROIC %",
            "Gross Margin %", "Profit Margin %", "EPS Growth %", "Forward EPS Growth %", "Growth Status",
        ])

        with st.expander("נפסלו בשלב Daily והסיבה"):
            table(daily_failed, [
                "Ticker", "Company", "Industry", "Daily Status", "Daily Points", "Daily SMA50 Start",
                "Daily SMA50 Now", "Daily SMA50 Change %", "Daily Close", "Daily Distance %",
                "Daily Crossings", "Days Above SMA50 %",
            ])

        if daily_no_data:
            with st.expander("לא התקבלו מספיק נתונים יומיים מ-Twelve Data"):
                table(daily_no_data, ["Ticker", "Company", "Industry", "Daily Status", "Daily Points"])

    with st.expander("נפסלו בשלב Monthly והסיבה"):
        table(monthly_failed, [
            "Ticker", "Company", "Industry", "Technical Status", "Monthly Points", "MA50 Start", "MA50 Now",
            "MA50 Change %", "MA50 Up Months", "Monthly Close",
        ])

    if monthly_no_data:
        with st.expander("לא התקבלו מספיק נתונים חודשיים מ-Twelve Data"):
            table(monthly_no_data, ["Ticker", "Company", "Industry", "Technical Status", "Monthly Points"])

with st.expander("נפסלו פונדמנטלית והסיבה"):
    table([diagnostic_row(r) for r in fund_failed], ["Ticker", "Company", "Industry", "Failed Criteria"])

st.caption(
    "מקור המחירים הטכניים: Twelve Data. Finviz נשאר מקור הסינון הפונדמנטלי. "
    "המפתח נשמר ב-Streamlit Secrets בלבד."
)
