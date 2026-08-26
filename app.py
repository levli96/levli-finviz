from __future__ import annotations
import html, time
from typing import Any
import streamlit as st
from levli_logic import parse_finviz_csv, screen_rows
from technical import technical_check

st.set_page_config(page_title="Levli Finviz v0.2", page_icon="⭐", layout="wide")

def fmt(v: Any) -> str:
    if v is None: return "—"
    if isinstance(v,float): return f"{v:.2f}"
    return str(v)

def table(rows, cols):
    if not rows:
        st.info("אין נתונים להצגה."); return
    head="".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body="".join("<tr>"+"".join(f"<td>{html.escape(fmt(r.get(c)))}</td>" for c in cols)+"</tr>" for r in rows)
    st.markdown(f"""<div style="overflow-x:auto"><table style="border-collapse:collapse;width:100%;font-size:14px">
    <thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>
    <style>table th,table td{{border:1px solid #ddd;padding:7px;white-space:nowrap}}table th{{background:#f3f4f6;color:#111}}</style>""", unsafe_allow_html=True)

def saved_key():
    try: return str(st.secrets.get("FMP_API_KEY","")).strip()
    except Exception: return ""

st.title("Levli — Finviz v0.2")
st.caption("Finviz fundamentals + technical validation")
uploaded=st.file_uploader("העלה Finviz Custom CSV",type=["csv"],accept_multiple_files=True)
fmp_key=st.sidebar.text_input("FMP API Key — טכני בלבד",value=saved_key(),type="password")
touch=st.sidebar.slider("נגיעה ב-MA50: עד % מתחת לממוצע",0.0,5.0,2.0,0.5)
trend_days=st.sidebar.slider("MA50 עולה לעומת כמה ימי מסחר אחורה",10,40,20,5)
if not uploaded: st.stop()

rows=[]
for f in uploaded:
    rows += parse_finviz_csv(f.getvalue().decode("utf-8-sig",errors="replace"))
rows=list({r["Ticker"]:r for r in rows if r.get("Ticker")}.values())
fund_passed,fund_failed=screen_rows(rows)
a,b,c=st.columns(3)
a.metric("ניירות ב-Finviz",len(rows)); b.metric("עברו פונדמנטלי",len(fund_passed)); c.metric("נפסלו פונדמנטלי",len(fund_failed))
st.info("הבדיקה הטכנית רצה רק על המניות שעברו פונדמנטלית: מגמת עלייה חודשית ~2 שנים, MA50 יומי עולה, ומחיר נוגע/מעל MA50.")

if not fmp_key:
    st.warning("הזן FMP API Key בצד שמאל. הוא משמש רק להיסטוריית מחיר של המועמדות."); st.stop()

limit=st.sidebar.slider("מספר מועמדות לבדיקה טכנית",1,min(50,max(1,len(fund_passed))),min(10,max(1,len(fund_passed))))
if st.button("בדוק מגמה טכנית",type="primary"):
    good=[]; bad=[]; unavailable=[]
    progress=st.progress(0); status=st.empty(); start=time.perf_counter()
    for i,row in enumerate(fund_passed[:limit],1):
        status.info(f"בודק {row['Ticker']} ({i}/{limit})")
        try:
            tech=technical_check(row["Ticker"],fmp_key,touch/100,trend_days)
            merged={**row,**tech}
            (good if tech["Technical Passed"] else bad).append(merged)
        except Exception as e:
            unavailable.append({"Ticker":row["Ticker"],"Status":str(e)})
        progress.progress(i/limit)
        time.sleep(0.4)
    status.empty()
    x1,x2,x3,x4=st.columns(4)
    x1.metric("נבדקו",limit); x2.metric("עברו הכול",len(good)); x3.metric("נפסלו טכנית",len(bad)); x4.metric("זמן",f"{time.perf_counter()-start:.1f} שנ׳")
    st.subheader("מניות שעברו Levli")
    table(good,["Ticker","Company","Levli Score","Price","MA50","MA50 Prior","Price vs MA50 %","2Y Monthly Trend","P/E","Forward P/E","ROE %","ROIC %"])
    with st.expander("נפסלו טכנית והסיבה"):
        table(bad,["Ticker","Company","Price","MA50","MA50 Prior","Price vs MA50 %","2Y Monthly Trend","Technical Failed Criteria"])
    if unavailable:
        with st.expander("Data unavailable"):
            table(unavailable,["Ticker","Status"])
