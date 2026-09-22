# -*- coding: utf-8 -*-
"""买入信号生成 (2026-09-08, 周二/交易日).
与回测引擎 passPreFilter 同源：⑤ 大盘硬过滤 + 容差 + 全市场过滤(趋势+量能+缺口)。
westock-mcp 在本自动化环境不可用 -> 走腾讯公开端点兜底。
数据源优先级：Sina(主) -> web.ifzq.gtimg.cn(备) -> proxy.finance.qq.com(stale检测) -> eastmoney(指数仅)。
import_final.json 的 kline.day 末棒停在 2026-09-04(周五)，缺失 09-07(周一)，故对 Top3 重拉新鲜日K(丢弃当日未完成棒)，
以 09-07 完成棒作为基准/信号日，与回测 signal-day=前一交易日对齐；重拉失败则回退 import_final kline。
"""
import json, urllib.request, sys, time

TODAY = "2026-09-08"
FQ = "D:/WorkBuddy/选股结果/import_final.json"
OUT = "D:/WorkBuddy/选股结果/buy_signal.json"
SINA = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=%s&scale=240&ma=5&datalen=40"
WEBIFZQ = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s,day,2026-08-01,2030-01-01,40,qfq"
PROXY = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get?param=%s,day,2026-08-01,2030-01-01,40,qfq"
QT = "https://qt.gtimg.cn/q="
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}
FRESH_MIN = "2026-08-15"  # 接受该日期之后的最新棒，否则视为 stale

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def pref(code):
    c = code[0]
    return ("sh" if c in "69" else "sz") + code

# ---- 数据源：Sina (主) ----
def sym(code):
    return code if code.startswith(("sh", "sz")) else pref(code)

def sina_kline(code):
    """返回 oldest-first [[date,open,close,high,low,volume]]；stale 检测。"""
    try:
        u = SINA % sym(code)
        arr = json.loads(http_get(u).decode("utf-8", errors="ignore"))
        if not arr:
            return None
        rows = [[x["day"], float(x["open"]), float(x["close"]), float(x["high"]), float(x["low"]), float(x["volume"])] for x in arr]
        rows = [r for r in rows if r[0] < TODAY]
        if not rows or rows[-1][0] < FRESH_MIN:
            return None
        return rows
    except Exception as e:
        print("  sina %s 出错: %s" % (code, repr(e)[:80]))
        return None

def webifzq_kline(code):
    try:
        u = WEBIFZQ % sym(code)
        j = json.loads(http_get(u).decode("utf-8", errors="ignore"))
        data = j.get("data", {})
        node = None
        for k in data:
            node = data[k]; break
        arr = node.get("qfqday") or node.get("day")
        if not arr:
            return None
        rows = [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])] for r in arr]
        rows.reverse()
        rows = [r for r in rows if r[0] < TODAY]
        if not rows or rows[-1][0] < FRESH_MIN:
            return None
        return rows
    except Exception as e:
        print("  webifzq %s 出错: %s" % (code, repr(e)[:80]))
        return None

def proxy_kline(code):
    try:
        u = PROXY % sym(code)
        j = json.loads(http_get(u).decode("utf-8", errors="ignore"))
        data = j.get("data", {})
        node = None
        for k in data:
            node = data[k]; break
        arr = node.get("qfqday") or node.get("day")
        if not arr:
            return None
        rows = [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])] for r in arr]
        rows.reverse()
        rows = [r for r in rows if r[0] < TODAY]
        if not rows or rows[-1][0] < FRESH_MIN:
            return None
        return rows
    except Exception as e:
        print("  proxy %s 出错: %s" % (code, repr(e)[:80]))
        return None

def fresh_kline(code):
    """多源依次尝试，返回 oldest-first 新鲜日K。"""
    for fn in (sina_kline, webifzq_kline, proxy_kline):
        r = fn(code)
        if r:
            return r, fn.__name__
    return None, None

def _sh_em():
    try:
        u = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.000001&fields1=f1&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1&end=20500101&lmt=30"
        j = json.loads(http_get(u).decode("utf-8", errors="ignore"))
        kl = j.get("data", {}).get("klines", [])
        if not kl:
            return None
        rows = []
        for s in kl:
            p = s.split(",")
            rows.append([p[0], float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5])])
        rows = [r for r in rows if r[0] < TODAY]
        return rows if rows and rows[-1][0] >= FRESH_MIN else None
    except Exception as e:
        print("  eastmoney 兜取出错:", repr(e)[:80])
        return None

