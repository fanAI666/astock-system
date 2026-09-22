# -*- coding: utf-8 -*-
"""
盘后定稿生成器（2026-07-16）：读取逐只转录的 K 线紧凑文件 _kl_<code>.json，
按 parse_and_score.py 引擎（任务 Step-3 口径）计算 6 维评分与综合胜率，
筛选达标（总分>=57 -> 胜率>=70%），内嵌 day(70)/min5(48) K 线，输出定稿 MD + import_final.json。
数据时间戳：2026-07-16 15:30 收盘（HQDate=20260716）。
"""
import os, json, datetime

BASE = r"D:/WorkBuddy"
OUT_DIR = os.path.join(BASE, "选股结果")
OUT_MD = os.path.join(OUT_DIR, "2026-07-16.md")
OUT_JSON = os.path.join(OUT_DIR, "import_final.json")
DATA_DATE = "2026-07-16"

# 权威盘后行情快照（tdx_quotes, HQDate=20260716, 15:30 收盘）
QUOTES = {
    "301520": dict(name="万邦医药", board="cyb",  now=66.65, pct=13.37, lb=1.16, hyzaf=-1.22),
    "603127": dict(name="昭衍新药", board="main", now=53.25, pct=5.20,  lb=2.35, hyzaf=-1.22),
    "688621": dict(name="阳光诺和", board="kcb",  now=60.07, pct=3.57,  lb=2.17, hyzaf=-1.22),
    "000999": dict(name="华润三九", board="main", now=25.84, pct=2.54,  lb=1.738, hyzaf=2.248),
    "300149": dict(name="睿智医药", board="cyb",  now=11.09, pct=6.74,  lb=3.51, hyzaf=-1.22),
    "002127": dict(name="南极电商", board="main", now=3.23,  pct=9.86,  lb=2.98, hyzaf=-0.71),
    "600664": dict(name="哈药股份", board="main", now=4.94,  pct=10.02, lb=1.66, hyzaf=0.40),
}

# 大盘环境（tdx_quotes, 2026-07-16 收盘）
INDICES = [
    ("上证指数", "000001", -1.85),
    ("深证成指", "399001", -1.97),
    ("创业板指", "399006", -2.95),
]

def setcode_of(code):
    return "1" if code[0] == "6" else "0"

# ---------- 指标计算（与 parse_and_score.py 严格一致） ----------
def fnum(x):
    try: return float(x)
    except: return 0.0

def sma(vals, n):
    if len(vals) < n: return sum(vals) / max(1, len(vals))
    return sum(vals[-n:]) / n

def rsi(closes, n=14):
    if len(closes) < n + 1: return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i-1]
        gains.append(max(ch, 0)); losses.append(max(-ch, 0))
    g = sum(gains[:n]) / n; l = sum(losses[:n]) / n
    for i in range(n, len(gains)):
        g = (g*(n-1) + gains[i]) / n
        l = (l*(n-1) + losses[i]) / n
    if l == 0: return 100.0
    rs = g / l
    return 100 - 100 / (1 + rs)

def atr_pct(bars, n=14):
    if len(bars) < n + 1: return 0.0
    trs = []
    for i in range(1, len(bars)):
        h = bars[i][3]; l = bars[i][4]; c_prev = bars[i-1][2]
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        trs.append(tr)
    a = sma(trs, n)
    return a / bars[-1][2] * 100

def min5_dt(date_int, second_int):
    hh = second_int // 3600
    mm = (second_int % 3600) // 60
    return f"{date_int} {hh:02d}{mm:02d}"

