# -*- coding: utf-8 -*-
"""
v1.0.7 重标定 winRate：
把 import_final.json 的展示字段 win 从「主观公式 50+score*0.35」就地回填为
回测真实胜率（来自 backtest_winrate.json 的 calibration.perStock.realized），
使面板"成功概率"与回测标定偏差 48.5pp -> ≈0。

- 旧公式分保留为 score 字段（综合强度分，仍作达标门槛依据，选股规则不变）。
- 严格不碰 kline / 止损 / 止盈 / 入场 等任何规则字段。
- 保留 extend_history.js 已注入的 320 根真实日线，不重跑 build_final.py（避免把历史冲回 70 根）。
"""
import os, json

BASE = r"D:/WorkBuddy"
FINAL = os.path.join(BASE, "选股结果", "import_final.json")
BW = os.path.join(BASE, "选股结果", "backtest_winrate.json")
WF = os.path.join(BASE, "选股结果", "walkforward_calib.json")

final = json.load(open(FINAL, encoding="utf-8"))

# P8 双轨标定：优先 walk-forward perStock 多笔真实胜率，回退旧单笔标定
per = {}
overall = 0.272
if os.path.exists(WF):
    try:
        wf = json.load(open(WF, encoding="utf-8"))
        for p in wf.get("calibration", {}).get("perStock", []):
            per[p["code"]] = p
        overall = wf.get("winRate", overall)
        print("[P8] 采用 walk-forward 标定源（perStock 多笔）")
    except Exception as e:
        print("⚠ walk-forward 载入失败:", e)
if not per and os.path.exists(BW):
    bw = json.load(open(BW, encoding="utf-8"))
    for p in bw.get("calibration", {}).get("perStock", []):
        per[p["code"]] = p
    overall = bw.get("winRate", overall)
    print("[回退] 采用旧 backtest_winrate 标定源")

print("=== v1.0.7 重标定：主观公式分 -> 回测真实胜率 ===")
changed = []
for it in final.get("items", []):
    code = it["code"]
    old = it.get("win")
    # 旧 win（公式分）转为综合强度分保留
    it["score"] = round(old, 1) if isinstance(old, (int, float)) else old
    ps = per.get(code)
    if ps and ps.get("realized") is not None:
        new_win = round(ps["realized"] * 100, 1)
    else:
        new_win = round(overall * 100, 1)
    it["win"] = new_win
    changed.append((code, old, new_win, ps.get("trades") if ps else None, ps.get("wins") if ps else None))

json.dump(final, open(FINAL, "w", encoding="utf-8"), ensure_ascii=False)
print(f"wrote {FINAL}  items={len(final.get('items', []))}")
for c, o, n, t, w in changed:
    print(f"  {c}: 综合强度分(原win) {o}  ->  成功概率(回测标定) {n}%  (回测 {w}/{t})")
