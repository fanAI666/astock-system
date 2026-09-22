# -*- coding: utf-8 -*-
"""2026-07-24 盘后定稿落盘：读取 _scored_0724.json（8 候选 6 维评分结果） ->
①合并去重追加达标项入 import_final.json（保留既有 26 项，只增不减）
②生成 选股结果/2026-07-24.md（盘后定稿简报，格式对齐 gen_final_0716.py）
大盘（07-24 收盘，源自盘前选股上下文 tdx_quotes 记录）：上证-1.61% / 深证-2.47% / 创业板-2.65% -> Step-8 系统性回调警示触发。
"""
import os, json, datetime

BASE = r"D:/WorkBuddy"
OUT_DIR = os.path.join(BASE, "选股结果")
OUT_JSON = os.path.join(OUT_DIR, "import_final.json")
OUT_MD = os.path.join(OUT_DIR, "2026-07-24.md")
DATA_DATE = "2026-07-24"

# 大盘环境（07-24 收盘，记录值：深证/创业板均跌超2% -> Step-8 触发）
INDICES = [
    ("上证指数", "000001", -1.61),
    ("深证成指", "399001", -2.47),
    ("创业板指", "399006", -2.65),
]

PASS = 57

def setcode_of(code):
    return "1" if code[0] == "6" else "0"

# ---------- 读取评分中间结果 ----------
scored = json.load(open(os.path.join(BASE, "_scored_0724.json"), encoding="utf-8"))
results = scored["results"]
new_codes = scored["new_codes"]

# ---------- ① 合并入 import_final.json（保留存量，去重追加） ----------
pool = json.load(open(OUT_JSON, encoding="utf-8"))
existing_codes = set(it["code"] for it in pool["items"])
merged = list(pool["items"])
added = 0
for r in results:
    if r["total"] < PASS:
        continue
    code = r["code"]
    if code in existing_codes:
        print(f"[SKIP] {code} 已在池中，跳过")
        continue
    m = r["m"]
    item = dict(
        name=f'{r["name"]} {r["code"]}',
        code=code,
        setcode=setcode_of(code),
        board=r["board"],
        ma20=m["ma20"], priceMa=m["priceMa"], ma60=m["ma60"],
        rsi=m["rsi"], vol=m["vol"], struct=m["struct"],
        sector=m["sector"], atr=m["atr"],
        score=r["total"], win=r["win"],
        category="final", date=DATA_DATE,
        stopPrice=r["stop"], targetPrice=r["target"],
        kline=r["kline"],
    )
    merged.append(item)
    existing_codes.add(code)
    added += 1

updated = datetime.datetime.now().astimezone().isoformat()
out = dict(updated=updated, items=merged, watch=pool.get("watch", []))
json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False)
print(f"[OK] import_final.json: 原 {len(pool['items'])} 项 + 新增 {added} 项 = {len(merged)} 项")
print(f"     新达标 {len(new_codes)} 只: {[ (r['name'],r['code']) for r in results if r['total']>=PASS ]}")
print(f"     size~{os.path.getsize(OUT_JSON)//1024}KB")

# ---------- ② 生成 2026-07-24.md ----------
def reason_line(r):
    m = r["m"]
    parts = []
    parts.append("MA20" + ("↑" if m["ma20"] == "up" else "↓"))
    parts.append("MA60" + ("↑" if m["ma60"] == "up" else "↓"))
    parts.append({"breakout": "放量突破", "pullback": "回踩", "neutral": "震荡"}[m["struct"]])
    parts.append({"high": "放量", "normal": "量平", "low": "缩量"}[m["vol"]])
    parts.append({"strong": "板块强", "mid": "板块中", "weak": "板块弱"}[m["sector"]])
    parts.append(f"RSI{m['rsi']}")
    parts.append(f"ATR{m['atr']}%")
    return "·".join(parts)

final_items = [r for r in results if r["total"] >= PASS]
final_items.sort(key=lambda x: -x["win"])

lines = []
lines.append(f"# 盘后定稿 · A股稳健选股策略（{DATA_DATE}）\n")
lines.append(f"> 数据时间戳：2026-07-24 15:00 收盘（通达信 HQDate=20260724）。所有胜率均为技术面估计模型，非投资建议；仅选股并警示，不下单/交易。\n")

lines.append("## 一、大盘环境（Step-8 风控）\n")
lines.append("| 指数 | 代码 | 涨跌幅 |")
lines.append("|------|------|--------|")
for nm, cd, chg in INDICES:
    lines.append(f"| {nm} | {cd} | {chg:+.2f}% |")
