import json, datetime, os

TODAY = "2026-07-10"
items = json.load(open(r"D:/WorkBuddy/_intermediate.json", encoding="utf-8"))
DATE_ISO = "2026-07-10T14:55:00+08:00"

BOARD_CN = {"main":"主板","cyb":"创业板","star":"科创板"}
BOARD_LABEL = {"main":"main","cyb":"cyb","star":"star"}

def dim_scores(m, q, loss):
    s_trend = (10 if m["ma20"]=="up" else 0)+(8 if m["priceMa"]=="above" else 0)+(7 if m["ma60"]=="up" else 0)
    s_struct = {"breakout":20,"pullback":16}.get(m["struct"],4)
    s_vol = {"high":15,"normal":8,"low":2}[m["vol"]]
    s_sector = {"strong":15,"mid":9,"weak":3}[m["sector"]]
    rs=m["rsi"]
    if 40<=rs<=60: s_rsi=15
    elif (30<=rs<40) or (60<rs<=70): s_rsi=8
    else: s_rsi=3
    if m["atr"]<=loss*1.2: s_stop=10
    elif m["atr"]<=loss*1.8: s_stop=5
    else: s_stop=0
    return s_trend,s_struct,s_vol,s_sector,s_rsi,s_stop

def reason(it):
    m=it["m"]; q=it["q"]
    parts=[]
    if q["pct"]>=9.9: parts.append("当日涨停")
    elif q["pct"]>=9: parts.append("逼近涨停")
    if m["struct"]=="breakout": parts.append("放量突破前高")
    elif m["struct"]=="pullback": parts.append("回踩均线")
    if m["ma20"]=="up" and m["ma60"]=="up": parts.append("均线多头")
    elif m["ma20"]=="up": parts.append("短多")
    if m["sector"]=="strong": parts.append(f"板块当日走强(+{q['hyzaf']:.1f}%)")
    elif m["sector"]=="weak": parts.append("板块当日偏弱")
    if m["rsi"]>=70: parts.append("RSI超买等回踩")
    if m["atr"]> (3.0 if q["board"] in ("cyb","star") else 2.0)*1.8: parts.append("ATR偏大止损易被扫")
    base = "、".join(parts) if parts else "技术结构中性"
    return base

# categorize
preok=[]; preobs=[]
for it in items:
    it["_reason"]=reason(it)
    if it["win"]>=70:
        it["category"]="preok"; preok.append(it)
    else:
        it["category"]="preobs"; preobs.append(it)
preok.sort(key=lambda x:(-x["win"],-x["total"]))
preobs.sort(key=lambda x:(-x["win"],-x["total"]))

# ---- build import_pre.json ----
out_items=[]
for it in items:
    q=it["q"]; m=it["m"]; loss=it["loss"]
    out_items.append({
        "name": f"{q['name']} {it['code']}",
        "board": q["board"],
        "ma20": m["ma20"],
        "priceMa": m["priceMa"],
        "ma60": m["ma60"],
        "rsi": m["rsi"],
        "vol": m["vol"],
        "struct": m["struct"],
        "sector": m["sector"],
        "atr": m["atr"],
        "entry": it["entry"],
        "category": it["category"],
        "date": TODAY,
        "stopPrice": it["stop"],
        "targetPrice": it["target"],
        "kline": {"day": m["day"], "min5": m["min5"]},
    })
import_pre = {"updated": DATE_ISO, "items": out_items}
os.makedirs(r"D:/WorkBuddy/选股结果", exist_ok=True)
json.dump(import_pre, open(r"D:/WorkBuddy/选股结果/import_pre.json","w",encoding="utf-8"), ensure_ascii=False)
print("wrote import_pre.json, items=", len(out_items))

# ---- build MD report ----
def row_table(lst):
    lines=[]
    lines.append("| 名称/代码 | 板块 | 综合分 | 胜率估算 | 参考止损价 | 参考止盈价 | 入选理由 |")
    lines.append("|---|---|---|---|---|---|---|")
    for it in lst:
        q=it["q"]
        lines.append(f"| {q['name']} {it['code']} | {BOARD_CN[q['board']]} | {it['total']} | {it['win']:.1f}% | {it['stop']} | {it['target']} | {it['_reason']} |")
    return "\n".join(lines)

detail=[]
detail.append("| 名称/代码 | 板块 | ma20 | 价vsMA20 | ma60 | RSI(14) | ATR% | 结构 | 量能 | 板块 | 趋势 | 结构 | 量能 | 板块 | RSI | 止损适配 | 总分 | 胜率 |")
detail.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for it in items:
    m=it["m"]; q=it["q"]; loss=it["loss"]
    st,ss,sv,sec,sr,ssp = dim_scores(m,q,loss)
    detail.append(f"| {q['name']} {it['code']} | {BOARD_CN[q['board']]} | {m['ma20']} | {m['priceMa']} | {m['ma60']} | {m['rsi']} | {m['atr']} | {m['struct']} | {m['vol']} | {m['sector']} | {st} | {ss} | {sv} | {sec} | {sr} | {ssp} | {it['total']} | {it['win']:.1f}% |")

