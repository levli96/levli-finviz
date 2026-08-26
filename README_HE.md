
# Levli Finviz v0.1

גרסת ניסיון נפרדת של Levli המבוססת על Finviz Export.

## מה היא עושה
- קוראת CSV של Finviz Custom.
- אפשר להעלות כמה CSVים יחד והמערכת מסירה כפילויות לפי Ticker.
- מניחה שה־Preset ב־Finviz כבר מסנן `Price above SMA50`.
- מפעילה את תנאי החובה הפונדמנטליים של Levli:
  - P/E > Forward P/E
  - Quick Ratio > 1
  - ROE >= 12%
  - ROIC >= 9%
  - Gross Margin >= 38%
  - Profit Margin >= 7%
- מציגה P/S Status ו־Growth Status.
- מחשבת Levli Score בכוכבים בלבד.

## חשוב
`MA50 Rising` נשאר תנאי חובה ב־Levli, אך עדיין אינו נאכף בגרסה זו.
לא הוחלף אותו בקירוב. השלב הבא הוא חיבור בדיקת המגמה הטכנית למועמדות שעברו את הסינון הפונדמנטלי.

## העלאה ל־GitHub
מומלץ ליצור branch/Repository נפרד לגרסת Finviz כדי לא לפגוע בגרסת FMP העובדת.
