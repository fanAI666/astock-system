import json

PATH = r"D:\WorkBuddy\选股结果\import_final.json"
OUT = r"D:\WorkBuddy\选股结果\buy_signal.json"

TODAY = "2026-08-28"
BASELINE_DATE = "2026-08-27"   # from import_final.updated 2026-08-27

# Top3 候选（按 win 降序） + 今日实际开盘价（data_quote time=2026-08-28 真实开盘）
CAND = [
    {"code": "601939", "open": 10.54},
    {"code": "600000", "open": 9.01},
    {"code": "002415", "open": 35.20},
]

with open(PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

items = {it["code"]: it for it in data["items"]}

top3 = []
for c in CAND:
    code = c["code"]
    it = items.get(code)
    if not it:
        top3.append({"code": code, "name": code, "board": "main", "win": 0,
                     "baseline": None, "open": c["open"], "dev": None, "tol": 0.02,
                     "decision": "hold", "reason": "候选池缺失"})
        continue
    name = it["name"]
    board = it.get("board", "main")
    win = it.get("win")
    day = (it.get("kline") or {}).get("day") or []

    baseline = day[-1][2] if day else None
    today_open = c["open"]

    # 5a 容差
    tol = 0.02 if board == "main" else 0.03
    dev = (today_open - baseline) / baseline if baseline else None
    tol_pass = (dev is not None) and (abs(dev) <= tol)

    # 5b 全市场过滤（信号日 = kline.day 最后一根）
    reason_parts = []
    filter_pass = False
    if len(day) < 20:
        reason_parts.append("趋势/量能过滤未过(历史不足20根)")
    else:
        last = day[-1]
        close = last[2]; open_ = last[1]; vol = last[5]
        prevClose = day[-2][2]
        ma5 = sum(d[2] for d in day[-5:]) / 5
        ma20 = sum(d[2] for d in day[-20:]) / 20
        ma20_prev = sum(d[2] for d in day[-21:-1]) / 20
        ma20_vol = sum(d[5] for d in day[-20:]) / 20
        trend_ok = (close > ma20) and (ma5 > ma20) and (ma20 > ma20_prev)
        vol_ok = vol >= 1.2 * ma20_vol
        gap = (open_ - prevClose) / prevClose
        gap_ok = (-0.04 <= gap <= 0.06)
        filter_pass = trend_ok and vol_ok and gap_ok
        if not trend_ok: reason_parts.append("趋势未过")
        if not vol_ok: reason_parts.append("量能未过")
        if not gap_ok: reason_parts.append("缺口未过")

    # 判定
    if not tol_pass:
        decision = "hold"
        reason = "超容差"
    elif not filter_pass:
        decision = "hold"
        reason = "过滤未过(" + ",".join(reason_parts) + ")"
    else:
        decision = "buy"
        reason = ""

    entry = {
        "code": code,
        "name": name,
        "board": board,
        "win": win,
        "baseline": round(baseline, 4) if baseline is not None else None,
        "open": today_open,
        "dev": round(dev, 6) if dev is not None else None,
        "tol": tol,
        "decision": decision,
    }
    if reason:
        entry["reason"] = reason
    top3.append(entry)
    print(f"{code} {name}: board={board} win={win} baseline={baseline} open={today_open} dev={dev} tol={tol} "
          f"tol_pass={tol_pass} filter_pass={filter_pass} -> {decision} {reason}")

trade = any(t["decision"] == "buy" for t in top3)
out = {
    "date": TODAY,
    "baselineDate": BASELINE_DATE,
    "top3": top3,
    "trade": trade,
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("\nTRADE:", trade)
print("WROTE:", OUT)
