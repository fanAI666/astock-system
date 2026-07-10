# -*- coding: utf-8 -*-
import os, json

DATE = "2026-07-09"

# board: main / cyb / kcb
# dims: trend(25), struct(20), vol(15), sector(15), rsi(15)  -> 止损适配(10) computed from ATR
# atr_abs from tdx_indicator_select; price from screener now_price
# signals: screener tags (data-backed); sector_strength is INFERRED from sector cluster + 概念板块 tags
stocks = [
    # name, code, board, price, chg, trend, struct, vol, sector, rsi_raw, atr_abs, sector_label, signals, reason
    ("恒尚节能","603137","main",25.20,10.00,25,20,15,9,97.927,1.1536,"建筑/节能/BIPV",
        "多头排列·创历史新高·涨停·放量","多头排列+创历史新高涨停，但RSI 97.9 极度超买、ATR过高"),
    ("中兴通讯","000063","main",40.33,9.38,25,16,15,15,72.999,1.9250,"通信/AI/算力",
        "平台整理后MACD金叉·放量·阳线多于阴线","通信/AI主线，平台整理后MACD金叉放量突破"),
    ("中芯国际","688981","kcb",173.00,13.74,25,20,15,15,78.352,11.7986,"半导体/芯片",
        "MACD金叉·创新高·放量·阳线多于阴线","半导体龙头MACD金叉创新高，量价齐升，ATR偏大"),
    ("江淮汽车","600418","main",24.45,9.99,8,16,15,9,40.385,1.7700,"汽车/新能源",
        "创新低后放量涨停·MACD金叉·下跌多于上涨","创新低后放量涨停反转，RSI健康(40)但趋势仍弱、MA未多头"),
    ("上海新阳","300236","cyb",131.32,18.76,25,20,15,15,69.749,10.7529,"半导体/芯片(光刻机)",
        "MACD金叉·创新高·放量","光刻机/先进封装MACD金叉创新高，强势"),
    ("海光信息","688041","kcb",363.46,5.97,25,20,15,15,67.936,25.2050,"半导体/CPU/AI",
        "MACD多头排列·创新高·红二波","CPU龙头多头排列MACD红二波创新高，ATR极大"),
    ("紫光国微","002049","main",87.09,4.29,25,16,15,15,65.343,5.1507,"半导体/芯片/军工",
        "平台整理后MACD金叉·放量·阳线多于阴线","芯片/军工平台整理后金叉，走势稳健"),
    ("富特科技","301607","cyb",57.37,20.00,25,20,15,12,68.037,4.9879,"汽车电子/充电桩",
        "多头排列·创新高·涨停·放量","多头排列涨停创新高，汽车电子/小米题材"),
    ("有研硅","688432","kcb",53.77,20.00,25,20,15,15,78.832,5.5486,"半导体/芯片",
        "多头排列·创新高·涨停·放量·强势股","半导体多头排列涨停创新高，RSI超买(78.8)"),
    ("东岳硅材","300821","cyb",30.33,14.71,25,20,15,9,85.211,2.6793,"有机硅/新材料",
        "多头排列·创新高·放量·强势股","有机硅多头排列创新高，RSI超买(85.2)"),
    ("颀中科技","688352","kcb",23.49,15.71,25,20,15,15,64.415,2.4679,"半导体/先进封装",
        "MACD金叉·创新高·涨停·放量","先进封装MACD金叉涨停创新高，RSI健康"),
    ("兴业股份","603928","main",18.00,10.02,25,20,15,9,76.187,1.4200,"化工/芯片/光刻机",
        "多头排列·创新高·涨停·放量·强势股","化工/光刻机多头排列涨停创新高，RSI超买(76.2)"),
    ("数据港","603881","main",24.42,0.87,18,16,15,15,48.008,1.4714,"数据中心/算力",
        "MACD金叉·放量·昨日涨停·60日内放量","算力数据中心MACD金叉，RSI健康(48)走势偏强未完全多头"),
    ("西部矿业","601168","main",28.99,2.87,10,16,15,9,55.321,1.7421,"有色/黄金/锂",
        "MACD金叉·20日均线压制·放量","有色/黄金MACD金叉，但价受压20日线、趋势偏弱"),
    ("丰林集团","601996","main",2.28,4.59,18,16,15,3,60.062,0.1293,"林业/造纸",
        "MACD金叉·阴线多于阴线·KDJ多头·涨停","林业低价股金叉但阴线偏多、板块弱"),
    ("居然智家","000785","main",2.02,1.51,8,4,15,3,40.631,0.0786,"零售/家居",
        "MACD金叉·创新低·平台整理·KDJ拐头","零售筑底MACD金叉，趋势弱、板块弱、无明确结构"),
    ("德美化工","002054","main",6.93,4.52,8,4,15,9,49.192,0.3350,"化工/合成生物",
        "MACD金叉·平台整理·KDJ底背离·放量","化工平台整理KDJ底背离金叉，超跌反弹无明确结构"),
]

