from __future__ import annotations
from datetime import date,timedelta
from typing import Any
import requests

BASE="https://financialmodelingprep.com/stable"

def history(symbol:str,key:str)->list[dict[str,Any]]:
    start=(date.today()-timedelta(days=850)).isoformat()
    r=requests.get(f"{BASE}/historical-price-eod/full",params={"symbol":symbol,"from":start,"apikey":key},timeout=30)
    if r.status_code==429: raise RuntimeError("429 — FMP rate limit")
    if r.status_code==402: raise RuntimeError("402 — FMP endpoint restriction")
    if r.status_code in (401,403): raise RuntimeError(f"{r.status_code} — FMP authorization")
    r.raise_for_status()
    d=r.json()
    if isinstance(d,dict): d=d.get("historical",[])
    rows=[x for x in d if isinstance(x,dict) and x.get("date") and x.get("close") is not None]
    rows.sort(key=lambda x:str(x["date"]))
    if len(rows)<260: raise RuntimeError("אין מספיק היסטוריית מסחר")
    return rows

def monthly_uptrend(rows):
    monthly={}
    for r in rows: monthly[str(r["date"])[:7]]=float(r["close"])
    vals=list(monthly.values())[-24:]
    if len(vals)<18: return False,0.0
    n=len(vals); xb=(n-1)/2; yb=sum(vals)/n
    slope=sum((i-xb)*(y-yb) for i,y in enumerate(vals))/(sum((i-xb)**2 for i in range(n)) or 1)
    first=sum(vals[:6])/6; last=sum(vals[-6:])/6
    pct=(last/first-1)*100 if first else 0
    return slope>0 and last>first,pct

def technical_check(symbol,key,tolerance=0.02,trend_days=20):
    rows=history(symbol,key); closes=[float(r["close"]) for r in rows]
    price=closes[-1]; ma50=sum(closes[-50:])/50
    end=len(closes)-trend_days; prior=sum(closes[end-50:end])/50
    rising=ma50>prior
    price_ok=price>=ma50*(1-tolerance)
    monthly_ok,pct=monthly_uptrend(rows)
    failed=[]
    if not monthly_ok: failed.append("2Y monthly uptrend")
    if not rising: failed.append("MA50 rising")
    if not price_ok: failed.append("Price touching/above MA50")
    return {"Price":price,"MA50":ma50,"MA50 Prior":prior,"Price vs MA50 %":(price/ma50-1)*100,
            "2Y Monthly Trend":f"{pct:.1f}% {'✅' if monthly_ok else '❌'}",
            "Technical Passed":not failed,"Technical Failed Criteria":", ".join(failed) if failed else "—"}
