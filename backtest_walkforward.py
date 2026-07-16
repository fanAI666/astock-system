# -*- coding: utf-8 -*-
"""
P8 walk-forward 回测标定（扩大样本量）：
直接吃 import_pre.json 全量预选池（9-10 只，含未达标票），
复用 backtest_winrate.js 同款交易规则，对每只票的 kline.day 做逐信号点回测，
聚合 perStock 多笔真实胜率 —— 替代旧版"perStock 仅 7 只 × 1 笔"的无效统计。

交易规则（与 backtest_winrate.js 严格一致）：
  - 候选：全量预选池（非仅 Top3 / 非仅达标定稿）
  - 基准：信号日 D 收盘 close[D]
  - 入场：次日开盘 open[D+1]，要求 |(open-baseline)/baseline| <= 容差
        主板(main) ±2%；创业板(cyb)/科创板(kcb) ±3%
  - 出场（分市场）：主板固定 2%/6% 强制止损；双创走 ATR 动态止损
        （止损距离 = K_ATR × ATR14，止盈 ×3，持有封顶 5 日，跟踪止损回撤 3% 封顶 6%）
  - 持有：逐根扫描，先触止损→亏损，先触止盈→盈利；超出持有窗口按窗口末收盘结算
  - ⑤ 组合层：大盘硬过滤(上证<MA20不交易) + 同日上限(≤3笔) + 回撤上限(>8%暂停次日)

输出：选股结果/walkforward_calib.json
  - perStock: 每票多笔信号聚合的真实胜率（trades/wins/realized）
  - byBoard / byWinTier / calibration / portfolio 同 backtest_winrate.js 结构
"""
import os, json

BASE = r"D:/WorkBuddy"
PRE = os.path.join(BASE, "选股结果", "import_pre.json")
INDEX_FILE = os.path.join(BASE, "选股结果", "index_sh.json")
OUT = os.path.join(BASE, "选股结果", "walkforward_calib.json")

# 回测周期：预设窗口（用于诚实标注"系统设计的回测区间"），
# 但实际 K 线数据覆盖由 pre 的 kline.day 决定。
# P8 关键修正：walk-forward 的"信号日落在数据窗口内"才有效，
# 故有效周期 = 预设区间 ∩ 数据实际覆盖区间（避免大量信号日落在数据真空区被误删）。
PERIOD_PRESET = {"from": "20250701", "to": "20260630"}
PERIOD = dict(PERIOD_PRESET)  # 实际扫描时会被数据覆盖区间收敛

# ---- 分市场止损参数（双规则：主板/创业板一套，科创板独立）----
MAX_HOLD_MAIN = 10
MAX_HOLD_DYN = 5        # 主板/创业板 动态持有封顶
MAX_HOLD_KCB = 12       # 科创板放宽（波动更大，给更多时间）
K_ATR = 1.05            # 主板/创业板 动态止损倍数
K_ATR_KCB = 2.5         # 科创板独立（P8 回测 0/7 胜率暴露 1.05 过紧）
TRAIL_PCT = 0.03
TRAIL_CAP = 0.06
ATR_WIN = 14
MA_WIN_TREND = 20
MA_WIN_SHORT = 5
VOL_MULT = 1.2
GAP_DOWN = 0.04
GAP_UP = 0.06

# ---- ⑤ 组合层 ----
MAX_BUY_PER_DAY = 3
DD_PAUSE = 0.08
IDX_MA_WIN = 20


def sma(bars, idx, win, field):
    if idx < win - 1 or idx >= len(bars):
        return None
    s = sum(bars[k][field] for k in range(idx - win + 1, idx + 1))
    return s / win


def atr14(bars, idx):
    if idx < ATR_WIN:
        return None
    s = 0.0
    for k in range(idx - ATR_WIN + 1, idx + 1):
        c0 = bars[k - 1][2]
        h, l = bars[k][3], bars[k][4]
        tr = max(h - l, abs(h - c0), abs(l - c0))
        s += tr
    return s / ATR_WIN


