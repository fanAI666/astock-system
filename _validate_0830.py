# -*- coding: utf-8 -*-
import json, os, sys

BASE = r"D:\WorkBuddy\选股结果"
imp = os.path.join(BASE, "import_final.json")
ff  = os.path.join(BASE, "fundflow.json")
bf  = os.path.join(BASE, "briefing_final.json")
md  = os.path.join(BASE, "2026-08-28.md")

print("=== import_final.json ===")
with open(imp, encoding="utf-8") as f:
    data = json.load(f)
items = data.get("items", [])
n = len(items)
print("updated:", data.get("updated"))
print("total items:", n)

boards = {}
miss_day = 0
miss_min5 = 0
miss_entry = 0
for it in items:
    b = it.get("board")
    boards[b] = boards.get(b, 0) + 1
    kl = it.get("kline") or {}
    if not kl.get("day"): miss_day += 1
    if not kl.get("min5"): miss_min5 += 1
    if not it.get("entry"): miss_entry += 1
print("board dist:", boards)
print("missing kline.day:", miss_day)
print("missing kline.min5:", miss_min5)
print("missing entry field:", miss_entry)

# date=2026-08-28 signed items
DATE = "2026-08-28"
signed = [it for it in items if it.get("date") == DATE]
print("signed(date=%s):" % DATE, len(signed))
bad_score = [it for it in signed if (it.get("score") or 0) < 57]
bad_win = [it for it in signed if (it.get("win") or 0) < 70]
print("signed with score<57:", len(bad_score))
print("signed with win<70%:", len(bad_win))

# stop/target math consistency for signed items
def to_f(x):
    try: return float(x)
    except: return None
bad_math = 0
for it in signed:
    e = to_f(it.get("entry")); s = to_f(it.get("stopPrice")); t = to_f(it.get("targetPrice"))
    b = it.get("board")
    if None in (e, s, t): 
        bad_math += 1; continue
    if b == "main": sl, tp = 0.02, 0.06
    else: sl, tp = 0.03, 0.09
    exp_s = e * (1 - sl); exp_t = e * (1 + tp)
    if abs(s - exp_s) > 0.02 or abs(t - exp_t) > 0.02:
        bad_math += 1
print("signed stop/target math deviations:", bad_math)

print()
print("=== fundflow.json ===")
with open(ff, encoding="utf-8") as f:
    ffj = json.load(f)
print("updatedAt:", ffj.get("updatedAt"))
print("indices:", len(ffj.get("indices") or []))
print("styleFactors:", len(ffj.get("styleFactors") or []))
print("heatSectors:", len(ffj.get("heatSectors") or []))
print("fundFlow:", len(ffj.get("fundFlow") or []))

print()
print("=== briefing_final.json ===")
with open(bf, encoding="utf-8") as f:
    bfj = json.load(f)
print("date:", bfj.get("date"))
print("warning:", bfj.get("warning"))
print("keys:", list(bfj.keys()))

print()
print("=== 2026-08-28.md ===")
print("exists:", os.path.exists(md), "size:", os.path.getsize(md) if os.path.exists(md) else 0)

print()
print("VALIDATION PASS" if (miss_day == 0 and miss_min5 == 0
        and len(bad_score) == 0 and len(bad_win) == 0
        and bad_math == 0 and ffj.get("indices") and ffj.get("styleFactors")
        and bfj.get("date") == DATE and os.path.exists(md)) else "VALIDATION ISSUES")