def load_kl(code):
    p = os.path.join(BASE, f"_kl_{code}.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def metrics(day, q):
    # day: [date, open, close, high, low, vol]  老->新
    closes = [b[2] for b in day]
    vols = [b[5] for b in day]
    ma20 = sma(closes, 20); ma20_5 = sma(closes[:-5], 20) if len(closes) > 25 else ma20
    ma60 = sma(closes, 60); ma60_5 = sma(closes[:-5], 60) if len(closes) > 65 else ma60
    last = closes[-1]
    ma20_up = ma20 >= ma20_5
    price_above = last >= ma20
    ma60_up = ma60 >= ma60_5
    r = rsi(closes, 14)
    a = atr_pct(day, 14)
    ma20v = sma(vols, 20)
    vratio = (vols[-1] / ma20v) if ma20v > 0 else 1.0
    if vratio >= 1.5 or q["lb"] >= 2.5:
        vol = "high"
    elif vratio >= 0.8:
        vol = "normal"
    else:
        vol = "low"
    highs = [b[3] for b in day]
    prev19 = max(highs[-20:-1]) if len(highs) >= 20 else max(highs)
    if highs[-1] > prev19 * 1.0001:
        struct = "breakout"
    elif abs(last - ma20) / ma20 < 0.03 and closes[-1] < closes[-2]:
        struct = "pullback"
    else:
        struct = "neutral"
    hz = q["hyzaf"]
    if hz >= 1.0: sector = "strong"
    elif hz >= 0.0: sector = "mid"
    else: sector = "weak"
    return dict(ma20="up" if ma20_up else "down", priceMa="above" if price_above else "below",
                ma60="up" if ma60_up else "down", rsi=round(r, 1), atr=round(a, 2),
                vol=vol, struct=struct, sector=sector)

def score(m, q):
    s = 0
    s += 10 if m["ma20"] == "up" else 0
    s += 8 if m["priceMa"] == "above" else 0
    s += 7 if m["ma60"] == "up" else 0
    s += {"breakout":20, "pullback":16}.get(m["struct"], 4)
    s += {"high":15, "normal":8, "low":2}[m["vol"]]
    s += {"strong":15, "mid":9, "weak":3}[m["sector"]]
    rs = m["rsi"]
    if 40 <= rs <= 60: s += 15
    elif (30 <= rs < 40) or (60 < rs <= 70): s += 8
    else: s += 3
    loss = 3.0 if q["board"] in ("cyb", "kcb") else 2.0
    if m["atr"] <= loss * 1.2: s += 10
    elif m["atr"] <= loss * 1.8: s += 5
    else: s += 0
    win = min(88, 50 + s * 0.35)
    return s, round(win, 1), loss

# ---------- 主流程 ----------
rows = []
for code, q in QUOTES.items():
    kl = load_kl(code)
    day_raw = [[str(b[0]), fnum(b[1]), fnum(b[2]), fnum(b[3]), fnum(b[4]), fnum(b[5])] for b in kl["day"]]
    min5_raw = kl["min5"]
    # 用权威收盘价修正最后一棒
    final_close = q["now"]
    if day_raw: day_raw[-1][2] = final_close
    if min5_raw: min5_raw[-1][2] = final_close
    day_t = day_raw[-70:] if len(day_raw) >= 70 else day_raw
    m = metrics(day_t, q)
    total, win, loss = score(m, q)
    entry = round(final_close, 2)
    stop = round(entry * (1 - loss/100), 2)
    target = round(entry * (1 + (loss*3)/100), 2)
    rows.append(dict(code=code, name=q["name"], board=q["board"], m=m,
                     total=total, win=win, entry=entry, stop=stop, target=target,
                     pct=q["pct"], lb=q["lb"], hyzaf=q["hyzaf"]))

rows.sort(key=lambda x: (-x["win"], -x["total"]))

# 达标判定：总分>=57 -> 胜率>=70%
PASS = 57
final_items = []
watch_items = []  # 本次无观察池逻辑，但保留结构
for r in rows:
    passed = r["total"] >= PASS
    if not passed:
        continue
    item = dict(
        name=f'{r["name"]} {r["code"]}',
        code=r["code"],
        setcode=setcode_of(r["code"]),
        board=r["board"],
        ma20=r["m"]["ma20"], priceMa=r["m"]["priceMa"], ma60=r["m"]["ma60"],
        rsi=r["m"]["rsi"], vol=r["m"]["vol"], struct=r["m"]["struct"],
        sector=r["m"]["sector"], atr=r["m"]["atr"],
        score=r["total"], win=r["win"],
        category="final", date=DATA_DATE,
        stopPrice=r["stop"], targetPrice=r["target"],
    )
    # 内嵌 K 线
    kl = load_kl(r["code"])
    day_out = [[str(b[0]), fnum(b[1]), fnum(b[2]), fnum(b[3]), fnum(b[4]), fnum(b[5])] for b in kl["day"][-70:]]
    if day_out: day_out[-1][2] = r["entry"]
    min5_out = []
    for b in kl["min5"][-48:]:
        date_int = int(b[0]); second_int = int(b[1])
        min5_out.append([min5_dt(date_int, second_int), fnum(b[2]), fnum(b[3]), fnum(b[4]), fnum(b[5]), fnum(b[6])])
    if min5_out: min5_out[-1][2] = r["entry"]
    item["kline"] = dict(day=day_out, min5=min5_out)
    final_items.append(item)

final_items.sort(key=lambda x: -x["win"])
updated = datetime.datetime.now().astimezone().isoformat()
out = dict(updated=updated, items=final_items, watch=watch_items)
json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False)
print(f"wrote {OUT_JSON}: final={len(final_items)}, watch={len(watch_items)}, size~{os.path.getsize(OUT_JSON)//1024}KB")

# ---------- 生成 2026-07-16.md ----------
def reason_line(r):
    m = r  # final_items carry metric fields at top level
    parts = []
    parts.append("MA20" + ("↑" if m["ma20"] == "up" else "↓"))
    parts.append("MA60" + ("↑" if m["ma60"] == "up" else "↓"))
    parts.append({"breakout": "放量突破", "pullback": "回踩", "neutral": "震荡"}[m["struct"]])
    parts.append({"high": "放量", "normal": "量平", "low": "缩量"}[m["vol"]])
    parts.append({"strong": "板块强", "mid": "板块中", "weak": "板块弱"}[m["sector"]])
    parts.append(f"RSI{m['rsi']}")
    parts.append(f"ATR{m['atr']}%")
    return "·".join(parts)

