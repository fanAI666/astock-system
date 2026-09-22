# -*- coding: utf-8 -*-
"""2026-07-27 盘后定稿落盘（Step5-6）：读取 _scored_0727.json（10 候选 6 维评分） ->
①合并去重追加达标项入 import_final.json（保留既有 31 项，只增不减）
②生成 选股结果/2026-07-27.md（盘后定稿）
大盘（07-27 收盘，源自 fetch_fundflow.py）：上证+1.15% / 深证+2.72% / 创业板+3.16% -> Step-8 未触发跌超2%暂停。
注意：tdx-connector 于 15:5x 断连，5分K线无法拉取 -> 新项 kline.min5=[]（日K完整）；300441/600369 板块维度按中性占位（HYZAF 缺失）。
"""
import os, json, datetime

BASE = r"D:/WorkBuddy"
OUT_DIR = os.path.join(BASE, "选股结果")
OUT_JSON = os.path.join(OUT_DIR, "import_final.json")
OUT_MD = os.path.join(OUT_DIR, "2026-07-27.md")
DATA_DATE = "2026-07-27"

PASS = 57

def setcode_of(code):
    return "1" if code[0] == "6" else "0"

# ---------- 读取评分 + 大盘 ----------
scored = json.load(open(os.path.join(BASE, "_scored_0727.json"), encoding="utf-8"))
results = scored["results"]
ff = json.load(open(os.path.join(OUT_DIR, "fundflow.json"), encoding="utf-8"))
INDICES = [(x["name"], x.get("code", ""), x["pct"]) for x in ff.get("indices", [])]
STYLE = ff.get("styleFactors", [])

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
print(f"     size~{os.path.getsize(OUT_JSON)//1024}KB")

# ---------- ② 生成 2026-07-27.md ----------
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
lines.append(f"> 数据时间戳：2026-07-27 15:00 收盘（通达信 HQDate=20260727）。所有胜率均为技术面估计模型，非投资建议；仅选股并警示，不下单/交易。\n")
lines.append("> ⚠️ **数据完整性说明**：本次 tdx-connector 于 15:5x 断连，①5 分钟 K 线未能拉取（新项 `kline.min5` 暂为空，日 K 完整 700 根）；②300441(鲍斯股份)/600369(西南证券) 的行情快照(行业涨幅 HYZAF)缺失，其「板块」维度按规范「缺失按中性/平处理」取中性(9 分)占位，真实板块强度待 tdx 恢复后复核。建议 tdx 稳定后重跑本自动化以回填 min5 与板块维度。\n")

lines.append("## 一、大盘环境（Step-8 风控）\n")
lines.append("| 指数 | 涨跌幅 |")
lines.append("|------|--------|")
for nm, cd, chg in INDICES:
    lines.append(f"| {nm} | {chg:+.2f}% |")
triggered = any(chg <= -2.0 for _, _, chg in INDICES)
lines.append("")
if triggered:
    lines.append("⚠️ **Step-8 警示**：存在单日跌幅 >2% 的指数，属普跌/系统性回调环境。建议收缩或暂停新增开仓。\n")
else:
    lines.append("✅ **大盘未触发跌超 2% 暂停警示**：三指全天收涨（普涨反弹格局），可正常按纪律开仓，但仍须严守 3:1 止损。\n")

lines.append("## 二、达标清单（总分≥57 → 胜率≥70%，按胜率降序）\n")
lines.append("| 排名 | 名称/代码 | 板块 | 综合分 | 胜率估计 | 止损价 | 目标价 | 一句话理由 |")
lines.append("|------|-----------|------|--------|----------|--------|--------|------------|")
for i, r in enumerate(final_items, 1):
    nm = f'{r["name"]} {r["code"]}'
    lines.append(f'| {i} | {nm} | {r["board"]} | {r["total"]} | {r["win"]:.1f}% | {r["stop"]} | {r["target"]} | {reason_line(r)} |')

lines.append("")
lines.append("## 三、盘中简报\n")
lines.append(f"- **达标数**：{len(final_items)} 只（候选池 {len(results)} 只，阈值 总分≥57）→ **本批 10 只候选全部达标**（普涨日、行业涨幅普遍为正所致）")
if final_items:
    top3 = "、".join(f'{it["name"]}({it["win"]:.1f}%)' for it in final_items[:3])
    lines.append(f"- **前 3**：{top3}")
