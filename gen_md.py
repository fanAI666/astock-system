# -*- coding: utf-8 -*-
"""根据 _final_summary.json 生成 选股结果/2026-07-10.md 盘后定稿报告。"""
import os, json, datetime

BASE = r"D:/WorkBuddy"
S = json.load(open(os.path.join(BASE, "_final_summary.json"), encoding="utf-8"))
rows = S["all_rows"]
final_count = S["final_count"]
updated = S["updated"]

BOARD_CN = {"main": "主板", "cyb": "创业板", "kcb": "科创板"}
# 盘后复拉的指数（深证成指/创业板指已确认跌超2%；上证指数该接口 code=000001 返回平安银行，未单独复拉）
INDICES = [
    ("深证成指 399001", "15046.67", "-2.29%"),
    ("创业板指 399006", "3842.73", "-4.37%"),
]
MARKET_TRIGGERED = True  # 深证/创业板均跌超2%

def reason(r):
    m = r["m"]; q = r["q"]; bp = r["bp"]
    parts = []
    if m["struct"] == "breakout":
        parts.append("放量突破前高")
    elif m["struct"] == "pullback":
        parts.append("回踩MA20支撑")
    else:
        parts.append("均线之上震荡")
    if m["ma20"] == "up" and m["ma60"] == "up":
        parts.append("均线多头")
    elif m["ma60"] == "up":
        parts.append("中期多头")
    if m["sector"] == "strong":
        parts.append(f"板块当日走强(+{q['hyzaf']:.1f}%)")
    elif m["sector"] == "weak":
        parts.append("板块偏弱")
    if m["rsi"] > 70:
        parts.append(f"RSI超买({m['rsi']:.0f})等回踩")
    if r["fit"] == 0:
        parts.append("ATR偏大止损易被扫")
    return "、".join(parts)

pass_rows = [r for r in rows if r["pass_"]]
observe_rows = [r for r in rows if not r["pass_"]]

def fmt_pct(x):
    return f"{x:+.2f}%"

L = []
L.append(f"# A股稳健选股 · 盘后定稿（2026-07-10）\n")
L.append("> ⚠️ **大盘跌超 2% 警示（已触发收缩/暂停建议）**：今日深证成指 **−2.29%**、创业板指 **−4.37%**，均跌破 −2% 阈值。按风控规则，建议**收缩候选范围**——仅在达标池中挑选结构最干净者，且以盘中回踩或次日分歧低吸为更优买点，尽量不追高；**今日不建议新建仓，等待大盘企稳**。\n")
L.append(f"> 数据日：2026-07-10（最近收盘交易日；今日为 2026-07-11 周六，无新交易）｜生成时间：{updated}｜数据源：通达信 tdx-connector（盘后复拉 15:00 收盘）。\n")

L.append("## 一、盘面速览")
L.append(f"- 大盘：深证成指 **−2.29%**、创业板指 **−4.37%**（均跌超 2%，触发收缩警示）；候选多为逆市涨停/逼近涨停的强势个股，属「个股强、大盘弱」极端分化。")
L.append(f"- 候选规模：共 {len(rows)} 只 → **达标池 {final_count} 只 / 观察池 {len(observe_rows)} 只**")
L.append(f"- 风控基线：本金 ¥100,000；盈亏比 3:1；主板止损 2%/止盈 6%，创业板·科创板止损 3%/止盈 9%；目标胜率 ≥70%。")
L.append(f"- 本周交易笔数：需用户在系统「风控看板」自行核对（无法读取系统 localStorage）；若已达/超 5 笔，建议暂停新增。\n")

L.append("## 二、达标池（胜率估算 ≥70%，按胜率降序）")
L.append("| 名称/代码 | 板块 | 综合分 | 胜率估算 | 参考止损价 | 参考止盈价 | 入选理由 |")
L.append("|---|---|---|---|---|---|---|")
for r in pass_rows:
    q = r["q"]; m = r["m"]
    L.append(f"| {r['name']} | {BOARD_CN[r['board']]} | {r['total']} | {r['win']:.1f}% | {r['stop']:.2f} | {r['target']:.2f} | {reason(r)} |")

L.append("\n## 三、观察池（总分 <57，仅次日跟踪，非建仓依据）")
L.append("| 名称/代码 | 板块 | 综合分 | 胜率估算 | 参考止损价 | 参考止盈价 | 入选理由 |")
L.append("|---|---|---|---|---|---|---|")
for r in observe_rows:
    q = r["q"]
    L.append(f"| {r['name']} | {BOARD_CN[r['board']]} | {r['total']} | {r['win']:.1f}% | {r['stop']:.2f} | {r['target']:.2f} | {reason(r)} |")

