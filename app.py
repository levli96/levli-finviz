from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import streamlit as st

from levli_logic import diagnostic_row, parse_finviz_csv, result_row, screen_rows
from technical_twelvedata import screen_daily_tickers, screen_tickers, test_connection
from finviz_api import download_finviz_csv, FinvizAPIError

st.set_page_config(
    page_title="Levli Score",
    page_icon="⭐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

STATE_FILE = Path("/tmp/levli_v082_state.json")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    try:
        return value.item()
    except Exception:
        return str(value)


def save_run_state() -> None:
    keys = [
        "source_rows_v082", "fund_passed_v082", "fund_failed_v082",
        "monthly_results_v08", "daily_results_v08",
    ]
    payload = {k: _json_safe(st.session_state[k]) for k in keys if k in st.session_state}
    try:
        STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def restore_run_state() -> bool:
    if not STATE_FILE.exists():
        return False
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        for k, v in payload.items():
            if k not in st.session_state:
                st.session_state[k] = v
        return bool(payload)
    except Exception:
        return False

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


st.markdown("""
# ⭐ Levli Score
### Stock Screening System

**Fundamental → MA50 Monthly → SMA50 Daily → Levli Score**

---
""")

st.html("""<style>
.dashboard-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-top: 20px;
    margin-bottom: 24px;
}

.dashboard-card {
    background: linear-gradient(145deg, #182331, #101820);
    border: 1px solid #26384a;
    border-radius: 16px;
    padding: 22px;
    min-height: 125px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.20);
}

.dashboard-card:hover {
    border-color: #4da3ff;
    transform: translateY(-2px);
    transition: 0.2s ease;
}

.card-step {
    color: #7f8c9a;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 10px;
}

.card-title {
    color: #ffffff;
    font-size: 21px;
    font-weight: 700;
    margin-bottom: 8px;
}

.card-subtitle {
    color: #9fb0c0;
    font-size: 14px;
}

.card-status {
    margin-top: 14px;
    color: #4da3ff;
    font-size: 13px;
    font-weight: 600;
}

@media (max-width: 900px) {
    .dashboard-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}
</style>

<div class="dashboard-grid">

    <div class="dashboard-card">
        <div class="card-step">STEP 01</div>
        <div class="card-title">📥 Data Source</div>
        <div class="card-subtitle">טעינת נתוני המניות למערכת</div>
        <div class="card-status">Ready</div>
    </div>

    <div class="dashboard-card">
        <div class="card-step">STEP 02</div>
        <div class="card-title">📊 Fundamental</div>
        <div class="card-subtitle">בדיקת 6 התנאים הפונדמנטליים</div>
        <div class="card-status">Screening</div>
    </div>

    <div class="dashboard-card">
        <div class="card-step">STEP 03</div>
        <div class="card-title">📈 MA50 Monthly</div>
        <div class="card-subtitle">בדיקת מגמת העלייה החודשית</div>
        <div class="card-status">Trend Filter</div>
    </div>

    <div class="dashboard-card">
        <div class="card-step">STEP 04</div>
        <div class="card-title">⭐ Levli Final</div>
        <div class="card-subtitle">המניות שעברו את כל הסינון</div>
        <div class="card-status">Final Results</div>
    </div>

</div>
""")
api_key = get_api_key()
credits = get_credits()



restore_run_state()
finviz_token = str(st.secrets.get("FINVIZ_API_TOKEN", "")).strip()
finviz_export_url = str(st.secrets.get("FINVIZ_EXPORT_URL", "")).strip()
use_auto_finviz = st.button("🚀 משוך סינון עדכני אוטומטית מ-Finviz")
if use_auto_finviz:
    try:
        finviz_df = download_finviz_csv(finviz_export_url, finviz_token)

        rows = parse_finviz_csv(finviz_df.to_csv(index=False))
        rows = list({r["Ticker"]: r for r in rows if r.get("Ticker")}.values())

        current_tickers = sorted(r["Ticker"] for r in rows)
        previous_tickers = sorted(
            r["Ticker"] for r in st.session_state.get("source_rows_v082", [])
        )

        if current_tickers != previous_tickers:
            st.session_state.pop("monthly_results_v08", None)
            st.session_state.pop("daily_results_v08", None)

        fund_passed, fund_failed = screen_rows(rows)

        st.session_state["source_rows_v082"] = rows
        st.session_state["fund_passed_v082"] = fund_passed
        st.session_state["fund_failed_v082"] = fund_failed

        save_run_state()

        st.success(
            f"✅ Finviz חובר בהצלחה — התקבלו {len(rows)} מניות, "
            f"{len(fund_passed)} עברו פונדמנטלי"
        )
        st.rerun()

    except (FinvizAPIError, ValueError) as exc:
        st.error(str(exc))
st.markdown("### 📥 Load Market Data")

upload_col, status_col = st.columns([3, 1])

with upload_col:
    uploaded = st.file_uploader(
        "Upload Finviz CSV",
        type=["csv"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

with status_col:
    st.metric("DATA SOURCE", "CSV")

if uploaded:
    rows: list[dict[str, Any]] = []
    try:
        for f in uploaded:
            rows += parse_finviz_csv(f.getvalue().decode("utf-8-sig", errors="replace"))
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    rows = list({r["Ticker"]: r for r in rows if r.get("Ticker")}.values())
    current_tickers = sorted(r["Ticker"] for r in rows)
    previous_tickers = sorted(r["Ticker"] for r in st.session_state.get("source_rows_v082", []))
    if current_tickers != previous_tickers:
        st.session_state.pop("monthly_results_v08", None)
        st.session_state.pop("daily_results_v08", None)

    fund_passed, fund_failed = screen_rows(rows)
    st.session_state["source_rows_v082"] = rows
    st.session_state["fund_passed_v082"] = fund_passed
    st.session_state["fund_failed_v082"] = fund_failed
    save_run_state()
else:
    rows = st.session_state.get("source_rows_v082", [])
    fund_passed = st.session_state.get("fund_passed_v082", [])
    fund_failed = st.session_state.get("fund_failed_v082", [])
    if not rows:
        st.stop()
    st.success("שוחזרה אוטומטית ההרצה האחרונה. אין צורך להעלות שוב את ה-CSV או להריץ מחדש שלבים שכבר הסתיימו.")

st.markdown("### 📊 Screening Overview")

monthly_results = st.session_state.get("monthly_results_v08", ([], [], []))
daily_results = st.session_state.get("daily_results_v08", ([], [], []))

monthly_passed = monthly_results[0] if monthly_results else []
final_passed = daily_results[0] if daily_results else []

st.html(f"""
<style>
.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin: 12px 0 28px 0;
}}

.kpi-card {{
    background: #141e29;
    border: 1px solid #2a3b4d;
    border-radius: 14px;
    padding: 18px 20px;
}}

.kpi-label {{
    color: #8fa3b8;
    font-size: 13px;
    font-weight: 600;
}}

.kpi-value {{
    color: white;
    font-size: 34px;
    font-weight: 700;
    margin-top: 6px;
}}

.kpi-final {{
    border-color: #c7a52b;
}}

@media (max-width: 900px) {{
    .kpi-grid {{
        grid-template-columns: repeat(2, 1fr);
    }}
}}
</style>

<div class="kpi-grid">

<div class="kpi-card">
    <div class="kpi-label">STOCKS LOADED</div>
    <div class="kpi-value">{len(rows)}</div>
</div>

<div class="kpi-card">
    <div class="kpi-label">FUNDAMENTAL PASS</div>
    <div class="kpi-value">{len(fund_passed)}</div>
</div>

<div class="kpi-card">
    <div class="kpi-label">MA50 MONTHLY</div>
    <div class="kpi-value">{len(monthly_passed)}</div>
</div>

<div class="kpi-card kpi-final">
    <div class="kpi-label">⭐ LEVLI FINAL</div>
    <div class="kpi-value">{len(final_passed)}</div>
</div>

</div>
""")

# ---------------- Monthly stage ----------------
monthly_est = max(0, (len(fund_passed) - 1) // credits)

st.html(f"""
<div style="
    background:#141e29;
    border:1px solid #2a3b4d;
    border-radius:16px;
    padding:22px 24px;
    margin:18px 0 14px 0;
">
    <div style="font-size:13px;color:#7f93a8;font-weight:600;">
        STEP 1 · TECHNICAL SCREENING
    </div>

    <div style="font-size:24px;color:white;font-weight:700;margin-top:6px;">
        📈 MA50 Monthly
    </div>

    <div style="color:#9fb0c0;margin-top:8px;">
        בדיקת מגמת עלייה חודשית באמצעות MA50 לאורך כ־24 חודשים
    </div>

    <div style="display:flex;gap:40px;margin-top:20px;">
        <div>
            <div style="font-size:12px;color:#7f93a8;">STOCKS TO CHECK</div>
            <div style="font-size:26px;font-weight:700;color:white;">
                {len(fund_passed)}
            </div>
        </div>

        <div>
            <div style="font-size:12px;color:#7f93a8;">ESTIMATED TIME</div>
            <div style="font-size:26px;font-weight:700;color:white;">
                ~{monthly_est} min
            </div>
        </div>

        <div>
            <div style="font-size:12px;color:#7f93a8;">DATA SOURCE</div>
            <div style="font-size:18px;font-weight:700;color:#4da3ff;">
                Twelve Data
            </div>
        </div>
    </div>
</div>
""")
if st.button("▶ הרץ MA50 Monthly", type="primary"):
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
    save_run_state()
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
daily_est = max(0, (len(monthly_passed) - 1) // credits)

st.html(f"""
    <div style="
        background:#141c29;
        border:1px solid #26384a;
        border-radius:14px;
        padding:20px 24px;
        margin-top:22px;
        margin-bottom:14px;
    ">
        <div style="font-size:12px;color:#7f93a8;font-weight:700;">
            STEP 2 · TECHNICAL SCREENING
        </div>

        <div style="font-size:24px;color:white;font-weight:700;margin-top:6px;">
            📈 SMA50 Daily
        </div>

        <div style="color:#9fb0c0;margin-top:8px;">
            בדיקת מגמה יומית לאורך כשנה + לפחות 5 חציות מאושרות של SMA50
        </div>

        <div style="display:flex;gap:40px;margin-top:20px;">
            <div>
                <div style="font-size:12px;color:#7f93a8;">STOCKS TO CHECK</div>
                <div style="font-size:26px;font-weight:700;color:white;">
                    {len(monthly_passed)}
                </div>
            </div>

            <div>
                <div style="font-size:12px;color:#7f93a8;">ESTIMATED TIME</div>
                <div style="font-size:26px;font-weight:700;color:white;">
                    ~{daily_est} min
                </div>
            </div>

            <div>
                <div style="font-size:12px;color:#7f93a8;">DATA SOURCE</div>
                <div style="font-size:18px;font-weight:700;color:#4da3ff;">
                    Twelve Data
                </div>
            </div>
        </div>
    </div>
""")

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
        save_run_state()
        progress_bar_d.progress(100)
        status_box_d.success("שלב 2 הסתיים.")
        st.rerun()       
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
        table(st.session_state["monthly_results_v08"][1], [
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
