import json, datetime

TODAY = "2026-08-27"
with open(r"D:\WorkBuddy\_bs_top3_0827.json", encoding="utf-8") as f:
    blob = json.load(f)
baselineDate = blob["baselineDate"]
top3 = blob["top3"]

# today opening prices from westock data_quote (time=2026-08-27)
opens = {"600000": 9.18, "600999": 18.50, "002415": 34.78}

out_top3 = []
for t in top3:
    code = t["code"]
    name = t["name"]
    board = t["board"]
    win = t["win"]
    baseline = t["baseline"]
    kl = t["kline_day"]
    n = len(kl)
    # tolerance
    if board == "main":
        tol = 0.02
    else:  # cyb / kcb / kc
        tol = 0.03
    op = opens.get(code)
    # deviation
    dev = (op - baseline) / baseline if (op is not None and baseline) else None

    decision = "hold"
    reason = None

    if op is None:
        decision = "hold"
        reason = "无法确认买入(开盘价缺失)"
    else:
        # 5a tolerance
        if abs(dev) > tol:
            decision = "hold"
            reason = "容差未过(|dev|%.4f>%.2f)" % (abs(dev), tol)
        else:
            # 5b full-market filter (signal day = last bar)
            if n < 20:
                decision = "hold"
                reason = "过滤未过(历史<20根,MA20不可算)"
            else:
                close = kl[-1][2]
                open_s = kl[-1][1]
                prevClose = kl[-2][2]
                vol = kl[-1][5]
                MA5 = sum(x[2] for x in kl[-5:]) / 5.0
                MA20 = sum(x[2] for x in kl[-20:]) / 20.0
                MA20_prev = sum(x[2] for x in kl[-21:-1]) / 20.0
                MA20_vol = sum(x[5] for x in kl[-20:]) / 20.0
                trendOK = (close > MA20) and (MA5 > MA20) and (MA20 > MA20_prev)
                volOK = vol >= 1.2 * MA20_vol
                gap = (open_s - prevClose) / prevClose if prevClose else 0
                gapOK = (-0.04 <= gap <= 0.06)
                filterPass = trendOK and volOK and gapOK
                if filterPass:
                    decision = "buy"
                else:
                    parts = []
                    if not trendOK: parts.append("趋势")
                    if not volOK: parts.append("量能")
                    if not gapOK: parts.append("缺口")
                    decision = "hold"
                    reason = "过滤未过(%s)" % "/".join(parts)
    item = {
        "code": code, "name": name, "board": board, "win": win,
        "baseline": baseline, "open": op, "dev": round(dev, 4) if dev is not None else None,
        "tol": tol, "decision": decision
    }
    if reason:
        item["reason"] = reason
    out_top3.append(item)
    print("%s %s board=%s win=%s base=%s open=%s dev=%s tol=%s -> %s %s" % (
        code, name, board, win, baseline, op, round(dev, 4) if dev is not None else None, tol, decision, reason or ""), file=__import__("sys").stderr)

trade = any(x["decision"] == "buy" for x in out_top3)
result = {
    "date": TODAY,
    "baselineDate": baselineDate,
    "top3": out_top3,
    "trade": trade
}
with open(r"D:\WorkBuddy\选股结果\buy_signal.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print("WROTE 选股结果/buy_signal.json trade=%s" % trade, file=__import__("sys").stderr)
