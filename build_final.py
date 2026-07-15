# -*- coding: utf-8 -*-
"""
盘后定稿引擎：读取 选股结果/import_pre.json（07-10 预选，K线已结束于 2026-07-10），
用复拉的 15:00 收盘/板块强度修正入场价与板块维度，按系统 scoreCandidate 引擎重算 6 维评分与综合强度分，
筛选 strength>=70 达标标的（star->kcb 修正），内嵌 day(70)/min5(245) K线，输出定稿 MD + import_final.json。

v1.2 改进项：
- P1: "胜率"→"综合强度分"(strength)，消除标签欺诈；win 字段留给 recalibrate_win.py 回填真实回测胜率。
- P2: ATR 止损适配从硬门槛改为池内百分位打分(0-10)，复活已死的 ATR 维度。
- P3: 新增同日涨幅过滤：pct>9.5% 硬拒绝；pct>6% 扣 10 分+追高警告。
- P4: RSI>72 超买硬约束，无论综合分多高都不放行。
"""
import os, json, datetime

BASE = r"D:/WorkBuddy"
PRE = os.path.join(BASE, "选股结果", "import_pre.json")
OUT_MD = os.path.join(BASE, "选股结果", "2026-07-10.md")
OUT_JSON = os.path.join(BASE, "选股结果", "import_final.json")
DATA_DATE = "2026-07-10"

# 复拉的盘后行情快照（15:00，HQDate=20260710）。now=今日收盘价(入场价)，pct=涨跌幅，lb=量比，hyzaf=所属板块当日涨跌幅
QUOTES = {
    "000779": dict(name="甘咨询",   now=10.60, pct=8.05,  lb=1.9458, hyzaf=2.4115),
    "600288": dict(name="大恒科技", now=16.54, pct=-1.43, lb=1.3325, hyzaf=-0.0849),
    "603137": dict(name="恒尚节能", now=26.75, pct=6.15,  lb=3.1225, hyzaf=2.9188),
    "688722": dict(name="同益中",   now=18.31, pct=19.99, lb=4.5409, hyzaf=0.5898),
    "300918": dict(name="南山智尚", now=12.37, pct=19.52, lb=3.2879, hyzaf=0.7747),
    "688101": dict(name="三达膜",   now=17.11, pct=11.39, lb=6.3666, hyzaf=0.3676),
    "301367": dict(name="瑞迈特",   now=44.99, pct=16.61, lb=2.2034, hyzaf=0.9753),
    "002414": dict(name="高德红外", now=14.64, pct=9.99,  lb=3.9773, hyzaf=1.0815),
    "002144": dict(name="宏达高科", now=10.77, pct=10.01, lb=5.3001, hyzaf=0.7747),
    "600718": dict(name="东软集团", now=8.00,  pct=9.14,  lb=3.8226, hyzaf=0.8993),
    "002841": dict(name="视源股份", now=52.45, pct=0.61,  lb=1.9938, hyzaf=-3.1252),
}

def setcode_of(code):
    return "1" if code[0] == "6" else "0"

# ---------- 指标计算（与 parse_and_score.py / 系统口径一致） ----------
def sma(vals, n):
    if len(vals) < n:
        return sum(vals) / max(1, len(vals))
    return sum(vals[-n:]) / n

def rsi(closes, n=14):
    if len(closes) < n + 1:
        return 50.0
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

def metrics(day, q):
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

# ---------- 评分引擎（P1-P4 改进版，严格与 stock-selection-system.html scoreCandidate 同步） ----------
def board_params(board):
    if board == "main":
        return dict(loss=2.0, profit=6.0)
    return dict(loss=3.0, profit=9.0)  # cyb / kcb 放宽 50%

# P4 硬约束：RSI 超买线
RSI_OVERBOUGHT = 72

# P3 涨幅过滤阈值
PCT_HARD_REJECT = 9.5   # % 同日涨幅超此值硬拒绝
PCT_WARNING = 6.0       # % 超此值扣分+警告