lines.append("- **风险提示**：")
rn = 1
lines.append(f"  {rn}. 全批「止损适配」多计 0 分（ATR% 偏高，固定比例止损易被扫损），仅 西南证券/威孚高科 ATR 略低得 10 分、华创云信得 5 分；建议按 ATR 动态止损或减仓。")
rn += 1
rsi_hot = [r for r in final_items if r["m"]["rsi"] > 70]
if rsi_hot:
    names = "、".join(f'{r["name"]}({r["m"]["rsi"]})' for r in rsi_hot)
    lines.append(f"  {rn}. RSI 超买（>70）：{names}，追高风险大，宜等回踩 MA20 买点。")
    rn += 1
pct_hot = [r for r in final_items if (r["pct"] or 0) > 6]
if pct_hot:
    names = "、".join(f'{r["name"]}(+{r["pct"]:.1f}%)' for r in pct_hot)
    lines.append(f"  {rn}. 同日涨幅偏大：{names}，短线获利盘丰厚，注意回调。")
    rn += 1
limit_up = [r for r in final_items if (r["pct"] or 0) >= 9.5]
for r in limit_up:
    is_cyb = r["board"] in ("cyb", "kcb")
    lines.append(f"  {rn}. 🔒 **涨停特别提示**：{r['name']} {r['code']} 今日 {r['pct']:.1f}%（{'双创 20%' if is_cyb else '主板 10%'} 涨停），收盘封死于涨停价 {r['entry']}，封板强度强；但已处涨停无法当日买入，信号日收盘作 entry，实际建仓须待次日开盘，且追板风险大。")
    rn += 1
maweak = [r for r in final_items if r["m"]["ma20"] == "down" or r["m"]["ma60"] == "down"]
if maweak:
    names = "、".join(f'{r["name"]}(ma20={r["m"]["ma20"]},ma60={r["m"]["ma60"]})' for r in maweak)
    lines.append(f"  {rn}. 均线弱势（MA20/MA60 向下）：{names}，属中期弱势中的短线反弹；按本系统 HTML 实盘 P7 硬规则（MA60≠up 即剔除）部分将被过滤，盘后定稿按总分≥57 保留但需警惕回踩。")
    rn += 1
lines.append(f"  {rn}. 300441(鲍斯股份)/600369(西南证券) 板块维度因 tdx 断连缺失 HYZAF，按中性(9 分)占位，其真实板块强度待复核；若实际为强板块则胜率被低估。")
rn += 1
lines.append(f"  {rn}. 本周交易笔数无法读取系统 localStorage，请自行在「风控看板」核对是否超 5 笔。")
rn += 1
lines.append(f"  {rn}. 惠城环保(300779) 今日亦入选「放量突破」候选，但已于 07-24 定稿入池（date=2026-07-24），本次按「去重」规则不重复追加，沿用既有条目。")

lines.append("")
lines.append("## 四、完整评分明细（10 候选全量）\n")
lines.append("| 名称/代码 | 板块 | ma20 | 价/MA20 | ma60 | RSI | ATR% | 结构 | 量能 | 板块 | 综合分 | 胜率 | 数据来源 |")
lines.append("|-----------|------|------|---------|------|-----|------|------|------|------|--------|------|----------|")
for r in results:
    m = r["m"]
    tag = "✅达标" if r["total"] >= PASS else "—"
    lines.append(f'| {r["name"]} {r["code"]} | {r["board"]} | {m["ma20"]} | {m["priceMa"]} | {m["ma60"]} | {m["rsi"]} | {m["atr"]} | {m["struct"]} | {m["vol"]} | {m["sector"]} | {r["total"]} | {r["win"]:.1f}% {tag} | {r["src"]} |')

lines.append("")
lines.append("---")
lines.append(f"\n_生成时间：{updated}_  |  引擎：6 维加权（趋势25/结构20/量能15/板块15/RSI15/止损适配10），胜率=min(88, 50+总分×0.35)。评分基于 tdx_kline 日K(700根,末棒20260727) + 本会话 tdx_quotes(8只)；2只缺失行情按中性处理。5分K线因 tdx 断连未嵌（min5=[]）。")

md = "\n".join(lines)
open(OUT_MD, "w", encoding="utf-8").write(md)
print(f"wrote {OUT_MD}")