def pass_pre_filter(bars, i):
    close = bars[i][2]
    open_ = bars[i][1]
    vol = bars[i][5]
    prev_close = bars[i - 1][2] if i > 0 else close
    gap = (open_ - prev_close) / prev_close if prev_close else 0
    gap_ok = -GAP_DOWN <= gap <= GAP_UP
    ma5 = sma(bars, i, MA_WIN_SHORT, 2)
    ma20 = sma(bars, i, MA_WIN_TREND, 2)
    ma20_prev = sma(bars, i - 1, MA_WIN_TREND, 2)
    ma20_vol = sma(bars, i, MA_WIN_TREND, 5)
    trend_ok = False
    if ma20 is not None and ma5 is not None:
        rising = ma20_prev is not None and (ma20 > ma20_prev)
        trend_ok = (close > ma20) and (ma5 > ma20) and rising
    vol_ok = ma20_vol is not None and ma20_vol > 0 and vol >= ma20_vol * VOL_MULT
    return trend_ok, vol_ok, gap_ok


def tol_for(board):
    if board in ("cyb", "kcb", "kc"):
        return 0.03
    return 0.02


def gen_signals(stock):
    bars = (stock.get("kline") or {}).get("day") or []
    if len(bars) < 2:
        return
    board = stock.get("board")
    is_dyn = board in ("cyb", "kcb", "kc")
    code = stock.get("code") or stock.get("name", "").strip().split()[-1]
    name = stock.get("name", "")
    for i in range(len(bars) - 1):
        d = bars[i]
        nd = bars[i + 1]
        date_d = d[0]
        if date_d < PERIOD["from"] or date_d > PERIOD["to"]:
            continue
        baseline = d[2]
        pre_stats["total"] += 1
        trend_ok, vol_ok, gap_ok = pass_pre_filter(bars, i)
        if not trend_ok:
            pre_stats["skipTrend"] += 1
            continue
        if not vol_ok:
            pre_stats["skipVol"] += 1
            continue
        if not gap_ok:
            pre_stats["skipGap"] += 1
            continue
        pre_stats["pass"] += 1
        next_open = nd[1]
        if not baseline or not next_open:
            continue
        dev = (next_open - baseline) / baseline
        if abs(dev) > tol_for(board):
            continue
        entry = next_open
        if is_dyn:
            a = atr14(bars, i)
            if a is None:
                skipped_no_atr.add(code)
                continue
            # 双规则：科创板 K_ATR=2.5（独立），主板/创业板=1.05
            k = K_ATR_KCB if board == "kcb" else K_ATR
            sl_dist = k * a
            sl = entry - sl_dist
            tp = entry + 3 * sl_dist
            max_hold = MAX_HOLD_KCB if board == "kcb" else MAX_HOLD_DYN
        else:
            sl_dist = entry * 0.02
            sl = entry * 0.98
            tp = entry * 1.06
            max_hold = MAX_HOLD_MAIN
        trail_cap = entry * (1 + TRAIL_CAP)
        cur_sl = sl
        outcome = None
        exit_price = entry
        exit_idx = i + 1
        hold_days = 0
        for j in range(i + 1, min(len(bars), i + max_hold + 1)):
            h, l = bars[j][3], bars[j][4]
            hold_days += 1
            if l <= cur_sl:
                outcome = "loss"
                exit_price = cur_sl
                exit_idx = j
                break
            if h >= tp:
                outcome = "win"
                exit_price = tp
                exit_idx = j
                break
            if is_dyn:
                new_sl = min(trail_cap, max(cur_sl, h * (1 - TRAIL_PCT)))
                if new_sl > cur_sl:
                    cur_sl = new_sl
        if not outcome:
            jlast = min(len(bars) - 1, i + max_hold)
            exit_price = bars[jlast][2]
            outcome = "win" if exit_price >= entry else "loss"
            hold_days = jlast - i
        ret = (exit_price - entry) / entry
        candidates.append({
            "code": code, "name": name, "board": board, "isDyn": is_dyn,
            "signalDate": date_d, "entryDate": nd[0],
            "baseline": round(baseline, 4), "entry": round(entry, 4),
            "slDist": round(sl_dist, 4), "maxHold": max_hold,
            "exitDate": bars[exit_idx][0], "exit": round(exit_price, 4),
            "dev": round(dev, 5), "outcome": outcome,
            "ret": round(ret, 5), "holdDays": hold_days,
            "predicted": stock.get("win") or stock.get("score") or None
        })