def score_candidate(c, pool_atrs=None):
    """返回 (total_score, formula_strength, atr_fit, bp, reasons, reject_info)
       - total_score: 6 维原始总分
       - formula_strength: P1 综合强度分 = min(88, 50 + total*0.35)，非真实胜率
       - atr_fit: P2 ATR 百分位得分(0-10)
       - reject_info: P3/P4 拒绝原因字符串，None 表示未拒绝
    """
    s = 0; reasons = []

    # ---- P4: RSI 超买硬约束（最优先检查）----
    if c["rsi"] > RSI_OVERBOUGHT:
        return (0, 0, 0, board_params(c["board"]), reasons,
                f"P4硬拒: RSI={c['rsi']:.1f}>{RSI_OVERBOUGHT} 超买区，不参与评分")

    # 趋势 25
    t = 0
    if c["ma20"] == "up": t += 10
    if c["priceMa"] == "above": t += 8
    if c["ma60"] == "up": t += 7
    s += t; reasons.append(f"趋势 {t}/25")
    st = {"breakout":20,"pullback":16}.get(c["struct"], 4)
    s += st; reasons.append(f"结构 {st}/20")
    v = {"high":15,"normal":8,"low":2}[c["vol"]]
    s += v; reasons.append(f"量能 {v}/15")
    sec = {"strong":15,"mid":9,"weak":3}[c["sector"]]
    s += sec; reasons.append(f"板块 {sec}/15")
    rs = c["rsi"]
    if 40 <= rs <= 60: r = 15
    elif (30 <= rs < 40) or (60 < rs <= 70): r = 8
    else: r = 3
    s += r; reasons.append(f"RSI {r}/15")

    # P2: ATR 分位打分（池内百分位）
    bp = board_params(c["board"])
    if pool_atrs is not None and len(pool_atrs) >= 2:
        # 百分位排名：ATR 越小 → 排名越靠前 → fit 越高
        sorted_atrs = sorted(pool_atrs)
        rank = sorted_atrs.index(c["atr"]) if c["atr"] in sorted_atrs else 0
        pct_rank = rank / (len(sorted_atrs) - 1)  # 0 = 最小ATR(最好), 1 = 最大ATR(最差)
        fit = max(0, round(10 * (1 - pct_rank)))
    else:
        # 无池信息时退化到连续衰减（比原硬门槛更宽容）
        fit = max(0, round(10 * max(0, 1 - c["atr"] / (bp["loss"] * 3))))
    s += fit; reasons.append(f"ATR适配 {fit}/10")

    strength = min(88, 50 + s * 0.35)  # P1: 这是综合强度分，不是胜率

    # P3: 涨幅过滤（由调用方传入 c.get("pct")）
    reject = None
    if "pct" in c:
        pct_val = c["pct"]
        if pct_val > PCT_HARD_REJECT:
            reject = f"P3硬拒: 同日涨幅{pct_val:.1f}%>{PCT_HARD_REJECT}% 追高风险，拒绝"
            s -= 999  # 确保不达标
            reasons.append(f"<b>⛔ 追高拒绝: 日涨+{pct_val:.1f}%</b>")
        elif pct_val > PCT_WARNING:
            s -= 10
            reasons.append(f"⚠️ 追高惩罚-10: 日涨+{pct_val:.1f}%>{PCT_WARNING}%")

    return (s, round(strength, 1), fit, bp, reasons, reject)

# ---------- 主流程 ----------
pre = json.load(open(PRE, encoding="utf-8"))
pre_items = pre["items"]

# 先做第一遍 metrics（仅提取 ATR 用于 P2 百分位打分）
raw_metrics = []
for it in pre_items:
    name_full = it["name"]
    code = name_full.strip().split()[-1]
    q = QUOTES.get(code)
    if not q: continue
    board = it.get("board")
    if board == "star": board = "kcb"
    day = [list(b) for b in it["kline"]["day"]]
    final_close = q["now"]
    if day: day[-1][2] = final_close
    day_t = day[-70:] if len(day) >= 70 else day
    m = metrics(day_t, q)
    raw_metrics.append((code, m["atr"]))

pool_atrs = [a for _, a in raw_metrics]

all_rows = []
final_items = []

