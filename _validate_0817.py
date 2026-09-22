#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 2026-08-14 盘后定稿（intraday 触发交付，不重造）。"""
import json, os, sys

BASE = r"D:\WorkBuddy\选股结果"
imp = os.path.join(BASE, "import_final.json")
ff = os.path.join(BASE, "fundflow.json")
bf = os.path.join(BASE, "briefing_final.json")
md = os.path.join(BASE, "2026-08-14.md")

print("=== 文件存在性 ===")
for p in (imp, ff, bf, md):
    print(f"{'OK ' if os.path.exists(p) else 'MISSING'} {os.path.basename(p):20s} {os.path.getsize(p)/1024/1024:.2f}MB" if os.path.exists(p) else f"MISSING {p}")

# import_final.json
with open(imp, encoding="utf-8") as f:
    data = json.load(f)
items = data.get("items", data) if isinstance(data, dict) else data
print(f"\n=== import_final.json 总行数: {len(items)} ===")

boards = {}
missing_day = 0
missing_min5 = 0
legacy_no_entry = 0
dated_0814 = 0
score_ok = 0
score_missing = 0
for it in items:
    b = it.get("board")
    boards[b] = boards.get(b, 0) + 1
    kl = it.get("kline", {}) or {}
    if not kl.get("day"):
        missing_day += 1
    if not kl.get("min5"):
        missing_min5 += 1
    if not it.get("entry"):
        legacy_no_entry += 1
    if it.get("date") == "2026-08-14":
        dated_0814 += 1
        sc = it.get("score")
        if sc is None:
            score_missing += 1
        elif sc >= 57:
            score_ok += 1
        else:
            score_ok += 0  # 低于57
print(f"board 分布: {boards}")
print(f"缺失 kline.day: {missing_day} / 缺失 kline.min5: {missing_min5}")
print(f"legacy 缺 entry(历史惯例): {legacy_no_entry}")
print(f"date=2026-08-14 签发项: {dated_0814} / 其中 score>=57: {score_ok} / score缺失: {score_missing}")

# fundflow.json
with open(ff, encoding="utf-8") as f:
    ffd = json.load(f)
print("\n=== fundflow.json ===")
print(f"updatedAt: {ffd.get('updatedAt')}")
print(f"indices({len(ffd.get('indices',[]))}) / styleFactors({len(ffd.get('styleFactors',[]))}) / heatSectors({len(ffd.get('heatSectors',[]))}) / fundFlow({len(ffd.get('fundFlow',[]))})")
print(f"northFlow 非空: {bool(ffd.get('northFlow'))}")

# briefing_final.json
with open(bf, encoding="utf-8") as f:
    bfd = json.load(f)
print("\n=== briefing_final.json ===")
print(f"date: {bfd.get('date')} / warning: {bfd.get('warning')}")

print("\n=== 校验结论 ===")
ok = (missing_day == 0 and missing_min5 == 0 and score_missing == 0 and dated_0814 == score_ok)
print("PASS" if ok else "WARN")
