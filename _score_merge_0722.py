# -*- coding: utf-8 -*-
"""2026-07-22 盘后定稿：解析 8 个 tdx_kline tool-result 文件 -> 归一化 K 线 ->
按 gen_final_0716.py 引擎对 4 只候选评分 -> 合并进 import_final.json（保留既有 24 项）。
"""
import os, json, glob, datetime

BASE = r"D:/WorkBuddy"
TR_DIR = "C:/Users/fanfan/.workbuddy/projects/d-WorkBuddy/95f3708a-a784-4f2c-8fae-95005c6782af/tool-results"
OUT_DIR = os.path.join(BASE, "选股结果")
OUT_JSON = os.path.join(OUT_DIR, "import_final.json")
DATA_DATE = "2026-07-22"

# ---------- 候选权威快照（tdx_quotes HQDate=20260722 + tool-result 表头现价） ----------
QUOTES = {
    "300643": dict(name="万通智控", board="cyb",  now=19.93, pct=6.92,  lb=3.15, hyzaf=-1.38),
    "300039": dict(name="上海凯宝", board="cyb",  now=5.76,  pct=3.04,  lb=1.06, hyzaf=-0.17),
    "301033": dict(name="迈普医学", board="cyb",  now=56.50, pct=6.20,  lb=0.98, hyzaf=-0.51),
    "001202": dict(name="炬申股份", board="main", now=14.08, pct=7.56,  lb=3.12, hyzaf=-0.03),
}

# ---------- 解析 tool-result 文件 ----------
def extract_json(buf):
    jstart = buf.find("{", buf.find("详细K线数据:"))
    return json.loads(buf[jstart:])

def min5_dt(date_int, second_int):
    hh = int(second_int) // 3600
    mm = (int(second_int) % 3600) // 60
    return f"{date_int} {hh:02d}{mm:02d}"

files = sorted(glob.glob(os.path.join(TR_DIR, "*.txt")))
files = [f for f in files if "tdx_kline" in f]

kl_by_code = {}   # code -> {"day":[...], "min5":[...]}
for f in files:
    buf = open(f, encoding="utf-8").read()
    header = buf.splitlines()[0]
    # 表头: 【名称】代码 | 现价: x.xx ...
    code = header.split("】")[1].split()[0]
    obj = extract_json(buf)
    rows = obj["Rows"]
    is_day = obj.get("Period") == 4
    norm = []
    for r in rows:
        o = float(r["Open"]); c = float(r["Close"]); h = float(r["High"]); lo = float(r["Low"])
        vol = float(r["Volume"])
        if is_day:
            norm.append([r["Data"], o, c, h, lo, vol])
        else:
            dint = int(r["Data"]); sint = int(r["Second"])
            norm.append([min5_dt(dint, sint), o, c, h, lo, vol])
    if is_day:
        kl_by_code.setdefault(code, {})["day"] = norm
    else:
        kl_by_code.setdefault(code, {})["min5"] = norm

# 用权威收盘价修正最后一棒
for code, q in QUOTES.items():
    kl = kl_by_code[code]
    if kl["day"]:
        kl["day"][-1][2] = q["now"]
    if kl["min5"]:
        kl["min5"][-1][2] = q["now"]

# ---------- 指标/评分（严格复制 gen_final_0716.py） ----------
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

def setcode_of(code):
    return "1" if code[0] == "6" else "0"

# ---------- 评分 4 只候选（metrics 用最后 70 根日K，与 gen_final_0716 一致） ----------
PASS = 57
rows = []
for code, q in QUOTES.items():
    kl = kl_by_code[code]
    day_all = kl["day"]
    day_t = day_all[-70:] if len(day_all) >= 70 else day_all
    m = metrics(day_t, q)
    total, win, loss = score(m, q)
    entry = round(q["now"], 2)
    stop = round(entry * (1 - loss/100), 2)
    target = round(entry * (1 + (loss*3)/100), 2)
    rows.append(dict(code=code, name=q["name"], board=q["board"], m=m,
                     total=total, win=win, entry=entry, stop=stop, target=target,
                     pct=q["pct"], lb=q["lb"], hyzaf=q["hyzaf"],
                     kline={"day": day_all, "min5": kl["min5"]}))

rows.sort(key=lambda x: (-x["win"], -x["total"]))

print("=== 候选评分汇总（按胜率降序）===")
print(f"{'code':6} {'name':6} {'board':4} {'ma20':4} {'pMA':5} {'ma60':4} {'rsi':5} {'atr%':6} {'struct':9} {'vol':6} {'sector':6} {'tot':3} {'win%':5} {'pass'}")
new_items = []
for r in rows:
    m = r["m"]
    passed = r["total"] >= PASS
    if passed:
        new_items.append(r)
    print(f"{r['code']:6} {r['name']:6} {r['board']:4} {m['ma20']:4} {m['priceMa']:5} {m['ma60']:4} {m['rsi']:<5} {m['atr']:<6} {m['struct']:9} {m['vol']:6} {m['sector']:6} {r['total']:<3} {r['win']:<5} {'Y' if passed else 'N'}")
    # 校验 K 线末棒
    print(f"     day[-1]={r['kline']['day'][-1][:3]}... len(day)={len(r['kline']['day'])} len(min5)={len(r['kline']['min5'])}")

# ---------- 合并入 import_final.json（保留既有 24 项，去重追加达标新项） ----------
pool = json.load(open(OUT_JSON, encoding="utf-8"))
existing_codes = set(it["code"] for it in pool["items"])
merged = list(pool["items"])
added = 0
for r in new_items:
    if r["code"] in existing_codes:
        print(f"[SKIP] {r['code']} 已在池中，跳过")
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
        kline=r["kline"],
    )
    merged.append(item)
    existing_codes.add(r["code"])
    added += 1

final_items = [it for it in merged if it.get("category") == "final"]
final_items.sort(key=lambda x: -x["win"])
updated = datetime.datetime.now().astimezone().isoformat()
out = dict(updated=updated, items=merged, watch=pool.get("watch", []))
json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False)
print(f"\n[OK] import_final.json: 原 {len(pool['items'])} 项 + 新增 {added} 项 = {len(merged)} 项")
print(f"     新达标 {len(new_items)} 只: {[r['name'] for r in new_items]}")
print(f"     size~{os.path.getsize(OUT_JSON)//1024}KB")