def rsi_score(r):
    if 40 <= r <= 60: return 15
    if (30 <= r < 40) or (60 < r <= 70): return 8
    return 3

rows = []
for (name,code,board,price,chg,trend,struct,vol,sector,rsi_raw,atr_abs,sector_label,signals,reason) in stocks:
    atr_pct = atr_abs/price*100
    loss = 2.0 if board=="main" else 3.0
    profit = loss*3.0
    if atr_pct <= loss*1.2: fit=10
    elif atr_pct <= loss*1.8: fit=5
    else: fit=0
    rs = rsi_score(rsi_raw)
    total = trend+struct+vol+sector+rs+fit
    win = min(88.0, 50+total*0.35)
    stop_px = price*(1-loss/100)
    profit_px = price*(1+profit/100)
    board_label = "主板" if board=="main" else ("创业板" if board=="cyb" else "科创板")
    cls = "达标" if total>=57 else ("观察" if 45<=total<=56 else "未入选")
    rows.append(dict(name=name,code=code,board=board_label,price=price,chg=chg,
        trend=trend,struct=struct,vol=vol,sector=sector,rsi=rs,rsi_raw=rsi_raw,
        fit=fit,atr_pct=atr_pct,total=total,win=round(win,1),
        stop=round(stop_px,2),profit=round(profit_px,2),loss=loss,profit_pct=profit,
        sector_label=sector_label,signals=signals,reason=reason,cls=cls))

pass_pool = sorted([r for r in rows if r["cls"]=="达标"], key=lambda x:-x["total"])
obs_pool  = sorted([r for r in rows if r["cls"]=="观察"], key=lambda x:-x["total"])

def fmt_row(r):
    return (f"| {r['name']} {r['code']} | {r['board']} | {r['total']} | {r['win']}% | "
            f"¥{r['stop']} (-{r['loss']:.0f}%) / ¥{r['profit']} (+{r['profit_pct']:.0f}%) | {r['reason']} |")

lines = []
lines.append(f"# A股尾盘预选结果 · {DATE}（收盘前 14:50 预选）")
lines.append("")
lines.append("> ⚠️ **预选仅为观察清单，非投资建议、不下单不交易。** 14:50 数据含当日盘中波动，最终以 18:00 盘后定稿为准。")
lines.append("> 风控基线（同 stock-selection-system.html）：本金 ¥10,000；盈亏比 3:1；主板止损2%/止盈6%，创业板·科创板放宽至止损3%/止盈9%；目标胜率≥70%。")
lines.append("")
lines.append("## 一、盘面与风控提示")
lines.append("")
lines.append(f"- **大盘**：深证成指 { '+3.07%' }（强势普涨，半导体/AI/算力主线领涨）。当日大盘未跌超2%，**不触发收缩预选警示**。（注：上证指数未单独核验，深成指可作广谱 proxy。）")
lines.append("- **本周交易笔数**：需在选股系统(localStorage)内核对，本自动化无访问权限，**无法自动判断是否已超 5 笔**。请自行确认周交易节奏是否已达上限。")
lines.append("- **⚠️ 全局风险（重要）**：本批 **17 只候选 ATR% 全部 > 止损×1.8**，故「止损适配」维度统一为 0 —— 即按系统 2%/3% 紧止损，当日正常波动即可能扫损。这批多为涨停/创新高后的高波动追涨标的，**建议：等回踩均线(MA20)的更优买点，或放大止损/缩小仓位以匹配波动**；RSI>70 的标的（恒尚97.9、东岳85.2、有研硅78.8、中芯78.4、兴业76.2、中兴73.0）已处超买，追高性价比低。")
lines.append("")
lines.append("## 二、达标池（胜率≥70%，总分≥57，按胜率降序）")
lines.append("")
lines.append("| 名称/代码 | 板块 | 综合分 | 胜率估算 | 参考止损价/止盈价 | 入选理由 |")
lines.append("|---|---|---|---|---|---|")
for r in pass_pool:
    lines.append(fmt_row(r))
