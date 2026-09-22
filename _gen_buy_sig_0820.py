import json

with open(r"D:\WorkBuddy\选股结果\import_final.json", encoding="utf-8") as f:
    data = json.load(f)

items = data.get("items", [])
items_sorted = sorted(items, key=lambda x: (-(x.get("win") or 0), x.get("code","")))
top3 = items_sorted[:3]

# 今日通过 westock data_quote 抓取的实时开盘价 (2026-08-20)
opens = {"600000": 9.03, "002415": 34.05, "002900": 17.19}

def filter_pass(kl):
    if len(kl) < 20:
        return False, "历史根数<20,MA20不可算"
    closes = [b[2] for b in kl]
    vols = [b[5] for b in kl]
    close, open_, prev_close, vol = closes[-1], kl[-1][1], closes[-2], vols[-1]
    ma5 = sum(closes[-5:]) / 5
    ma20 = sum(closes[-20:]) / 20
    ma20_prev = sum(closes[-21:-1]) / 20
    ma20_vol = sum(vols[-20:]) / 20
    trend_ok = (close > ma20) and (ma5 > ma20) and (ma20 > ma20_prev)
    vol_ok = vol >= 1.2 * ma20_vol
    gap = (open_ - prev_close) / prev_close
    gap_ok = (-0.04 <= gap <= 0.06)
    fp = trend_ok and vol_ok and gap_ok
    reasons = []
    if not trend_ok: reasons.append("趋势")
    if not vol_ok: reasons.append("量能")
    if not gap_ok: reasons.append("缺口")
    return fp, ("全过" if fp else "未过(" + "/".join(reasons) + ")")

top3_out = []
for it in top3:
    code = it["code"]
    board = it.get("board")
    win = it.get("win")
    kl = it["kline"]["day"]
    baseline = kl[-1][2]
    op = opens.get(code)
    tol = 0.03 if board in ("cyb", "kcb", "kc") else 0.02
    dev = (op - baseline) / baseline if op else None
    fp, fpreason = filter_pass(kl)
    decision = "hold"
    reason = None
    if op is None:
        decision = "hold"; reason = "无法取得开盘价"
    elif abs(dev) > tol:
        decision = "hold"; reason = f"开盘偏离 {dev*100:+.2f}% 超{board} ±{tol*100:.0f}% 容差"
    elif not fp:
        decision = "hold"; reason = "5b全市场过滤未过(" + fpreason.replace("未过(", "").rstrip(")") + ")"
    else:
        decision = "buy"
    top3_out.append({
        "code": code, "name": it.get("name"), "board": board, "win": win,
        "baseline": baseline, "open": op, "dev": round(dev, 6) if dev is not None else None,
        "tol": tol, "decision": decision,
    })
    if reason:
        top3_out[-1]["reason"] = reason

trade = any(t["decision"] == "buy" for t in top3_out)
out = {
    "date": "2026-08-20",
    "baselineDate": (data.get("updated") or "")[:10],
    "top3": top3_out,
    "trade": trade,
}
with open(r"D:\WorkBuddy\选股结果\buy_signal.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(json.dumps(out, ensure_ascii=False, indent=2))
print("\n大盘: 多头(上证收3903.72 > MA20≈3888.73) → 进入个股评估")
print("trade =", trade)