def get_sh_index():
    """返回 (last_close, ma20, last_date)。源：sina -> webifzq -> proxy -> eastmoney。"""
    rows = None; src = None
    for fn, name in ((sina_kline, "sina"), (webifzq_kline, "webifzq"), (proxy_kline, "proxy")):
        rows = fn("sh000001")
        if rows:
            src = name; break
        time.sleep(1)
    if not rows:
        rows = _sh_em()
        src = "eastmoney" if rows else None
    if not rows or len(rows) < 20:
        return None
    closes = [r[2] for r in rows[-20:]]
    ma20 = sum(closes) / 20
    last = rows[-1]
    print("  上证数据源=%s 末棒=%s 收=%.2f MA20=%.2f" % (src, last[0], last[2], ma20))
    return (last[2], ma20, last[0])

def get_opens(codes):
    q = QT + ",".join(pref(c) for c in codes)
    raw = http_get(q).decode("gbk", errors="ignore")
    out = {}
    for line in raw.split(";"):
        line = line.strip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        m = key.strip().strip("v_")
        val = val.strip().strip('"')
        if not val:
            continue
        f = val.split("~")
        code = m[2:] if m.startswith(("sh", "sz")) else m
        try:
            out[code] = {
                "name": f[1],
                "price": float(f[3]) if f[3] else None,
                "prev": float(f[4]) if f[4] else None,
                "open": float(f[5]) if f[5] else None,
                "time": f[30] if len(f) > 30 else "",
            }
        except (ValueError, IndexError):
            continue
    return out

# ---- 1) 载入 import_final (Top3 by win 降序) ----
with open(FQ, encoding="utf-8") as f:
    data = json.load(f)
items = data.get("items", [])
if not items:
    print("NO_ITEMS"); sys.exit(2)
items_sorted = sorted(items, key=lambda x: float(x.get("win", 0) or 0), reverse=True)
top3 = items_sorted[:3]
print("import_final items:", len(items))
for it in top3:
    print("  Top3:", it.get("code"), it.get("name"), it.get("board"), "win=", it.get("win"))

# ---- 2) 上证 大盘硬过滤 ----
market = get_sh_index()
if market is None:
    print("上证抓取失败 -> 降级 trade:false")
    signal = {"date": TODAY, "baselineDate": "2026-09-07", "top3": [], "trade": False,
              "note": "westock-mcp不可用且所有公开端点取上证指数失败，无法判定大盘环境，降级为 trade:false"}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(signal, f, ensure_ascii=False, indent=2)
    print("WROTE", OUT)
    sys.exit(0)
last_close, ma20, last_date = market
market_ok = last_close >= ma20
print("上证 末棒 %s 收 %.2f MA20 %.2f -> %s" % (last_date, last_close, ma20, "多头" if market_ok else "空头"))

# ---- 3) 个股 kline：重拉新鲜(优先) / import_final 回退 ----
codes = [it.get("code") for it in top3]
results = []
for it in top3:
    code = it.get("code"); name = it.get("name"); board = it.get("board"); win = float(it.get("win", 0) or 0)
    rk_imp = it.get("kline", {}).get("day", [])
    fresh, fsrc = fresh_kline(code)
    use_rk = None; src = None
    if fresh and len(fresh) >= 20:
        use_rk, src = fresh, fsrc
    elif rk_imp and len(rk_imp) >= 20:
        use_rk, src = rk_imp, "import_final"
    base_date = use_rk[-1][0] if use_rk else None
    baseline = round(use_rk[-1][2], 4) if use_rk else None
    fdetail = "N/A"
    if use_rk and len(use_rk) >= 20:
        close = use_rk[-1][2]; o = use_rk[-1][1]; prevClose = use_rk[-2][2]; vol = use_rk[-1][5]
        ma5 = sum(r[2] for r in use_rk[-5:]) / 5
        ma20k = sum(r[2] for r in use_rk[-20:]) / 20
        ma20prev = sum(r[2] for r in use_rk[-21:-1]) / 20
        ma20vol = sum(r[5] for r in use_rk[-20:]) / 20
        trendOK = (close > ma20k) and (ma5 > ma20k) and (ma20k > ma20prev)
        volOK = vol >= 1.2 * ma20vol
        gap = (o - prevClose) / prevClose
        gapOK = (-0.04 <= gap <= 0.06)
        fdetail = "趋势%s 量能%s(%.0f/%.0f=%.2f) 缺口%s(%.4f)" % (
            "OK" if trendOK else "NG", "OK" if volOK else "NG", vol, ma20vol, vol / ma20vol if ma20vol else 0,
            "OK" if gapOK else "NG", gap)
    else:
        fdetail = "重拉失败/不足20根"
    results.append({"code": code, "name": name, "board": board, "win": win,
                    "baseline": baseline, "baselineDate": base_date, "filter_detail": fdetail, "src": src})
    print("  %s 基准日=%s 源=%s 基准=%.4f 过滤[%s]" % (code, base_date, src, baseline or 0, fdetail))