lines = []
lines.append(f"# 盘后定稿 · A股稳健选股策略（{DATA_DATE}）\n")
lines.append(f"> 数据时间戳：2026-07-16 15:30 收盘（通达信 HQDate=20260716）。所有胜率均为技术估计，非投资建议；仅选股并警示，不下单/交易。\n")

lines.append("## 一、大盘环境（Step-8 风控）\n")
lines.append("| 指数 | 代码 | 涨跌幅 |")
lines.append("|------|------|--------|")
for nm, cd, chg in INDICES:
    lines.append(f"| {nm} | {cd} | {chg:+.2f}% |")
triggered = any(chg <= -2.0 for _, _, chg in INDICES)
lines.append("")
if triggered:
    lines.append("⚠️ **Step-8 警示**：创业板指单日跌幅 >2%（三指同步下挫），属普跌/系统性回调环境。建议**收缩或暂停新增开仓**，仅保留既有的高胜率逆市强势标的观察，严格按 3:1 止损纪律执行。\n")
else:
    lines.append("✅ 大盘未触发跌超 2% 暂停警示。\n")

lines.append("## 二、达标清单（总分≥57 → 胜率≥70%，按胜率降序）\n")
lines.append("| 排名 | 名称/代码 | 板块 | 综合分 | 胜率估计 | 止损价 | 目标价 | 一句话理由 |")
lines.append("|------|-----------|------|--------|----------|--------|--------|------------|")
for i, r in enumerate(final_items, 1):
    nm = f'{r["name"]} {r["code"]}'
    lines.append(f'| {i} | {nm} | {r["board"]} | {r["score"]} | {r["win"]:.1f}% | {r["stopPrice"]} | {r["targetPrice"]} | {reason_line(r)} |')

lines.append("")
lines.append("## 三、盘中简报\n")
lines.append(f"- **达标数**：{len(final_items)} 只（候选池 {len(rows)} 只，阈值 总分≥57）")
if final_items:
    top3 = "、".join(f'{it["name"].split()[0]}({it["win"]:.1f}%)' for it in final_items[:3])
    lines.append(f"- **前 3**：{top3}")
lines.append("- **风险提示**：")
lines.append("  1. 全批 ATR% 普遍偏高（止损适配维度多计 0 分），固定比例止损易被扫损，建议按 ATR 动态止损或减仓。")
rsi_hot = [r for r in final_items if r["rsi"] > 70]
if rsi_hot:
    names = "、".join(r["name"].split()[0] for r in rsi_hot)
    lines.append(f"  2. RSI 超买（>70）：{names}，追高风险大，宜等回踩 MA20 买点。")
pct_hot = [r for r in final_items if QUOTES[r["code"]]["pct"] > 6]
if pct_hot:
    names = "、".join(f'{r["name"].split()[0]}(+{QUOTES[r["code"]]["pct"]:.1f}%)' for r in pct_hot)
    lines.append(f"  3. 同日涨幅偏大：{names}，短线获利盘丰厚，注意回调。")
lines.append("  4. 本周交易笔数无法读取系统 localStorage，请自行在「风控看板」核对是否超 5 笔。")
lines.append("  5. 所有标的均为技术面逆市放量突破筛选，板块强度多数偏弱，属题材轮动博弈，非长线价值仓。")

lines.append("")
lines.append("## 四、完整评分明细\n")
lines.append("| 名称/代码 | 板块 | ma20 | 价/MA20 | ma60 | RSI | ATR% | 结构 | 量能 | 板块 | 综合分 | 胜率 |")
lines.append("|-----------|------|------|---------|------|-----|------|------|------|------|--------|------|")
for r in rows:
    m = r["m"]
    tag = "✅达标" if r["total"] >= PASS else "—"
    lines.append(f'| {r["name"]} {r["code"]} | {r["board"]} | {m["ma20"]} | {m["priceMa"]} | {m["ma60"]} | {m["rsi"]} | {m["atr"]} | {m["struct"]} | {m["vol"]} | {m["sector"]} | {r["total"]} | {r["win"]:.1f}% {tag} |')

lines.append("")
lines.append("---")
lines.append(f"\n_生成时间：{updated}_  |  引擎：6 维加权（趋势25/结构20/量能15/板块15/RSI15/止损适配10），胜率=min(88, 50+总分×0.35)。")

md = "\n".join(lines)
open(OUT_MD, "w", encoding="utf-8").write(md)
print(f"wrote {OUT_MD}")

# 控制台汇总
print("\n=== 评分汇总（按胜率降序）===")
print(f"{'code':6} {'name':6} {'board':4} {'ma20':4} {'pMA':5} {'ma60':4} {'rsi':5} {'atr%':6} {'struct':9} {'vol':6} {'sector':6} {'tot':3} {'win%':5} {'pass'}")
for r in rows:
    m = r["m"]
    print(f"{r['code']:6} {r['name']:6} {r['board']:4} {m['ma20']:4} {m['priceMa']:5} {m['ma60']:4} {m['rsi']:<5} {m['atr']:<6} {m['struct']:9} {m['vol']:6} {m['sector']:6} {r['total']:<3} {r['win']:<5} {'Y' if r['total']>=PASS else 'N'}")
