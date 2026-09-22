# -*- coding: utf-8 -*-
"""买入信号生成 (2026-09-07, 周一/交易日).
与回测引擎 passPreFilter 同源：⑤ 大盘硬过滤 + 容差 + 全市场过滤(趋势+量能+缺口)。
westock-mcp 在本自动化环境不可用 -> 走腾讯公开端点兜底 (proxy.finance.qq.com 日K / qt.gtimg.cn 实时开盘价 gbk)。
directly 使用 import_final.json 的 kline.day（已刷新至 2026-09-04 完成棒，无需重拉）。
"""
import json, urllib.request, datetime, sys, os, time

TODAY = "2026-09-07"
FQ = "D:/WorkBuddy/选股结果/import_final.json"
OUT = "D:/WorkBuddy/选股结果/buy_signal.json"
PROXY = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get?param="
QT = "https://qt.gtimg.cn/q="
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def pref(code):
    c = code[0]
    return ("sh" if c in "69" else "sz") + code

def get_kline_proxy(code, limit=60, window=None):
    """proxy 返回 newest-first -> 转 oldest-first，最新完成棒在 rk[-1]。"""
    if window:
        url = PROXY + "%s,day,%s,%s,%d,qfq" % (pref(code), window[0], window[1], limit)
    else:
        url = PROXY + "%s,day,%d,qfq" % (pref(code), limit)
    j = json.loads(http_get(url).decode("utf-8", errors="ignore"))
    node = j["data"][pref(code)]
    arr = node.get("qfqday") or node.get("day")
    if not arr:
        return None
    out = [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])] for r in arr]
    out.reverse()
    return out

def _sh_rows_from(url):
    try:
        j = json.loads(http_get(url).decode("utf-8", errors="ignore"))
        node = j["data"]["sh000001"]
        arr = node.get("qfqday") or node.get("day")
        if not arr:
            return None
        rows = [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])] for r in arr]
        rows.reverse()  # oldest-first
        rows = [r for r in rows if r[0] < TODAY]  # 丢弃当日未完成棒
        return rows
    except Exception:
        return None

def _sh_rows_em():
    """eastmoney push2his 兜底：返回 oldest-first，含当日未完成棒则丢弃。"""
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
        rows = [r for r in rows if r[0] < TODAY]  # 丢弃当日未完成棒
        return rows if len(rows) >= 20 else None
    except Exception as e:
        print("  eastmoney 兜取出错:", repr(e)[:80])
        return None

def get_sh_index():
    """上证指数：proxy 主源带间隔重试(抗瞬时过期缓存) -> eastmoney 兜底。返回 (last_close, ma20, last_date)。"""
    fresh_cut = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    primary = PROXY + "sh000001,day,2025-01-01,2030-01-01,30,qfq"
    for attempt in range(3):  # 单源、少量间隔重试，避免限频
        rows = _sh_rows_from(primary)
        if rows and len(rows) >= 20 and rows[-1][0] >= fresh_cut:
            closes = [r[2] for r in rows[-20:]]
            ma20 = sum(closes) / 20
            last = rows[-1]
            return (last[2], ma20, last[0])
        time.sleep(3)
    # 兜底：eastmoney
    rows = _sh_rows_em()
    if rows and len(rows) >= 20:
        closes = [r[2] for r in rows[-20:]]
        ma20 = sum(closes) / 20
        last = rows[-1]
        return (last[2], ma20, last[0])
    return None

def get_opens(codes):
    """qt.gtimg.cn 批量实时快照 (gbk)。返回 {code: {'open':float,'prev':float,'price':float,'time':str}}。"""
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
        # f[0]=code f[1]=name f[3]=现价 f[4]=昨收 f[5]=今开 f[30]=时间
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
    signal = {"date": TODAY, "baselineDate": "2026-09-04", "top3": [], "trade": False,
              "note": "westock-mcp不可用且腾讯公开端点取上证指数失败，无法判定大盘环境，降级为 trade:false"}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(signal, f, ensure_ascii=False, indent=2)
    print("WROTE", OUT)
    sys.exit(0)
last_close, ma20, last_date = market
market_ok = last_close >= ma20
print("上证 末完成棒 %s 收 %.2f MA20 %.2f -> %s" % (last_date, last_close, ma20, "多头" if market_ok else "空头"))

