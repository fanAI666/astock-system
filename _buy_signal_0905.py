# -*- coding: utf-8 -*-
"""09:30 买入信号生成 (2026-09-05 Sat, 非交易日降级) — 与回测 passPreFilter 同源。
westock-mcp 在本自动化环境不可用 → 兜底腾讯公开端点：
  指数/个股日K: proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get
  实时开盘价: qt.gtimg.cn (gbk) — 周末无实时开盘 → 按 step4 规则全部 hold
"""
import json, urllib.request, datetime, sys

TODAY = "2026-09-05"          # 今天(周六, 非交易日)
PROJ = "D:/WorkBuddy"
IMPORT = f"{PROJ}/选股结果/import_final.json"
OUT = f"{PROJ}/选股结果/buy_signal.json"

def get(url, timeout=15):
    req = urllib.request.Request(url, headers={"Referer": "https://gu.qq.com/", "User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore"))

def prefix(code):
    return ("sh" if code[0] in "69" else "sz") + code

def kline_last(code, pc=None):
    """返回该票已完成日K数组 (proxy.finance.qq.com)，丢弃当日未完成棒。"""
    if pc is None:
        pc = prefix(code)
    url = f"https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get?param={pc},day,2025-03-01,{TODAY},800,qfq"
    j = get(url)
    q = j["data"][pc]
    day = q.get("qfqday") or q.get("day") or []
    # 周末: 末根即上一交易日完成棒; 若末根 date>=今日 则丢弃(盘中未完成)
    day = [d for d in day if d[0] < TODAY]
    return day

# ---- 1) 读取 import_final.json ----
d = json.load(open(IMPORT, encoding="utf-8"))
items = d.get("items", [])
print(f"[import_final] updated={d.get('updated')} n={len(items)}")

# ---- 2) ⑤ 大盘硬过滤 (上证 vs MA20, 取已完成棒) ----
idx = kline_last("000001", pc="sh000001")  # 上证指数
last20 = idx[-20:]
ma20 = sum(float(x[2]) for x in last20) / 20
latest_close = float(idx[-1][2])
latest_date = idx[-1][0]
bear = latest_close < ma20
print(f"[大盘] 上证 末棒 {latest_date} 收 {latest_close:.2f}  MA20({len(last20)}) {ma20:.2f}  -> {'空头' if bear else '多头'}")

# ---- 3) Top3 by win desc ----
ranked = sorted(items, key=lambda x: float(x.get("win") or 0), reverse=True)[:3]
print("[Top3 by win]")
for it in ranked:
    print("   ", it.get("code"), it.get("name"), it.get("board"), it.get("win"))

# ---- 4/5) 非交易日 → 全部 hold (无实时开盘价) ----
top3 = []
for it in ranked:
    code = it.get("code"); board = it.get("board", "main")
    name = it.get("name"); win = float(it.get("win") or 0)
    # 重拉日K取最新完成棒收盘作基准 (与回测信号日同源)
    try:
        kl = kline_last(code)
        baseline = float(kl[-1][2]) if kl else None
        base_date = kl[-1][0] if kl else None
    except Exception as e:
        baseline = None; base_date = None
        print(f"   [warn] {code} 重拉K线失败: {e}")
    tol = 0.02 if board == "main" else 0.03
    top3.append({
        "code": code, "name": name, "board": board, "win": win,
        "baseline": baseline, "open": None, "dev": None, "tol": tol,
        "decision": "hold",
        "reason": "非交易日(周六)，无 09:30 实时开盘价，无法确认入场"
    })
    print(f"   {code} 基准({base_date})={baseline} 容差={tol} -> hold")

baseline_date = base_date or "2026-09-04"
trade = any(t["decision"] == "buy" for t in top3)

out = {
    "date": TODAY,
    "baselineDate": baseline_date,
    "top3": top3,
    "trade": trade,
    "note": "非交易日(周六)降级：无实时开盘价，Top3 全部 hold；大盘过滤仅作参考。import_final.json 仍停留 2026-09-01(15:40盘后定稿自09-01起未刷新)。"
}
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"[write] {OUT}  trade={trade}  baselineDate={baseline_date}")
print(json.dumps(out, ensure_ascii=False, indent=2))