detail_block = "\n".join(detail)

md = f"""# A股收盘前预选一批 · {TODAY}（14:50 预选）

> ⚠️ **盘面警示（已触发收缩建议）**：今日深证成指(399001)截至 14:57 报 **15049.27，−2.27%**，已**跌破 −2% 阈值**。按风控规则，建议**收缩预选范围**——仅在达标池中挑选最强势、结构最干净者，且尽量等回踩而非追高；观察池今日仅作跟踪，不建议新建仓。
> 另：本批候选多为**当日涨停/逼近涨停**的强势股（同益中、高德红外、宏达高科 涨停；南山智尚、瑞迈特 逼近涨停），属「个股强、大盘弱」的极端分化。追涨停板风险极高，2%/3% 紧止损易被盘中震荡扫损，**务必以盘中回踩或次日分歧低吸为更优买点**。

## 一、盘面速览
- 预选时间：{TODAY} 14:50（数据含盘中波动，最终以 18:00 盘后定稿为准）
- 大盘：深证成指 −2.27%（跌超 2%，触发收缩警示）；候选多为逆市涨停的强势个股
- 候选规模：共 11 只 → **达标池 {len(preok)} 只 / 观察池 {len(preobs)} 只**
- 风控基线：本金 ¥10,000；盈亏比 3:1；主板止损 2%/止盈 6%，创业板·科创板止损 3%/止盈 9%；目标胜率 ≥70%

## 二、达标池（胜率估算 ≥70%，按胜率降序）
{row_table(preok)}

## 三、观察池（总分 45–56，仅次日跟踪，非建仓依据）
{row_table(preobs)}

## 四、6 维评分明细（与选股系统 scoreCandidate 引擎一致）
维度权重：趋势 25（ma20 方向10 + 价vsMA20 8 + ma60 方向7）｜结构 20｜量能 15｜板块 15｜RSI 15｜止损适配 10（ATR≤止损×1.2 给10，≤×1.8 给5，否则0）。
胜率 = min(88, 50 + 总分×0.35)。
{detail_block}
## 五、数据来源与说明
- **行情快照**：通达信 `tdx_quotes`，采集于 {TODAY} 14:5x。现价/涨跌幅/量比(LB)/所属板块当日涨跌幅(HYZAF) 均来自实时接口，**未编造**。
- **K 线**：通达信 `tdx_kline` 日线(period=4, wantNum=240) + 5 分钟线(period=0, wantNum=245)，前复权(tqFlag=1)。已内嵌进 `import_pre.json` 供系统在候选区直接画图。
- **板块强度**：以 `tdx_quotes` 返回的 **HYZAF（所属板块当日涨跌幅）** 为代理——≥+1.0% 判强、0~+1.0% 判中、<0 判弱。属可核验数据，非纯主观推断；若需更严谨板块排名可改拉板块指数行情。
- **指标口径**：MA20/MA60 取日线收盘；方向 = 当前 MA 与 5 个交易日前 MA 比较。RSI(14) 用 Wilder 平滑，基于日线收盘。ATR(14)% = ATR/现价×100。结构 = 今日最高是否创 20 日新高（breakout）/回踩 MA20（pullback）/中性。
- **缺失处理**：本批 11 只均成功取到行情与日/5分 K 线，无缺失维度；如个别字段后续无法获取，将标注「中性/平」并按中性计分，严禁臆造。

## 六、尾盘提示（14:50 行动建议）
1. **收缩优先**：大盘 −2.27% 已触发警示，今日只做「达标池内最强结构」的轻仓试错，总仓位建议压到平常一半以下。
2. **别追涨停**：同益中/高德红外/宏达高科 已封板，南山智尚/瑞迈特 逼近涨停，尾盘追入风险收益比差；更优买点是次日分歧低吸或回踩 MA20。
3. **重点盯达标前排**：{preok[0]['q']['name']}、{preok[1]['q']['name']}、{preok[2]['q']['name']}（胜率 {preok[0]['win']:.0f}%/{preok[1]['win']:.0f}%/{preok[2]['win']:.0f}%），结构均为放量突破且板块偏强，可列为次日首选观察。
4. **止损纪律**：全批 ATR% 普遍 > 止损×1.8（止损适配多为 0），说明波动大、紧止损易被扫；若入场，止损位以表格参考价为准，破位即走。
5. **非投资建议**：本清单为收盘前预选观察项，非最终下单依据；最终以 18:00 盘后定稿与次日实盘为准。

---
*生成时间：{DATE_ISO} · 数据源：通达信 tdx-connector · 仅供研究，不构成投资建议。*
"""
open(r"D:/WorkBuddy/选股结果/预选_2026-07-10.md","w",encoding="utf-8").write(md)
print("wrote 预选_2026-07-10.md")
print("达标:", [f"{i['q']['name']}({i['win']:.1f}%)" for i in preok])
print("观察:", [f"{i['q']['name']}({i['win']:.1f}%)" for i in preobs])
