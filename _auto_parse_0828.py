import json, sys

PATH = r"D:\WorkBuddy\选股结果\import_final.json"

with open(PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

# top-level keys
print("TOP_KEYS:", list(data.keys()))

updated = data.get("updated") or data.get("date") or data.get("item_date")
print("UPDATED:", updated)

items = data.get("items", [])
print("ITEM_COUNT:", len(items))

# inspect first item keys
if items:
    print("ITEM0_KEYS:", list(items[0].keys()))
    # show kline structure keys
    kl = items[0].get("kline")
    if isinstance(kl, dict):
        print("KLINE_KEYS:", list(kl.keys()))
        day0 = kl.get("day")
        if day0:
            print("DAY0_LEN:", len(day0), "DAY0_LAST:", day0[-1])

# sort by win desc, take top 3
def win_of(it):
    w = it.get("win")
    if w is None:
        return -1
    return float(w)

top = sorted(items, key=win_of, reverse=True)[:3]
print("\n=== TOP3 ===")
for it in top:
    code = it.get("code")
    name = it.get("name")
    board = it.get("board")
    win = it.get("win")
    kl = it.get("kline") or {}
    day = kl.get("day") or []
    baseline = day[-1][2] if day else None
    last_date = day[-1][0] if day else None
    nday = len(day)
    print(f"{code}\t{name}\t{board}\twin={win}\tbaseline={baseline}\tlastDay={last_date}\tnDay={nday}")
