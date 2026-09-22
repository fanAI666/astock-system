import json, os, sys

BASE = r"D:\WorkBuddy\选股结果"
report = []

def log(s):
    report.append(s)
    print(s)

# ---- import_final.json ----
p = os.path.join(BASE, "import_final.json")
log("== import_final.json ==")
with open(p, "r", encoding="utf-8") as f:
    data = json.load(f)
items = data if isinstance(data, list) else data.get("items", [])
log(f"type={type(data).__name__}  total_items={len(items)}")

# board distribution
from collections import Counter
boards = Counter(it.get("board", "?") for it in items)
log(f"board_dist={dict(boards)}")

# category check
cats = Counter(it.get("category", "?") for it in items)
log(f"category_dist={dict(cats)}")

# kline presence
no_day = [it.get("name") for it in items if not it.get("kline") or not it.get("kline", {}).get("day")]
no_min5 = [it.get("name") for it in items if not it.get("kline") or not it.get("kline", {}).get("min5")]
log(f"missing kline.day: {len(no_day)} -> {no_day[:5]}")
log(f"missing kline.min5: {len(no_min5)} -> {no_min5[:5]}")

# date distribution
dates = Counter(it.get("date", "?") for it in items)
log(f"date_dist={dict(dates)}")

# 08-14 signed items: score/win check
signed = [it for it in items if it.get("date") == "2026-08-14"]
log(f"08-14 signed items: {len(signed)}")
missing_score = [it.get("name") for it in signed if it.get("score") is None]
low_score = [it.get("name") for it in signed if (it.get("score") or 0) < 57]
log(f"  08-14 missing score field: {len(missing_score)} -> {missing_score[:10]}")
log(f"  08-14 score<57: {len(low_score)} -> {low_score[:10]}")

# stop/target math spot check on 08-14 signed
bad_math = []
for it in signed:
    entry = it.get("entry"); stop = it.get("stopPrice"); target = it.get("targetPrice")
    board = it.get("board")
    if entry is None or stop is None or target is None:
        continue
    if board in ("cyb", "kcb"):
        stop_ok = abs(stop - entry*0.97) < 0.05
        tgt_ok = abs(target - entry*1.09) < 0.05
    else:
        stop_ok = abs(stop - entry*0.98) < 0.05
        tgt_ok = abs(target - entry*1.06) < 0.05
    if not (stop_ok and tgt_ok):
        bad_math.append(it.get("name"))
log(f"  08-14 stop/target math deviations: {len(bad_math)} -> {bad_math[:10]}")

# required fields
req = {"name","board","ma20","priceMa","ma60","rsi","vol","struct","sector","atr","entry","category","date","stopPrice","targetPrice","kline"}
missing_any = [it.get("name") for it in items if not req.issubset(it.keys())]
log(f"items missing required fields: {len(missing_any)} -> {missing_any[:5]}")

# ---- fundflow.json ----
log("")
log("== fundflow.json ==")
with open(os.path.join(BASE,"fundflow.json"),"r",encoding="utf-8") as f:
    ff = json.load(f)
log(f"keys={sorted(ff.keys())}")
log(f"indices={ff.get('indices')}  styleFactors={ff.get('styleFactors')}  heatSectors={len(ff.get('heatSectors',[]))}  fundFlow={len(ff.get('fundFlow',[]))}  northFlow={ff.get('northFlow')}  updatedAt={ff.get('updatedAt')}")

# ---- briefing_final.json ----
log("")
log("== briefing_final.json ==")
with open(os.path.join(BASE,"briefing_final.json"),"r",encoding="utf-8") as f:
    bf = json.load(f)
log(f"date={bf.get('date')}  warning={bf.get('warning')}  top_keys={sorted(bf.keys())[:12]}")

# ---- 2026-08-14.md ----
log("")
log("== 2026-08-14.md ==")
mdp = os.path.join(BASE,"2026-08-14.md")
log(f"exists={os.path.exists(mdp)}  size={os.path.getsize(mdp) if os.path.exists(mdp) else 0}")

with open(os.path.join(BASE,"_validate_0815_report.txt"),"w",encoding="utf-8") as f:
    f.write("\n".join(report))