for it in pre_items:
    name_full = it["name"]                      # "三达膜 688101"
    code = name_full.strip().split()[-1]        # "688101"
    q = QUOTES.get(code)
    if not q:
        print("!! 缺少复发行情:", code, name_full); continue
    board = it.get("board")
    if board == "star":
        board = "kcb"                            # 系统引擎用 kcb（688 科创板）
    assert board in ("main","cyb","kcb"), board

    day = [list(b) for b in it["kline"]["day"]]   # 老->新 [date,o,c,h,l,v]
    min5 = [list(b) for b in it["kline"]["min5"]]

    # 用权威 15:00 收盘价修正最后一棒（K线原为 14:50 盘中值）
    final_close = q["now"]
    if day: day[-1][2] = final_close
    if min5: min5[-1][2] = final_close

    day_t = day[-70:] if len(day) >= 70 else day
    min5_t = min5[-245:] if len(min5) >= 245 else min5

    m = metrics(day_t, q)
    entry = round(final_close, 2)
    c = dict(board=board, ma20=m["ma20"], priceMa=m["priceMa"], ma60=m["ma60"],
             rsi=m["rsi"], vol=m["vol"], struct=m["struct"], sector=m["sector"],
             atr=m["atr"])
    # P3: 注入同日涨幅
    c["pct"] = q.get("pct", 0)

    total, strength, fit, bp, reasons, reject_info = score_candidate(c, pool_atrs=pool_atrs)
    stop = round(entry * (1 - bp["loss"]/100), 2)
    target = round(entry * (1 + bp["profit"]/100), 2)

    # P3/P4 拒决判定
    hard_rejected = reject_info is not None
    pass_ = (strength >= 70) and (not hard_rejected)

    row = dict(code=code, name=name_full, board=board, q=q, m=m,
               total=total, strength=strength, fit=fit, bp=bp,
               reasons=reasons, entry=entry, stop=stop, target=target,
               pass_=pass_, rejected=hard_rejected, reject_reason=reject_info or "",
               pct=c.get("pct",0),
               day=day_t, min5=min5_t)
    all_rows.append(row)

    if pass_:
        item = dict(name=name_full, code=code, setcode=setcode_of(code), board=board,
                    ma20=m["ma20"], priceMa=m["priceMa"], ma60=m["ma60"], rsi=m["rsi"],
                    vol=m["vol"], struct=m["struct"], sector=m["sector"], atr=m["atr"],
                    score=total, win=strength,          # P1: score=原始总分, strength=综合强度分(公式), win待recalibrate覆盖
                    category="final", date=DATA_DATE,
                    stopPrice=stop, targetPrice=target,
                    kline=dict(day=day_t, min5=min5_t))
        final_items.append(item)

# 排序：综合强度分降序，同分综合分降序
all_rows.sort(key=lambda x: (-x["strength"], -x["total"]))
final_items.sort(key=lambda x: -x["win"])

print("=== 全候选 6 维评分（P1-P4 改进版，11 只，按综合强度分降序）===")
print(f"{'code':6} {'name':8} {'board':4} {'ma20':4} {'pMA':5} {'ma60':4} {'rsi':5} {'atr%':6} {'pct%':5} {'struct':9} {'vol':6} {'sector':6} {'fit':3} {'tot':3} {'str%':5} {'pass':4} {'reject'}")
for r in all_rows:
    m = r["m"]
    rej = r["reject_reason"][:20] if r["rejected"] else ""
    print(f"{r['code']:6} {r['q']['name']:8} {r['board']:4} {m['ma20']:4} {m['priceMa']:5} {m['ma60']:4} {m['rsi']:<5} {m['atr']:<6} {r['pct']:<5.1f} {m['struct']:9} {m['vol']:6} {m['sector']:6} {r['fit']:<3} {r['total']:<3} {r['strength']:<5} {'Y' if r['pass_'] else 'N':<4} {rej}")

rejected_count = sum(1 for r in all_rows if r["rejected"])
print(f"\nP3/P4 硬拒绝: {rejected_count} 只")
print(f"达标数(综合强度分>=70): {len(final_items)} / 候选 {len(all_rows)}")

# ---------- 写 import_final.json ----------
updated = datetime.datetime.now().astimezone().isoformat()
out = dict(updated=updated, items=final_items)
json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False)
print("wrote", OUT_JSON, "items=", len(final_items), "size~", os.path.getsize(OUT_JSON)//1024, "KB")

# 把全量明细存一份供生成 MD 用
json.dump(dict(all_rows=[{k:v for k,v in r.items() if k not in ('day','min5')} for r in all_rows],
               final_count=len(final_items), rejected_count=rejected_count, updated=updated),
          open(os.path.join(BASE, "_final_summary.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("wrote _final_summary.json")
