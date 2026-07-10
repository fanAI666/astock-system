# -*- coding: utf-8 -*-
"""
盘后定稿引擎：读取 选股结果/import_pre.json（07-10 预选，K线已结束于 2026-07-10），
用复拉的 15:00 收盘/板块强度修正入场价与板块维度，按系统 scoreCandidate 引擎重算 6 维评分与胜率，
筛选 win>=70% 达标标的（star->kcb 修正），内嵌 day(70)/min5(245) K线，输出定稿 MD + import_final.json。
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

# ---------- 评分引擎（严格复刻 stock-selection-system.html scoreCandidate） ----------
def board_params(board):
    if board == "main":
        return dict(loss=2.0, profit=6.0)
    return dict(loss=3.0, profit=9.0)  # cyb / kcb 放宽 50%

def score_candidate(c):
    s = 0; reasons = []
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
    bp = board_params(c["board"])
    if c["atr"] <= bp["loss"] * 1.2: fit = 10
    elif c["atr"] <= bp["loss"] * 1.8: fit = 5
    else: fit = 0
    s += fit; reasons.append(f"止损适配 {fit}/10")
    win = min(88, 50 + s * 0.35)
    return s, round(win, 1), fit, bp, reasons

# ---------- 主流程 ----------
pre = json.load(open(PRE, encoding="utf-8"))
pre_items = pre["items"]

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
             rsi=m["rsi"], vol=m["vol"], struct=m["struct"], sector=m["sector"], atr=m["atr"])
    total, win, fit, bp, reasons = score_candidate(c)
    stop = round(entry * (1 - bp["loss"]/100), 2)
    target = round(entry * (1 + bp["profit"]/100), 2)
    pass_ = win >= 70

    row = dict(code=code, name=name_full, board=board, q=q, m=m, total=total, win=win,
               fit=fit, reasons=reasons, entry=entry, stop=stop, target=target, pass_=pass_,
               day=day_t, min5=min5_t, bp=bp)
    all_rows.append(row)

    if pass_:
        item = dict(name=name_full, code=code, setcode=setcode_of(code), board=board,
                    ma20=m["ma20"], priceMa=m["priceMa"], ma60=m["ma60"], rsi=m["rsi"],
                    vol=m["vol"], struct=m["struct"], sector=m["sector"], atr=m["atr"],
                    win=win, entry=entry, category="final", date=DATA_DATE,
                    stopPrice=stop, targetPrice=target,
                    kline=dict(day=day_t, min5=min5_t))
        final_items.append(item)

# 排序：胜率降序，同胜率综合分降序
all_rows.sort(key=lambda x: (-x["win"], -x["total"]))
final_items.sort(key=lambda x: -x["win"])

print("=== 全候选 6 维评分（11 只，按胜率降序）===")
print(f"{'code':6} {'name':8} {'board':4} {'ma20':4} {'pMA':5} {'ma60':4} {'rsi':5} {'atr%':6} {'struct':9} {'vol':6} {'sector':6} {'fit':3} {'tot':3} {'win%':5} {'pass':4}")
for r in all_rows:
    m = r["m"]
    print(f"{r['code']:6} {r['name'].split()[-1] if False else r['q']['name']:8} {r['board']:4} {m['ma20']:4} {m['priceMa']:5} {m['ma60']:4} {m['rsi']:<5} {m['atr']:<6} {m['struct']:9} {m['vol']:6} {m['sector']:6} {r['fit']:<3} {r['total']:<3} {r['win']:<5} {'Y' if r['pass_'] else 'N':<4}")

print(f"\n达标数(胜率>=70%): {len(final_items)} / 候选 {len(all_rows)}")

# ---------- 写 import_final.json ----------
updated = datetime.datetime.now().astimezone().isoformat()
out = dict(updated=updated, items=final_items)
json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False)
print("wrote", OUT_JSON, "items=", len(final_items), "size~", os.path.getsize(OUT_JSON)//1024, "KB")

# 把全量明细存一份供生成 MD 用
json.dump(dict(all_rows=[{k:v for k,v in r.items() if k not in ('day','min5')} for r in all_rows],
               final_count=len(final_items), updated=updated),
          open(os.path.join(BASE, "_final_summary.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("wrote _final_summary.json")
