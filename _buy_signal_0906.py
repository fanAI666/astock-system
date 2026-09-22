# -*- coding: utf-8 -*-
"""买入信号生成 (2026-09-06, 周日/非交易日降级).
与回测引擎 passPreFilter 同源：⑤ 大盘硬过滤 + 容差 + 全市场过滤(趋势+量能+缺口)。
westock-mcp 在本自动化环境不可用 -> 走腾讯公开端点兜底 (proxy.finance.qq.com 日K / qt.gtimg.cn 实时)。
今天为周日，无 09:30 实时开盘价，Top3 全部 hold，trade=false。
"""
import json, urllib.request, datetime, sys, os

TODAY = "2026-09-06"
FQ = "D:/WorkBuddy/选股结果/import_final.json"
OUT = "D:/WorkBuddy/选股结果/buy_signal.json"
PROXY = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get?param="
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

def pref(code):
    c = code[0]
    return ("sh" if c in "69" else "sz") + code

def get_kline(code, limit=60):
    """返回 [[date,open,close,high,low,vol],...] oldest-first（最新完成棒在 rk[-1]）。
    用显式窗口 2026-08-10~2026-09-04，避免 proxy limit 参数在超大区间下返回旧数据。"""
    url = PROXY + "%s,day,2026-08-10,2026-09-04,%d,qfq" % (pref(code), limit)
    j = json.loads(http_get(url))
    node = j["data"][pref(code)]
    arr = node.get("qfqday") or node.get("day")
    if not arr:
        return None
    out = []
    for row in arr:  # 源为 newest-first
        out.append([row[0], float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])])
    out.reverse()  # -> oldest-first
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

# ---- 2) 上证 大盘硬过滤 (最新完成棒 vs MA20) ----
# 指数 qfq 在窗口化请求下会返回损坏序列，必须用「超大区间+limit=30」形式取近30根。
market_ok = None
try:
    j = json.loads(http_get(PROXY + "sh000001,day,2025-01-01,2030-01-01,30,qfq"))
    node = j["data"]["sh000001"]
    iarr = node.get("qfqday") or node.get("day")
    if iarr and len(iarr) >= 20:
        closes = [float(r[2]) for r in iarr[-20:]]
        ma20 = sum(closes) / 20
        last_close = float(iarr[-1][2])
        last_date = iarr[-1][0]
        market_ok = last_close >= ma20
        print("上证 末棒 %s 收 %.2f MA20 %.2f -> %s" % (last_date, last_close, ma20, "多头" if market_ok else "空头"))
    else:
        print("上证 不足20根")
except Exception as e:
    print("上证 抓取失败:", e)

# ---- 3) 每只：基准=最新完成棒(09-04) + ⑤过滤(信息性) ----
results = []
for it in top3:
    code = it.get("code"); name = it.get("name"); board = it.get("board"); win = float(it.get("win", 0) or 0)
    rk = get_kline(code, limit=40)
    if not rk or len(rk) < 20:
        baseline = None; base_date = None; fdetail = "重拉失败/不足20根"
    else:
        sig = rk[0]                          # 09-04 完成棒 (oldest-first -> index0=最新)
        baseline = sig[2]; base_date = sig[0]
        close = sig[2]; o = sig[1]; prevClose = rk[1][2]; vol = sig[5]
        ma5 = sum(r[2] for r in rk[:5]) / 5
        ma20 = sum(r[2] for r in rk[:20]) / 20
        ma20prev = sum(r[2] for r in rk[1:21]) / 20
        ma20vol = sum(r[5] for r in rk[:20]) / 20
        trendOK = (close > ma20) and (ma5 > ma20) and (ma20 > ma20prev)
        volOK = vol >= 1.2 * ma20vol
        gap = (o - prevClose) / prevClose
        gapOK = (-0.04 <= gap <= 0.06)
        fdetail = "趋势%s 量能%s 缺口%s(%.4f)" % ("OK" if trendOK else "NG", "OK" if volOK else "NG", "OK" if gapOK else "NG", gap)
    results.append({"code": code, "name": name, "board": board, "win": win,
                    "baseline": round(baseline, 4) if baseline is not None else None,
                    "baselineDate": base_date, "filter_detail": fdetail})

baseline_date = results[0]["baselineDate"] if results else None
print("统一 baselineDate =", baseline_date)

# ---- 4) 组装 buy_signal.json (周日全部 hold) ----
top3_out = []
for r in results:
    tol = 0.03 if r["board"] in ("cyb", "kcb", "kc") else 0.02
    top3_out.append({
        "code": r["code"], "name": r["name"], "board": r["board"], "win": r["win"],
        "baseline": r["baseline"], "open": None, "dev": None, "tol": tol,
        "decision": "hold",
        "reason": "非交易日(周日)无实时开盘价，无法确认买入；⑤过滤参考: " + (r["filter_detail"] or "N/A"),
    })

signal = {
    "date": TODAY, "baselineDate": baseline_date, "top3": top3_out, "trade": False,
    "note": "周日非交易日降级：全部 hold，无实盘信号。market=%s" % ("多头" if market_ok else ("空头" if market_ok is False else "未知")),
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(signal, f, ensure_ascii=False, indent=2)
print("WROTE", OUT)
print(json.dumps(signal, ensure_ascii=False, indent=2))