if not market_ok:
    print("大盘空头 -> 全市场不交易")
    signal = {"date": TODAY, "baselineDate": "2026-09-04", "top3": [], "trade": False,
              "note": "大盘空头(上证<MA20)：上证 %s 收 %.2f < MA20 %.2f，当日全市场不交易" % (last_date, last_close, ma20)}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(signal, f, ensure_ascii=False, indent=2)
    print("WROTE", OUT)
    sys.exit(0)

# ---- 3) 基准 = kline.day 最后一根 [2] (09-04 完成棒) ----
codes = [it.get("code") for it in top3]
opens = get_opens(codes)

results = []
for it in top3:
    code = it.get("code"); name = it.get("name"); board = it.get("board"); win = float(it.get("win", 0) or 0)
    rk = it.get("kline", {}).get("day", [])
    baseline = round(rk[-1][2], 4) if rk else None
    base_date = rk[-1][0] if rk else None
    # 全市场过滤 (信号日=09-04 完成棒)
    fdetail = "N/A"
    if rk and len(rk) >= 20:
        close = rk[-1][2]; o = rk[-1][1]; prevClose = rk[-2][2]; vol = rk[-1][5]
        ma5 = sum(r[2] for r in rk[-5:]) / 5
        ma20 = sum(r[2] for r in rk[-20:]) / 20
        ma20prev = sum(r[2] for r in rk[-21:-1]) / 20
        ma20vol = sum(r[5] for r in rk[-20:]) / 20
        trendOK = (close > ma20) and (ma5 > ma20) and (ma20 > ma20prev)
        volOK = vol >= 1.2 * ma20vol
        gap = (o - prevClose) / prevClose
        gapOK = (-0.04 <= gap <= 0.06)
        fdetail = "趋势%s 量能%s(%.0f/%.0f=%.2f) 缺口%s(%.4f)" % (
            "OK" if trendOK else "NG", "OK" if volOK else "NG", vol, ma20vol, vol / ma20vol if ma20vol else 0,
            "OK" if gapOK else "NG", gap)
    else:
        fdetail = "重拉失败/不足20根"
    results.append({"code": code, "name": name, "board": board, "win": win,
                    "baseline": baseline, "baselineDate": base_date, "filter_detail": fdetail})

baseline_date = results[0]["baselineDate"] if results else "2026-09-04"
print("统一 baselineDate =", baseline_date)

# ---- 4) 实时开盘价（qt.gtimg.cn） ----
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
            # 全市场过滤
            if "不足20根" in r["filter_detail"] or "重拉失败" in r["filter_detail"]:
                decision = "hold"; reason = "全市场过滤未过(历史不足20根)"
            elif not ("趋势OK" in r["filter_detail"] and "量能OK" in r["filter_detail"] and "缺口OK" in r["filter_detail"]):
                decision = "hold"; reason = "过滤未过: " + r["filter_detail"]
            else:
                decision = "buy"
                any_buy = True
        # 交叉核验 昨收 ≈ baseline
        prev = op.get("prev") if op else None
        if prev is not None and r["baseline"] is not None:
            diff = abs(prev - r["baseline"]) / r["baseline"]
            if diff > 0.01:
                reason = (reason + " | " if reason else "") + "⚠昨收%.2f与基准%.2f偏差%.1f%%" % (prev, r["baseline"], diff * 100)
    top3_out.append({
        "code": r["code"], "name": r["name"], "board": r["board"], "win": r["win"],
        "baseline": r["baseline"], "open": openpx, "dev": dev, "tol": tol,
        "decision": decision,
        "reason": reason,
    })
    print("  %s %s 基准%.4f 开%.4f dev=%s 容差%.2f 过滤[%s] -> %s" % (
        r["code"], r["name"], r["baseline"] or 0, openpx or 0, dev, tol, r["filter_detail"], decision))

signal = {
    "date": TODAY, "baselineDate": baseline_date, "top3": top3_out, "trade": any_buy,
    "note": "大盘多头(上证%s收%.2f>=MA20%.2f)；westock-mcp不可用, 走腾讯公开端点兜底" % (last_date, last_close, ma20) if market_ok else "",
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(signal, f, ensure_ascii=False, indent=2)
print("WROTE", OUT, "trade=", any_buy)
print(json.dumps(signal, ensure_ascii=False, indent=2))
