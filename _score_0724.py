# -*- coding: utf-8 -*-
"""2026-07-24 盘后定稿（16:00 收盘后）：解析 16 个 tdx_kline tool-result 文件 ->
归一化 K 线 -> 按 gen_final_0716.py 引擎对 8 只候选做 6 维评分 -> 筛选达标。
本脚本仅解析+评分+打印，不直接写 import_final.json（校验后再由 merge 脚本落盘）。
依赖：16 个 tool-result 文件（日K~820 + 5分K~245），已落盘。
行情快照：现价/涨跌幅/换手率 取自 tool-result 表头；行业涨幅 HYZAF 取自盘前记录的 07-24 选股上下文。
量比 lb 由 K 线成交量比推导（q["lb"]=0，仅用 vratio>=1.5 判 high），避免依赖不可达的 tdx_quotes。
"""
import os, json, glob, re, datetime

BASE = r"D:/WorkBuddy"
TR_DIR = "C:/Users/fanfan/.workbuddy/projects/d-WorkBuddy/8c4003a5-e276-477c-99fe-8ed72ba74955/tool-results"
DATA_DATE = "2026-07-24"

# 行业涨幅 HYZAF（07-24 盘前选股上下文记录，全部为负 -> 板块维度统一 weak）
HYZAF = {
    "688237": -1.34,  # 超卓航科
    "000011": -1.27,  # 深物业A
    "300779": -1.77,  # 惠城环保
    "001258": -3.41,  # 立新能源
    "605028": -3.41,  # 世茂能源
    "301552": -2.63,  # 科力装备
    "300444": -3.21,  # 双杰电气
    "002112": -3.21,  # 三变科技
}

def board_of(code):
    if code.startswith("688"): return "kcb"
    if code.startswith("300") or code.startswith("301"): return "cyb"
    return "main"

def extract_json(buf):
    j = buf.find("{", buf.find("详细K线数据:"))
    return json.loads(buf[j:])

def min5_dt(date_int, second_int):
    hh = int(second_int) // 3600
    mm = (int(second_int) % 3600) // 60
    return f"{date_int} {hh:02d}{mm:02d}"

# ---------- 解析 16 个 tool-result 文件 ----------
files = sorted(glob.glob(os.path.join(TR_DIR, "*.txt")))
files = [f for f in files if "tdx_kline" in f]
assert len(files) == 16, f"期望 16 个 K 线文件，实得 {len(files)}"

kl_by_code = {}   # code -> {"day","min5","name","now","pct"}
for f in files:
    buf = open(f, encoding="utf-8").read()
    header = buf.splitlines()[0]
    code = header.split("】")[1].split()[0]
    # 表头: 【名称】代码 | 现价: x.xx (+x.xx%) | 换手率: ...
    m_now = re.search(r"现价:\s*([\d.]+)", header)
    m_pct = re.search(r"\(([+-]?\d+\.?\d*)%\)", header)
    name = header.split("】")[0].lstrip("【")
    now = float(m_now.group(1)) if m_now else None
    pct = float(m_pct.group(1)) if m_pct else None
    obj = extract_json(buf)
    rows = obj["Rows"]
    is_day = obj.get("Period") == 4   # 日K Period=4；5分K 无 Period 键
    norm = []
    for r in rows:
        o = float(r["Open"]); c = float(r["Close"]); h = float(r["High"]); lo = float(r["Low"]); vol = float(r["Volume"])
        if is_day:
            norm.append([str(r["Data"]), o, c, h, lo, vol])
        else:
            dint = int(r["Data"]); sint = int(r["Second"])
            norm.append([min5_dt(dint, sint), o, c, h, lo, vol])
    d = kl_by_code.setdefault(code, {"name": name})
    if is_day:
        d["day"] = norm
    else:
        d["min5"] = norm
    d["now"] = now
    d["pct"] = pct

# 用表头现价修正最后一根（与 _score_merge 一致）
for code, d in kl_by_code.items():
    if d.get("now") and d.get("day"):
        d["day"][-1][2] = d["now"]
    if d.get("now") and d.get("min5"):
        d["min5"][-1][2] = d["now"]

# ---------- 指标/评分（严格复制 gen_final_0716.py / _score_merge_0722.py） ----------
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
                vol=vol, struct=struct, sector=sector, vratio=round(vratio, 2))

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

PASS = 57
results = []
for code in HYZAF:
    d = kl_by_code[code]
    board = board_of(code)
    q = dict(name=d["name"], board=board, now=d["now"], pct=d["pct"],
             hyzaf=HYZAF[code], lb=0.0)
    day_all = d["day"]
    day_t = day_all[-70:] if len(day_all) >= 70 else day_all
    m = metrics(day_t, q)
    total, win, loss = score(m, q)
    entry = round(q["now"], 2)
    stop = round(entry * (1 - loss/100), 2)
    target = round(entry * (1 + (loss*3)/100), 2)
    results.append(dict(code=code, name=q["name"], board=board, m=m,
                        total=total, win=win, entry=entry, stop=stop, target=target,
                        pct=q["pct"], hyzaf=q["hyzaf"], vratio=m["vratio"],
                        kline={"day": day_all, "min5": d["min5"]},
                        len_day=len(day_all), len_min5=len(d["min5"])))

results.sort(key=lambda x: (-x["win"], -x["total"]))

print("=== 2026-07-24 候选 6 维评分汇总（胜率降序）===")
print(f"{'code':6}{'name':7}{'board':4}{'ma20':4}{'pMA':5}{'ma60':4}{'rsi':5}{'atr%':6}{'struct':9}{'vol':6}{'sector':6}{'vr':5}{'tot':3}{'win%':5}{'pct':6}{'pass'}")
new_items = []
for r in results:
    m = r["m"]
    passed = r["total"] >= PASS
    if passed: new_items.append(r)
    print(f"{r['code']:6}{r['name']:7}{r['board']:4}{m['ma20']:4}{m['priceMa']:5}{m['ma60']:4}{str(m['rsi']):<5}{str(m['atr']):<6}{m['struct']:9}{m['vol']:6}{m['sector']:6}{str(r['vratio']):<5}{r['total']:<3}{r['win']:<5}{str(r['pct']):<6}{'Y' if passed else 'N'}")
    print(f"     len(day)={r['len_day']} len(min5)={r['len_min5']} day[-1]={r['kline']['day'][-1][:3]} min5[-1]={r['kline']['min5'][-1][:3]}")

print(f"\n达标（>=57）：{len(new_items)} 只 -> {[ (r['name'],r['code']) for r in new_items ]}")
print(f"落选：{[ (r['name'],r['code'],r['total']) for r in results if r['total']<PASS ]}")

# 落盘中间结果供 merge 脚本读取
out_inter = dict(date=DATA_DATE, results=results, new_codes=[r["code"] for r in new_items])
json.dump(out_inter, open(os.path.join(BASE, "_scored_0724.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("\n[_scored_0724.json 已写出]")
