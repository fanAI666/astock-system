# -*- coding: utf-8 -*-
"""2026-07-27 盘后定稿（16:00 收盘后）Step2-4：解析 10 个 tdx_kline 日K tool-result 文件 ->
归一化 -> 6 维评分 -> 筛选达标(总分>=57)。
行情快照：8 只来自本会话 tdx_quotes（HYZAF/LB/Now），2 只(300441/600369)因 tdx 断连缺失 ->
按 spec「缺失按中性/平处理」：板块=中性(mid=9)、量比=0(由日K量比vratio判定)。
5分K线因 tdx 断连无法拉取 -> 本步仅评分，min5 在 merge 步置空并标注。
依赖：tool-results 目录 11 个日K文件(301122 重复，去重)。
"""
import os, json, glob, re

BASE = r"D:/WorkBuddy"
TR_DIR = "C:/Users/fanfan/.workbuddy/projects/d-WorkBuddy/03e33504-fe77-4a54-a3b3-15cf18a828e2/tool-results"
DATA_DATE = "2026-07-27"

# 本会话 tdx_quotes 实测（HQDate=20260727）：code -> (now, pct, lb, hyzaf)
QUOTES = {
    "301122": (33.2, 15.84, 2.01126194, 2.48291636),
    "002879": (19.86, 10.03, 2.99272394, 3.01221752),
    "001328": (31.42, 10.01, 1.74055254, 6.6770339),
    "002900": (12.54, 10.00, 1.21045876, 2.24609661),
    "002415": (36.99, 4.23, 2.7724371, 2.19862771),
    "000581": (17.05, 1.01, 0.570281744, 2.51111722),
    "002345": (10.39, 5.16, 1.11600542, 2.55343533),
    "600155": (5.7, 3.07, 0.913476348, 0.429103762),
}
# 缺失(tdx 断连)：300441 / 600369 -> pct 取自盘前 screener 上下文，HYZAF/LB 缺失
MISSING = {
    "300441": (7.59, "cyb"),   # 鲍斯股份 +7.59%（均线多头站上20日线），创业板
    "600369": (0.99, "main"),  # 西南证券 +0.99%（均线多头站上20日线），主板
}

def board_of(code):
    if code.startswith("688"): return "kcb"
    if code.startswith("300") or code.startswith("301"): return "cyb"
    return "main"

def extract_json(buf):
    j = buf.find("{", buf.find("详细K线数据:"))
    return json.loads(buf[j:])

# ---------- 解析日K文件（去重 by code，保留末次） ----------
kl_by_code = {}
for f in sorted(glob.glob(os.path.join(TR_DIR, "*tdx_kline*.txt"))):
    buf = open(f, encoding="utf-8").read()
    header = buf.splitlines()[0]
    code = header.split("】")[1].split()[0]
    obj = extract_json(buf)
    rows = obj["Rows"]
    norm = []
    for r in rows:
        o = float(r["Open"]); c = float(r["Close"]); h = float(r["High"]); lo = float(r["Low"]); vol = float(r["Volume"])
        norm.append([str(r["Data"]), o, c, h, lo, vol])
    # 末棒以表头现价修正（与既有管线一致）
    m_now = re.search(r"现价:\s*([\d.]+)", header)
    if m_now:
        norm[-1][2] = float(m_now.group(1))
    kl_by_code[code] = norm   # 覆盖式去重

print(f"[解析] 日K文件 -> {len(kl_by_code)} 只唯一标的: {sorted(kl_by_code)}")

# ---------- 指标/评分（严格复制 _score_0724.py / gen_final_0716.py 引擎） ----------
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
    if hz is None:
        sector = "mid"   # 缺失按中性
    elif hz >= 1.0: sector = "strong"
    elif hz >= 0.0: sector = "mid"
    else: sector = "weak"
    return dict(ma20="up" if ma20_up else "down", priceMa="above" if price_above else "below",
                ma60="up" if ma60_up else "down", rsi=round(r, 1), atr=round(a, 2),
                vol=vol, struct=struct, sector=sector, vratio=round(vratio, 2),
                hyzaf=hz)

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

PASS = 57
results = []
for code in sorted(kl_by_code):
    day_all = kl_by_code[code]
    board = board_of(code)
    if code in QUOTES:
        now, pct, lb, hyzaf = QUOTES[code]
        q = dict(board=board, now=now, pct=pct, lb=lb, hyzaf=hyzaf, src="quote")
    elif code in MISSING:
        pct, _ = MISSING[code]
        now = day_all[-1][2]
        q = dict(board=board, now=now, pct=pct, lb=0.0, hyzaf=None, src="missing-neutral")
    else:
        continue
    day_t = day_all[-70:] if len(day_all) >= 70 else day_all
    m = metrics(day_t, q)
    total, win, loss = score(m, q)
    entry = round(q["now"], 2)
    stop = round(entry * (1 - loss/100), 2)
    target = round(entry * (1 + (loss*3)/100), 2)
    results.append(dict(code=code, name=None, board=board, m=m,
                        total=total, win=win, entry=entry, stop=stop, target=target,
                        pct=q["pct"], hyzaf=q["hyzaf"], vratio=m["vratio"],
                        src=q["src"], kline={"day": day_all, "min5": []},
                        len_day=len(day_all)))

# 名称补全（从日K AttachInfo）
for r in results:
    f = [x for x in glob.glob(os.path.join(TR_DIR, "*tdx_kline*.txt")) if r["code"] in open(x, encoding="utf-8").read().splitlines()[0]]
    if f:
        buf = open(f[0], encoding="utf-8").read()
        r["name"] = buf.splitlines()[0].split("】")[0].lstrip("【")

results.sort(key=lambda x: (-x["win"], -x["total"]))

print("=== 2026-07-27 候选 6 维评分汇总（胜率降序）===")
print(f"{'code':6}{'name':6}{'board':4}{'ma20':4}{'pMA':5}{'ma60':4}{'rsi':5}{'atr%':6}{'struct':9}{'vol':6}{'sector':6}{'vr':5}{'tot':4}{'win%':6}{'pct':6}{'src':9}{'pass'}")
new_items = []
for r in results:
    m = r["m"]
    passed = r["total"] >= PASS
    if passed: new_items.append(r)
    print(f"{r['code']:6}{r['name']:6}{r['board']:4}{m['ma20']:4}{m['priceMa']:5}{m['ma60']:4}{str(m['rsi']):<5}{str(m['atr']):<6}{m['struct']:9}{m['vol']:6}{m['sector']:6}{str(r['vratio']):<5}{r['total']:<4}{r['win']:<6}{str(r['pct']):<6}{r['src']:9}{'Y' if passed else 'N'}")

print(f"\n达标（>=57）：{len(new_items)} 只 -> {[(r['name'], r['code'], r['win']) for r in new_items]}")
print(f"落选：{[(r['name'], r['code'], r['total']) for r in results if r['total'] < PASS]}")

out = dict(date=DATA_DATE, results=results, new_codes=[r["code"] for r in new_items])
json.dump(out, open(os.path.join(BASE, "_scored_0727.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("\n[_scored_0727.json 已写出]")
