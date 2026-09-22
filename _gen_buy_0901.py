# -*- coding: utf-8 -*-
import json, urllib.request, datetime, sys, os

BASE = "D:/WorkBuddy"
SRC = os.path.join(BASE, "选股结果", "import_final.json")
OUT = os.path.join(BASE, "选股结果", "buy_signal.json")
TODAY = "2026-09-01"

def http_get(url, enc="utf-8", timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=timeout).read().decode(enc, errors="replace")

def prefix(code):
    return ("sh" if code[0] in "69" else "sz") + code

# ---- 1) load source ----
with open(SRC, "r", encoding="utf-8") as f:
    data = json.load(f)
updated = data.get("updated") or data.get("date") or ""
baselineDate = updated[:10] if updated else ""
items = data.get("items", [])
print("items:", len(items), "| baselineDate:", baselineDate)

# ---- 2) 大盘硬过滤 (sh000001 MA20) ----
def index_bearish():
    try:
        u = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,2025-06-01,2026-12-31,60,qfq"
        j = json.loads(http_get(u))
        node = j["data"]["sh000001"]["day"]
        closes = [float(b[2]) for b in node[-20:]]
        ma20 = sum(closes) / len(closes)
        last_close = float(node[-1][2])
        return (last_close < ma20), last_close, ma20, node[-1][0]
    except Exception as e:
        print("index fetch ERR:", repr(e))
        return None, None, None, None

bearish, idx_last, idx_ma20, idx_date = index_bearish()
print("INDEX sh000001 last_close=%.2f MA20=%.2f date=%s -> bearish=%s" % (idx_last, idx_ma20, idx_date, bearish))

if bearish:
    out = {
        "date": TODAY,
        "baselineDate": baselineDate,
        "top3": [],
        "trade": False,
        "reason": "大盘空头(上证<MA20)  sh000001 last=%.2f MA20=%.2f" % (idx_last, idx_ma20),
        "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("WROTE trade:false (大盘空头) ->", OUT)
    sys.exit(0)

# ---- 3) Top3 by win ----
ranked = sorted(items, key=lambda x: float(x.get("win") or 0), reverse=True)
top3 = ranked[:3]
print("TOP3:", [(t["code"], t["name"], t["win"]) for t in top3])

# ---- 4) fetch realtime open for Top3 ----
codes = [prefix(t["code"]) for t in top3]
q = "https://qt.gtimg.cn/q=" + ",".join(codes)
s = http_get(q, enc="gbk")
quotes = {}
for line in s.strip().split(";"):
    line = line.strip()
    if not line.startswith("v_"):
        continue
    try:
        code = line[2:line.index("=")]
        body = line[line.index('"')+1:line.rindex('"')]
        a = body.split("~")
        quotes[code] = {"open": a[5], "last": a[3], "prevclose": a[4], "name": a[1]}
    except Exception:
        pass
print("quotes:", quotes)

# ---- 5) evaluate ----
def tol_for(board):
    b = (board or "").lower()
    if b == "main":
        return 0.02
    return 0.03  # cyb / kcb / kc

def market_filter(day):
    if len(day) < 20:
        return False, "历史根数<20,MA20不可算"
    closes = [float(b[2]) for b in day]
    vols = [float(b[5]) for b in day]
    close = float(day[-1][2]); o = float(day[-1][1]); prevClose = float(day[-2][2]); vol = float(day[-1][5])
    ma5 = sum(closes[-5:]) / 5
    ma20 = sum(closes[-20:]) / 20
    ma20_prev = sum(closes[-21:-1]) / 20
    ma20vol = sum(vols[-20:]) / 20
    trend_ok = (close > ma20) and (ma5 > ma20) and (ma20 > ma20_prev)
    vol_ok = vol >= 1.2 * ma20vol
    gap = (o - prevClose) / prevClose
    gap_ok = (-0.04 <= gap <= 0.06)
    passed = trend_ok and vol_ok and gap_ok
    detail = "trend=%s vol=%s(%.0f>=%.0f) gap=%.4f(%s)" % (
        trend_ok, vol_ok, vol, 1.2*ma20vol, gap, gap_ok)
    return passed, detail

result_top3 = []
any_buy = False
for t in top3:
    code = t["code"]; name = t["name"]; board = t.get("board")
    win = float(t.get("win") or 0)
    day = (t.get("kline") or {}).get("day") or []
    baseline = day[-1][2] if day else None
    pc = prefix(code)
    q = quotes.get(pc, {})
    open_px = None
    try:
        open_px = float(q.get("open"))
    except Exception:
        open_px = None
    entry = {
        "code": code,
        "name": name,
        "board": board,
        "win": win,
        "baseline": baseline,
        "open": open_px,
    }
    if baseline is None or open_px is None:
        entry["decision"] = "hold"
        entry["reason"] = "无开盘价/基线" if open_px is None else "无基线"
        entry["dev"] = None
        entry["tol"] = tol_for(board)
    else:
        dev = (open_px - baseline) / baseline
        tol = tol_for(board)
        entry["dev"] = round(dev, 4)
        entry["tol"] = tol
        if abs(dev) > tol:
            entry["decision"] = "hold"
            entry["reason"] = "偏离超容差 dev=%.4f tol=%.2f%%" % (dev, tol*100)
        else:
            passed, detail = market_filter(day)
            if passed:
                entry["decision"] = "buy"
                any_buy = True
            else:
                entry["decision"] = "hold"
                entry["reason"] = "过滤未过 " + detail
    result_top3.append(entry)
    print(entry)

out = {
    "date": TODAY,
    "baselineDate": baselineDate,
    "top3": result_top3,
    "trade": any_buy,
    "index": {"sh000001": {"last": idx_last, "ma20": round(idx_ma20, 2), "bearish": False}},
    "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("WROTE", OUT, "| trade=", any_buy)