lines.append("")
lines.append("## 三、观察池（总分45–56，胜率约66%–70%，仅次日跟踪，不计入达标）")
lines.append("")
if obs_pool:
    lines.append("| 名称/代码 | 板块 | 综合分 | 胜率估算 | 参考止损价/止盈价 | 入选理由 |")
    lines.append("|---|---|---|---|---|---|")
    for r in obs_pool:
        lines.append(fmt_row(r))
else:
    lines.append("_（本批无落入观察区间的标的）_")
lines.append("")
lines.append("## 四、评分明细（6维加权）")
lines.append("")
lines.append("| 名称/代码 | 趋势25 | 结构20 | 量能15 | 板块15 | RSI15 | 止损适配10 | 总分 | 胜率 | ATR% |")
lines.append("|---|---|---|---|---|---|---|---|---|---|")
for r in sorted(rows, key=lambda x:-x["total"]):
    lines.append(f"| {r['name']} {r['code']} | {r['trend']} | {r['struct']} | {r['vol']} | {r['sector']} | {r['rsi']}({r['rsi_raw']}) | {r['fit']} | {r['total']} | {r['win']}% | {r['atr_pct']:.2f}% |")
lines.append("")
lines.append("## 五、说明与数据来源")
lines.append("")
lines.append("- **趋势/结构/量能**：来自通达信 `tdx_screener` 选股标签（多头排列、放量、创新高/突破、平台整理、MACD金叉等），为数据驱动，非臆造。")
lines.append("- **RSI(14)/ATR**：来自 `tdx_indicator_select` 真实指标；ATR% = ATR绝对值 ÷ 当日价 ×100，用于「止损适配」判定（ATR%≤止损×1.2给10，≤×1.8给5，否则0）。")
lines.append("- **板块强度（强15/中9/弱3）**：**为推断值**——依据候选所属概念板块标签及同板块候选在多头排列池中的密度（今日半导体/芯片/AI/算力集群极强），非直接板块指数行情；已在表中标注板块名称供核对。")
lines.append("- **打分引擎**：胜率估算 = 50% + 总分×0.35（上限88%）；总分≥57 即胜率≥70%（达标阈值）。")
lines.append("- **止损/止盈价**：按板块比例 + 当日价计算（主板 -2%/+6%，创/科板 -3%/+9%），仅供参考。")
lines.append("")
lines.append(f"**简报**：达标 {len(pass_pool)} 只，观察 {len(obs_pool)} 只。前3名（并列83分/胜率79.0%）：上海新阳、海光信息、颀中科技。尾盘提示：距收盘约10分钟，达标 {len(pass_pool)} 只可盯量能确认；但全批ATR过高、半数RSI超买，建议优先等回踩MA20的买点而非追高。")

out = "\n".join(lines)
os.makedirs(r"D:\WorkBuddy\选股结果", exist_ok=True)
path = rf"D:\WorkBuddy\选股结果\预选_{DATE}.md"
with open(path,"w",encoding="utf-8") as f:
    f.write(out)

print("PASS:",len(pass_pool),"OBS:",len(obs_pool))
for r in pass_pool[:5]:
    print(f"  {r['name']} {r['code']} total={r['total']} win={r['win']}% stop={r['stop']} profit={r['profit']} atr%={r['atr_pct']:.2f}")
print("---obs---")
for r in obs_pool:
    print(f"  {r['name']} {r['code']} total={r['total']} win={r['win']}% atr%={r['atr_pct']:.2f}")
print("PATH:",path)