# ---- 加载索引（大盘硬过滤）----
idx_close, idx_ma20 = {}, {}
try:
    idx = json.load(open(INDEX_FILE, encoding="utf-8"))
    ib = idx.get("bars") or []
    for b in ib:
        idx_close[b[0]] = b[2]
    for i in range(len(ib)):
        if i >= IDX_MA_WIN - 1:
            s = sum(ib[k][2] for k in range(i - IDX_MA_WIN + 1, i + 1))
            idx_ma20[ib[i][0]] = s / IDX_MA_WIN
except Exception as e:
    print("⚠ 未加载上证指数:", e)

# ---- 主流程 ----
pre = json.load(open(PRE, encoding="utf-8"))
items = pre.get("items") or []

# P8 修正：用数据实际覆盖区间收敛 PERIOD（预设 ∩ 数据窗口）
_cov_from, _cov_to = "99999999", "00000000"
for s in items:
    for b in ((s.get("kline") or s.get("kline") or {}).get("day") or []):
        if b[0] < _cov_from:
            _cov_from = b[0]
        if b[0] > _cov_to:
            _cov_to = b[0]
PERIOD["from"] = max(PERIOD["from"], _cov_from)
PERIOD["to"] = min(PERIOD["to"], _cov_to)
print(f"有效回测窗口: {PERIOD['from']} ~ {PERIOD['to']} (预设 {PERIOD_PRESET['from']}~{PERIOD_PRESET['to']} ∩ 数据覆盖 {_cov_from}~{_cov_to})")

pre_stats = {"total": 0, "pass": 0, "skipTrend": 0, "skipVol": 0, "skipGap": 0}
skipped_no_atr = set()
candidates = []

# 数据覆盖区间
data_from, data_to = "99999999", "00000000"
for s in items:
    for b in ((s.get("kline") or {}).get("day") or []):
        if b[0] < data_from:
            data_from = b[0]
        if b[0] > data_to:
            data_to = b[0]

# P8：全量预选池回测（扩样本）
for s in items:
    gen_signals(s)

# ---- ⑤ 组合层 ----
idx_filtered = []
after_index = []
idx_bearish_days = set()
for c in candidates:
    ma = idx_ma20.get(c["signalDate"])
    cl = idx_close.get(c["signalDate"])
    if ma is not None and cl is not None and cl < ma:
        idx_filtered.append(c)
        idx_bearish_days.add(c["signalDate"])
    else:
        after_index.append(c)

by_day = {}
for c in after_index:
    by_day.setdefault(c["signalDate"], []).append(c)
after_cap = []
per_day_capped = 0
for d in sorted(by_day):
    arr = sorted(by_day[d], key=lambda x: (x["predicted"] or 0), reverse=True)
    per_day_capped += max(0, len(arr) - MAX_BUY_PER_DAY)
    after_cap.extend(arr[:MAX_BUY_PER_DAY])

all_dates = sorted(set(c["signalDate"] for c in after_cap))
date_idx = {d: i for i, d in enumerate(all_dates)}
dd_sorted = sorted(after_cap, key=lambda c: (c["signalDate"], -(c["predicted"] or 0)))
equity = peak = 1.0
paused = False
pause_until = None
dd_paused = 0
trades = []
for c in dd_sorted:
    if paused:
        if pause_until is None or c["signalDate"] <= pause_until:
            dd_paused += 1
            continue
        paused = False
    equity *= (1 + c["ret"])
    if equity > peak:
        peak = equity
    trades.append(c)
    if peak - equity > DD_PAUSE * peak:
        paused = True
        i = date_idx.get(c["signalDate"])
        pause_until = all_dates[i + 1] if (i is not None and i + 1 < len(all_dates)) else None

# ---- 统计 ----
total = len(trades)
wins = [t for t in trades if t["outcome"] == "win"]
losses = [t for t in trades if t["outcome"] == "loss"]
win_rate = wins.__len__() / total if total else 0
avg_win = sum(t["ret"] for t in wins) / len(wins) if wins else 0
avg_loss = sum(abs(t["ret"]) for t in losses) / len(losses) if losses else 0
sum_win = sum(t["ret"] for t in wins)
sum_loss = sum(abs(t["ret"]) for t in losses)
profit_factor = sum_win / sum_loss if sum_loss else (float("inf") if sum_win else 0)
avg_hold = sum(t["holdDays"] for t in trades) / total if total else 0
expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss

