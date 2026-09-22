# -*- coding: utf-8 -*-
"""修复 每日简报.md 中 2026-08-10 段：
16:30「简报滚动归并」自动化于 23:10 抢先归并了本次选股的**第一版** MD
（40 达标、含次新股 688797 臻宝科技、且尚未 patch 大盘实况）。
本脚本用 23:12 修正后的 选股结果/2026-08-10.md 覆盖该段，保证滚动归档与
import_final.json / briefing_final.json 三者一致。
"""
import os, sys, shutil
sys.stdout.reconfigure(encoding="utf-8")

RES = r"D:/WorkBuddy/选股结果"
ROLL = os.path.join(RES, "每日简报.md")
DATE = "2026-08-10"
DATED = os.path.join(RES, DATE + ".md")

roll = open(ROLL, encoding="utf-8").read()
fresh = open(DATED, encoding="utf-8").read().strip()

start = roll.find(f"## {DATE}")
assert start >= 0, "滚动文件中未找到 08-10 段"
# 下一个日期段起点
nxt = roll.find("\n## 2026-", start + 5)
assert nxt > start, "未找到下一个日期段"

old_seg = roll[start:nxt]
new_seg = f"## {DATE}\n\n{fresh}\n"

shutil.copyfile(ROLL, ROLL + ".bak_0810fix")
roll2 = roll[:start] + new_seg + roll[nxt:]
open(ROLL, "w", encoding="utf-8").write(roll2)

print(f"旧段 {len(old_seg)} 字 → 新段 {len(new_seg)} 字")
print(f"文件 {len(roll)} → {len(roll2)} 字")
print("旧段含『达标数量】40』:", "达标数量**：40" in old_seg)
print("新段含『达标数量】39』:", "达标数量**：39" in new_seg)
print("新段含 大盘实况:", "## 四、大盘实况" in new_seg)
print("新段含 破位警示:", "## 五、存量持仓破位警示" in new_seg)
print("新段残留次新688797:", "688797" in new_seg)

# 复验：段序与唯一性
import re
segs = re.findall(r"^## (\d{4}-\d{2}-\d{2})", roll2, re.M)
print("日期段数:", len(segs), "唯一:", len(segs) == len(set(segs)), "倒序正确:", segs == sorted(segs, reverse=True))
print("首4段:", segs[:4])
