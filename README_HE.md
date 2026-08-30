
# Levli — Finviz v0.4

גרסת Finviz Only שמונעת תוצאה מטעה של "עברו Levli" ללא בדיקת מגמת Monthly.

## סדר העבודה
1. Finviz Custom Export כולל גם `IPO Date`.
2. Levli פוסלת אוטומטית מניות עם פחות מ-2 שנות היסטוריית מסחר.
3. Levli מפעילה את תנאי הפונדמנטל.
4. התוצאה בשלב הזה היא **Candidates for Monthly Review**, לא "עברו Levli".
5. עוברים על המועמדות ב-Finviz Charts עם התבנית `Levli Monthly MA50`.
6. מדביקים באפליקציה רק את ה-Tickers שאושרו ויזואלית כמגמת עלייה מובהקת עם SMA50.
7. רק אז הם מופיעים תחת "עברו Levli".

## למה זה בנוי כך
Finviz מאפשר להציג גרף Monthly ו-SMA50, אך אינו מייצא raw historical price data שמאפשר לאפליקציה לחשב אוטומטית את שיפוע SMA50 לאורך שנתיים. v0.4 לא מנסה לזייף את הבדיקה הזו.

אין צורך ב-FMP API Key.