L.append("\n## 四、6 维评分明细（与选股系统 scoreCandidate 引擎一致）")
L.append("维度权重：趋势 25（ma20 方向10 + 价vsMA20 8 + ma60 方向7）｜结构 20｜量能 15｜板块 15｜RSI 15｜止损适配 10（ATR≤止损×1.2 给10，≤×1.8 给5，否则0）。胜率 = min(88, 50 + 总分×0.35)。")
L.append("| 名称/代码 | 板块 | ma20 | 价vsMA20 | ma60 | RSI(14) | ATR% | 结构 | 量能 | 板块 | 趋势 | 结构 | 量能 | 板块 | RSI | 止损适配 | 总分 | 胜率 |")
L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for r in rows:
    m = r["m"]
    trend = (10 if m["ma20"]=="up" else 0) + (8 if m["priceMa"]=="above" else 0) + (7 if m["ma60"]=="up" else 0)
    st = {"breakout":20,"pullback":16}.get(m["struct"],4)
    vo = {"high":15,"normal":8,"low":2}[m["vol"]]
    se = {"strong":15,"mid":9,"weak":3}[m["sector"]]
    rs = 15 if 40<=m["rsi"]<=60 else (8 if (30<=m["rsi"]<40) or (60<m["rsi"]<=70) else 3)
    L.append(f"| {r['name']} | {BOARD_CN[r['board']]} | {m['ma20']} | {m['priceMa']} | {m['ma60']} | {m['rsi']:.1f} | {m['atr']:.2f} | {m['struct']} | {m['vol']} | {m['sector']} | {trend} | {st} | {vo} | {se} | {rs} | {r['fit']} | {r['total']} | {r['win']:.1f}% |")

L.append("\n## 五、数据来源与说明")
L.append("- **行情快照**：通达信 `tdx_quotes`，复拉于盘后（HQDate=20260710），取 15:00 收盘价(入场价)/涨跌幅/量比(LB)/所属板块当日涨跌幅(HYZAF)，均来自实时接口，**未编造**。"
           "（注：上证指数在该接口 code=000001 返回为平安银行，故大盘研判采用深证成指与创业板指。）")
L.append("- **K 线**：通达信 `tdx_kline` 日线(period=4)+5分钟线(period=0)，前复权；本定稿 K线已用 15:00 收盘价修正最后一棒，并经校验结束于 2026-07-10，内嵌进 `import_final.json` 供系统在候选区直接画图（day=70 / min5=245）。")
L.append("- **板块强度**：以 `tdx_quotes` 返回的 **HYZAF（所属板块当日涨跌幅）** 为代理——≥+1.0% 判强、0~+1.0% 判中、<0 判弱，属可核验数据，非纯主观推断。")
L.append("- **指标口径**：MA20/MA60 取日线收盘；方向=当前 MA 与 5 个交易日前 MA 比较。RSI(14) 用 Wilder 平滑，基于日线收盘。ATR(14)% = ATR/现价×100。结构=今日最高是否创 20 日新高(breakout)/回踩 MA20(pullback)/中性。")
L.append("- **板段归一**：688 开头科创板统一记为 `kcb`（与选股系统评分引擎一致；预选文件曾用 `star`，定稿已修正）。")
L.append("- **缺失处理**：本批 11 只均成功取到行情与日/5分 K 线，无缺失维度；如个别字段后续无法获取，将标注「中性/平」并按中性计分，严禁臆造。")

L.append("\n## 六、风险提示")
L.append("1. **大盘极端分化**：深证 −2.29%、创业板 −4.37% 跌超 2%，逆市涨停个股追高易被盘中震荡扫损；2%/3% 紧止损在大盘弱势下更易被触发，**建议等回踩 MA20 或次日分歧低吸，今日不追涨**。")
L.append("2. **全批 ATR% 偏高（止损适配多为 0）**：11 只 ATR% 普遍 > 止损×1.8，说明波动大、紧止损易被扫；若入场，止损位以表格参考价为准，破位即走。")
L.append("3. **RSI 超买**：甘咨询(90.9)/恒尚节能(92.7)/视源股份(85.3) RSI 已深度超买，等回踩买点更优。")
L.append("4. **非投资建议**：本清单为盘后定稿候选，所有评分与胜率均为基于技术面的估算模型，不构成投资建议；只做选股与提示，不下单、不交易。")
L.append("\n---")
L.append("*生成时间：" + updated + " · 数据源：通达信 tdx-connector · 仅供研究，不构成投资建议。*")

md = "\n".join(L)
out_path = os.path.join(BASE, "选股结果", "2026-07-10.md")
open(out_path, "w", encoding="utf-8").write(md)
print("wrote", out_path, len(md), "chars; 达标", final_count, "观察", len(observe_rows))