if not market_ok:
    signal = {"date": TODAY, "baselineDate": last_date, "top3": [], "trade": False,
              "note": "大盘空头(上证<MA20)：上证 %s 收 %.2f < MA20 %.2f，当日全市场不交易" % (last_date, last_close, ma20)}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(signal, f, ensure_ascii=False, indent=2)
    print("WROTE", OUT)
    sys.exit(0)

baseline_date = results[0]["baselineDate"] if results else "2026-09-07"
print("统一 baselineDate =", baseline_date)

# ---- 4) 实时开盘价（qt.gtimg.cn） ----
opens = get_opens(codes)

# ---- 5) 容差 + 全市场过滤 ----
top3_out = []
any_buy = False
for r in results:
    tol = 0.03 if r["board"] in ("cyb", "kcb", "kc") else 0.02
    op = opens.get(r["code"])
    openpx = op.get("open") if op else None
    reason = None
    decision = "hold"
    dev = None
    if openpx is None:
        reason = "抓不到实时开盘价(qt.gtimg.cn)，无法确认买入"
    else:
        dev = round((openpx - r["baseline"]) / r["baseline"], 4)
        if abs(dev) > tol:
            decision = "hold"
            reason = "容差未过 |dev|=%.4f > %.4f" % (abs(dev), tol)
        else:
            if "不足20根" in r["filter_detail"] or "重拉失败" in r["filter_detail"]:
                decision = "hold"; reason = "全市场过滤未过(历史不足20根)"
            elif not ("趋势OK" in r["filter_detail"] and "量能OK" in r["filter_detail"] and "缺口OK" in r["filter_detail"]):
                decision = "hold"; reason = "过滤未过: " + r["filter_detail"]
            else:
                decision = "buy"; any_buy = True
        prev = op.get("prev") if op else None
        if prev is not None and r["baseline"] is not None:
            diff = abs(prev - r["baseline"]) / r["baseline"]
            if diff > 0.01:
                reason = (reason + " | " if reason else "") + "⚠昨收%.2f与基准%.2f偏差%.1f%%" % (prev, r["baseline"], diff * 100)
    top3_out.append({
        "code": r["code"], "name": r["name"], "board": r["board"], "win": r["win"],
        "baseline": r["baseline"], "open": openpx, "dev": dev, "tol": tol,
        "decision": decision, "reason": reason,
    })
    print("  %s %s 基准%.4f 开%.4f dev=%s 容差%.2f 过滤[%s] -> %s" % (
        r["code"], r["name"], r["baseline"] or 0, openpx or 0, dev, tol, r["filter_detail"], decision))

signal = {
    "date": TODAY, "baselineDate": baseline_date, "top3": top3_out, "trade": any_buy,
    "note": "大盘多头(上证%s收%.2f>=MA20%.2f)；westock-mcp不可用, 走腾讯/Sina公开端点兜底；Top3 基准确认源=fresh-repull优先" % (last_date, last_close, ma20),
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(signal, f, ensure_ascii=False, indent=2)
print("WROTE", OUT, "trade=", any_buy)
print(json.dumps(signal, ensure_ascii=False, indent=2))