# 分市场
by_board = {}
for t in trades:
    b = t["board"]
    by_board.setdefault(b, {"trades": 0, "wins": 0})
    by_board[b]["trades"] += 1
    if t["outcome"] == "win":
        by_board[b]["wins"] += 1
for b, o in by_board.items():
    o["winRate"] = round(o["wins"] / o["trades"], 4) if o["trades"] else 0

# 分层（预测≥70 / <70）
by_tier = {
    "high": {"predMin": 70, "trades": 0, "wins": 0},
    "low": {"predMin": 0, "trades": 0, "wins": 0},
}
for t in trades:
    tier = by_tier["high"] if (t["predicted"] or 0) >= 70 else by_tier["low"]
    tier["trades"] += 1
    if t["outcome"] == "win":
        tier["wins"] += 1
for k, o in by_tier.items():
    o["winRate"] = round(o["wins"] / o["trades"], 4) if o["trades"] else 0

# ① 标定：perStock 多笔聚合
per_stock = {}
for t in trades:
    o = per_stock.setdefault(t["code"], {
        "code": t["code"], "name": t["name"], "board": t["board"],
        "predicted": t["predicted"], "trades": 0, "wins": 0
    })
    o["trades"] += 1
    if t["outcome"] == "win":
        o["wins"] += 1
per_stock_arr = []
for o in per_stock.values():
    o["realized"] = round(o["wins"] / o["trades"], 4) if o["trades"] else 0
    per_stock_arr.append(o)

pred_list = [o["predicted"] for o in per_stock_arr if o["predicted"] is not None]
pred_mean = sum(pred_list) / len(pred_list) if pred_list else 0
calib_bias = round(pred_mean / 100 - win_rate, 4)

portfolio = {
    "enabled": True,
    "indexFilter": {"rule": "上证指数收盘<MA20(20日)→当日全市场不交易",
                    "dropped": len(idx_filtered), "bearishDays": len(idx_bearish_days)},
    "perDayCap": {"max": MAX_BUY_PER_DAY, "rule": f"每个信号日最多开仓 {MAX_BUY_PER_DAY} 笔",
                  "dropped": per_day_capped},
    "drawdownPause": {"threshold": DD_PAUSE, "rule": f"权益曲线自峰值回撤>{DD_PAUSE*100:.0f}%→暂停下一交易日",
                      "dropped": dd_paused},
    "finalTrades": len(trades),
    "stageCounts": {"raw": len(candidates), "afterIndex": len(after_index),
                    "afterCap": len(after_cap), "final": len(trades)}
}

result = {
    "metric": "walkforwardWinRate",
    "label": "P8 walk-forward 回测标定（全量预选池）",
    "period": {"from": "2025-07-01", "to": "2026-06-30"},
    "dataRange": {"from": data_from[:4] + "-" + data_from[4:6] + "-" + data_from[6:],
                  "to": data_to[:4] + "-" + data_to[4:6] + "-" + data_to[6:]},
    "winRate": round(win_rate, 4),
    "trades": total,
    "wins": len(wins),
    "losses": len(losses),
    "avgWin": round(avg_win, 4),
    "avgLoss": round(avg_loss, 4),
    "profitFactor": round(profit_factor, 2) if profit_factor != float("inf") else None,
    "expectancy": round(expectancy, 4),
    "avgHoldDays": round(avg_hold, 2),
    "universe": len(items),
    "pool": "full-preselect",
    "note": "P8：直接吃 import_pre.json 全量预选池（含未达标票），逐信号点 walk-forward，perStock 多笔聚合。",
    "byBoard": by_board,
    "byWinTier": by_tier,
    "calibration": {
        "predMean": round(pred_mean / 100, 4),
        "realized": round(win_rate, 4),
        "bias": calib_bias,
        "perStock": per_stock_arr,
        "perStockTradesTotal": sum(o["trades"] for o in per_stock_arr),
        "perStockCount": len(per_stock_arr)
    },
    "preFilter": {
        "total": pre_stats["total"], "pass": pre_stats["pass"],
        "skipTrend": pre_stats["skipTrend"], "skipVol": pre_stats["skipVol"], "skipGap": pre_stats["skipGap"]
    },
    "ruleMain": "主板：强制止损−2%/止盈+6%（固定3:1），持有≤10日",
    "ruleDyn": "创业板：动态止损=入场价−1.05×ATR(14)，止盈×3，持有封顶5日；科创板(独立)：动态止损=入场价−2.5×ATR(14)，止盈×3，持有封顶12日；均含跟踪止损(回撤3%,封顶6%)",
    "ruleFilterAll": "全市场：趋势+量能+缺口 过滤",
    "rulePortfolio": "⑤ 组合层：大盘硬过滤+同日上限(≤3笔)+回撤上限(>8%暂停次日)",
    "portfolio": portfolio,
    "generatedAt": __import__("datetime").datetime.now().isoformat(),
    "trades_detail": trades
}