triggered = any(chg <= -2.0 for _, _, chg in INDICES)
lines.append("")
if triggered:
    lines.append("⚠️ **Step-8 警示**：深证成指、创业板指单日跌幅均 >2%（三指同步下挫），属普跌/系统性回调环境。建议**收缩或暂停新增开仓**，仅保留既有的高胜率逆市强势标的观察，严格按 3:1 止损纪律执行。\n")
else:
    lines.append("✅ 大盘未触发跌超 2% 暂停警示。\n")

lines.append("## 二、达标清单（总分≥57 → 胜率≥70%，按胜率降序）\n")
lines.append("| 排名 | 名称/代码 | 板块 | 综合分 | 胜率估计 | 止损价 | 目标价 | 一句话理由 |")
lines.append("|------|-----------|------|--------|----------|--------|--------|------------|")
for i, r in enumerate(final_items, 1):
    nm = f'{r["name"]} {r["code"]}'
    lines.append(f'| {i} | {nm} | {r["board"]} | {r["total"]} | {r["win"]:.1f}% | {r["stop"]} | {r["target"]} | {reason_line(r)} |')

lines.append("")
lines.append("## 三、盘中简报\n")
lines.append(f"- **达标数**：{len(final_items)} 只（候选池 {len(results)} 只，阈值 总分≥57）")
if final_items:
    top3 = "、".join(f'{it["name"]}({it["win"]:.1f}%)' for it in final_items[:3])
    lines.append(f"- **前 3**：{top3}")
lines.append("- **风险提示**：")
lines.append("  1. 全批 ATR% 普遍偏高（止损适配维度多计 0~5 分），固定比例止损易被扫损，建议按 ATR 动态止损或减仓。")
rsi_hot = [r for r in final_items if r["m"]["rsi"] > 70]
if rsi_hot:
    names = "、".join(f'{r["name"]}({r["m"]["rsi"]})' for r in rsi_hot)
    lines.append(f"  2. RSI 超买（>70）：{names}，追高风险大，宜等回踩 MA20 买点。")
pct_hot = [r for r in final_items if (r["pct"] or 0) > 6]
if pct_hot:
    names = "、".join(f'{r["name"]}(+{r["pct"]:.1f}%)' for r in pct_hot)
    lines.append(f"  3. 同日涨幅偏大：{names}，短线获利盘丰厚，注意回调。")
# 涨停特别提示
limit_up = [r for r in final_items if (r["pct"] or 0) >= 20.0 - 1e-9]
if limit_up:
    for r in limit_up:
        lines.append(f"  4. 🔒 **涨停特别提示**：{r['name']} {r['code']} 今日 {r['pct']:.1f}%（科创板 20% 涨停），收盘封死于涨停价 {r['entry']}（=区间最高），封板强度强；但已处涨停无法当日买入，信号日收盘作 entry，实际建仓须待次日开盘（受 ±3% 双创准入约束），且 RSI {r['m']['rsi']} 偏高，追板风险大。")
lines.append("  5. 本周交易笔数无法读取系统 localStorage，请自行在「风控看板」核对是否超 5 笔。")
lines.append("  6. 所有标的板块强度均弱（行业涨幅 HYZAF 全为负），属逆市放量突破的题材轮动博弈，非长线价值仓；大盘系统性回调下胜率模型置信度下降。")
lines.append("  7. 深物业A(000011)/世茂能源(605028) MA60 向下，属中期弱势中的短线反弹，按本系统 HTML 实盘 P7 硬规则（MA60≠up 即剔除）将被过滤，盘后定稿按总分≥57 保留但需警惕。")

lines.append("")
lines.append("## 四、完整评分明细（8 候选全量）\n")
lines.append("| 名称/代码 | 板块 | ma20 | 价/MA20 | ma60 | RSI | ATR% | 结构 | 量能 | 板块 | 综合分 | 胜率 |")
lines.append("|-----------|------|------|---------|------|-----|------|------|------|------|--------|------|")
for r in results:
    m = r["m"]
    tag = "✅达标" if r["total"] >= PASS else "—"
    lines.append(f'| {r["name"]} {r["code"]} | {r["board"]} | {m["ma20"]} | {m["priceMa"]} | {m["ma60"]} | {m["rsi"]} | {m["atr"]} | {m["struct"]} | {m["vol"]} | {m["sector"]} | {r["total"]} | {r["win"]:.1f}% {tag} |')

lines.append("")
lines.append("---")
lines.append(f"\n_生成时间：{updated}_  |  引擎：6 维加权（趋势25/结构20/量能15/板块15/RSI15/止损适配10），胜率=min(88, 50+总分×0.35)。候选行情取自 tdx_kline 表头（现价/涨跌幅），行业涨幅 HYZAF 取自盘前选股上下文；量比由 K 线量比推导。")

md = "\n".join(lines)
open(OUT_MD, "w", encoding="utf-8").write(md)
print(f"wrote {OUT_MD}")
