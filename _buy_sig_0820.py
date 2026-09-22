import json

with open(r"D:\WorkBuddy\选股结果\import_final.json", encoding="utf-8") as f:
    data = json.load(f)

updated = data.get("updated", "")
items = data.get("items", [])
print("updated:", updated)
print("total items:", len(items))

def baseline_close(kl):
    return kl[-1][2]

def filter_metrics(kl):
    if len(kl) < 20:
        return None
    closes = [b[2] for b in kl]
    vols = [b[5] for b in kl]
    close = closes[-1]
    open_ = kl[-1][1]
    prev_close = closes[-2]
    vol = vols[-1]
    ma5 = sum(closes[-5:]) / 5
    ma20 = sum(closes[-20:]) / 20
    ma20_prev = sum(closes[-21:-1]) / 20
    ma20_vol = sum(vols[-20:]) / 20
    trend_ok = (close > ma20) and (ma5 > ma20) and (ma20 > ma20_prev)
    vol_ok = vol >= 1.2 * ma20_vol
    gap = (open_ - prev_close) / prev_close
    gap_ok = (-0.04 <= gap <= 0.06)
    return {
        "close": close, "open": open_, "prev_close": prev_close, "vol": vol,
        "ma5": ma5, "ma20": ma20, "ma20_prev": ma20_prev, "ma20_vol": ma20_vol,
        "trend_ok": trend_ok, "vol_ok": vol_ok, "gap": gap, "gap_ok": gap_ok,
        "filter_pass": trend_ok and vol_ok and gap_ok,
        "last_date": kl[-1][0], "n_bars": len(kl),
    }

# sort by win desc, tie-break by code for stability
items_sorted = sorted(items, key=lambda x: (-(x.get("win") or 0), x.get("code","")))
top3 = items_sorted[:3]
print("\n=== TOP3 by win ===")
for it in top3:
    kl = it.get("kline", {}).get("day", [])
    fm = filter_metrics(kl)
    base = baseline_close(kl)
    print(json.dumps({
        "code": it["code"], "name": it["name"], "board": it.get("board"),
        "win": it.get("win"), "baseline": base,
        "last_bar_date": kl[-1][0] if kl else None, "n_bars": len(kl),
        "filter": fm,
    }, ensure_ascii=False))