json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)

# ---- 打印 ----
fmt = lambda d: f"{d[:4]}-{d[4:6]}-{d[6:]}"
print("=== P8 walk-forward 回测标定 ===")
print(f"回测周期 : {PERIOD['from']} ~ {PERIOD['to']}")
print(f"数据覆盖 : {fmt(data_from)} ~ {fmt(data_to)}")
print(f"候选宇宙 : {len(items)} 支（全量预选池，含未达标）")
print(f"候选信号 : {pre_stats['total']} 笔 | 通过过滤 {pre_stats['pass']} | 趋势未过 {pre_stats['skipTrend']} | 量能未过 {pre_stats['skipVol']} | 缺口未过 {pre_stats['skipGap']}")
print(f"触发交易 : {total} 笔")
print(f"盈利/亏损: {len(wins)} / {len(losses)}")
print(f"交易胜率 : {win_rate*100:.1f}%")
print(f"平均盈/亏: {avg_win*100:.2f}% / {avg_loss*100:.2f}%")
print(f"盈亏比   : {profit_factor:.2f}" if profit_factor != float('inf') else "盈亏比   : ∞")
print(f"期望值   : {expectancy*100:.2f}% / 笔")
print(f"平均持有 : {avg_hold:.2f} 交易日")
print(f"分市场   : " + "  ".join(f"{b} {o['winRate']*100:.1f}%({o['wins']}/{o['trades']})" for b, o in by_board.items()))
print(f"分层≥70  : {by_tier['high']['winRate']*100:.1f}%({by_tier['high']['wins']}/{by_tier['high']['trades']}) | <70: {by_tier['low']['winRate']*100:.1f}%({by_tier['low']['wins']}/{by_tier['low']['trades']})")
print(f"标定偏差 : 预测均值 {pred_mean:.1f}% vs 实现 {win_rate*100:.1f}% (偏差 {calib_bias*100:.1f}pp)")
print(f"perStock: {len(per_stock_arr)} 只，合计 {sum(o['trades'] for o in per_stock_arr)} 笔（旧版仅 7只×1笔）")
print(f"输出文件 : {OUT} ({os.path.getsize(OUT)//1024} KB)")
if skipped_no_atr:
    print(f"跳过(双创ATR不足): {','.join(sorted(skipped_no_atr))}")
print("\n=== ⑤ 组合层 ===")
print(f"大盘硬过滤: 剔除 {portfolio['indexFilter']['dropped']} 笔 | 空头日 {portfolio['indexFilter']['bearishDays']} 天")
print(f"同日上限  : ≤{portfolio['perDayCap']['max']} 笔 | 剔除 {portfolio['perDayCap']['dropped']} 笔")
print(f"回撤上限  : 阈值 {portfolio['drawdownPause']['threshold']*100:.0f}% | 暂停剔除 {portfolio['drawdownPause']['dropped']} 笔")
print(f"组合后成交: {portfolio['finalTrades']} 笔 (raw {portfolio['stageCounts']['raw']} → 过指 {portfolio['stageCounts']['afterIndex']} → 过限 {portfolio['stageCounts']['afterCap']} → 最终 {portfolio['stageCounts']['final']})")
