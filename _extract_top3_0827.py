import json, sys

path = r"D:\WorkBuddy\选股结果\import_final.json"
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

# baseline date from updated/date
updated = data.get("updated") or data.get("date") or ""
baselineDate = updated[:10] if updated else ""

items = data.get("items", [])
print("total items:", len(items), "updated:", updated, "baselineDate:", baselineDate, file=sys.stderr)

# Sort by win desc, take top 3 (stable)
ranked = sorted(items, key=lambda x: float(x.get("win", 0) or 0), reverse=True)
top3 = ranked[:3]

out = {"baselineDate": baselineDate, "top3": []}
for it in top3:
    code = it.get("code")
    name = it.get("name")
    board = it.get("board")
    win = it.get("win")
    kl = it.get("kline", {}).get("day", [])
    n = len(kl)
    last = kl[-1] if n else None
    baseline = last[2] if last else None
    out["top3"].append({
        "code": code, "name": name, "board": board, "win": win,
        "bars": n, "baseline": baseline,
        "kline_day": kl  # full array for 5b filter
    })

with open(r"D:\WorkBuddy\_bs_top3_0827.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

print("WROTE _bs_top3_0827.json with top3:", [(t["code"], t["name"], t["board"], t["win"], t["baseline"]) for t in out["top3"]], file=sys.stderr)
