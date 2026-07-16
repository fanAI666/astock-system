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

# P6: 静态行业映射（本地演示用；生产环境由 16:00 自动化接真实申万一级行业替换）
# 仅覆盖本批 11 只候选，键=代码，值=行业名
INDUSTRY_OF = {
    "000779": "建筑装饰",   # 甘咨询
    "600288": "计算机",     # 大恒科技
    "603137": "建筑装饰",   # 恒尚节能
    "688722": "电子",        # 同益中
    "300918": "纺织服饰",   # 南山智尚
    "688101": "基础化工",   # 三达膜
    "301367": "机械设备",   # 瑞迈特
    "002414": "国防军工",   # 高德红外
    "002144": "纺织服饰",   # 宏达高科
    "600718": "计算机",     # 东软集团
    "002841": "电子",        # 视源股份
}
# P6: 单行业最多入选数量（超出按综合强度分降序保留前 N）
MAX_PER_INDUSTRY = 2

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

def metrics(day, q, pool_hyzaf=None):
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
    # P5: 板块 RPS 分位打分（替代原强/中/弱三档粗分）
    # 用池内 hyzaf（板块当日涨跌幅）做分位排名：排名前1/3→15、中1/3→9、后1/3→3
    if pool_hyzaf is not None and len(pool_hyzaf) >= 3:
        srt = sorted(pool_hyzaf)
        n = len(srt)
        idx = srt.index(hz) if hz in srt else 0
        rank_frac = idx / (n - 1) if n > 1 else 0.0
        if rank_frac <= 1/3:   sector = "strong"   # 前1/3：行业内相对强度高
        elif rank_frac <= 2/3: sector = "mid"
        else:                 sector = "weak"
    else:
        # 无池信息时退化到绝对值阈值（保持向后兼容）
        if hz >= 1.0: sector = "strong"
        elif hz >= 0.0: sector = "mid"
        else: sector = "weak"
    return dict(ma20="up" if ma20_up else "down", priceMa="above" if price_above else "below",
                ma60="up" if ma60_up else "down", rsi=round(r, 1), atr=round(a, 2),
                vol=vol, struct=struct, sector=sector)

# ---------- 评分引擎（P1-P4 改进版，严格与 stock-selection-system.html scoreCandidate 同步） ----------
def board_params(board):
    # 双规则：主板/创业板共用（relax=1.5）；科创板独立一套（止损5%/止盈15%/K_ATR=2.5）
    if board in ("main", "cyb"):
        return dict(loss=2.0, profit=6.0, k_atr=1.5)
    return dict(loss=5.0, profit=15.0, k_atr=2.5)  # kcb 科创板独立规则

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

    # ---- P7: MA60 硬约束（趋势根基）----
    if c["ma60"] != "up":
        return (0, 0, 0, board_params(c["board"]), reasons,
                f"P7硬拒: MA60={c['ma60']} 未向上，中长期趋势根基不稳，不参与评分")

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
        # 无池信息时退化到连续衰减（阈值 = k_atr × 止损，科创板更宽容）
        fit = max(0, round(10 * max(0, 1 - c["atr"] / (bp["loss"] * bp["k_atr"]))))
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

# P5: 池内 hyzaf 列表（板块当日涨跌幅），供 metrics 做 RPS 分位
pool_hyzaf = [QUOTES.get(code, {}).get("hyzaf", 0.0) for code, _ in raw_metrics]

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

    m = metrics(day_t, q, pool_hyzaf=pool_hyzaf)
    entry = round(final_close, 2)
    c = dict(board=board, ma20=m["ma20"], priceMa=m["priceMa"], ma60=m["ma60"],
             rsi=m["rsi"], vol=m["vol"], struct=m["struct"], sector=m["sector"],
             atr=m["atr"])
    # P3: 注入同日涨幅
    c["pct"] = q.get("pct", 0)
    # P6: 行业归属（静态映射，生产接真实行业）
    c["industry"] = INDUSTRY_OF.get(code, "其他")

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
               pct=c.get("pct",0), industry=c.get("industry","其他"),
               day=day_t, min5=min5_t)
    all_rows.append(row)

# 排序：综合强度分降序，同分综合分降序
all_rows.sort(key=lambda x: (-x["strength"], -x["total"]))

# P6: 行业上限裁决——先取所有 pass_ 候选，按综合强度分降序，
# 对每个行业计数，超过 MAX_PER_INDUSTRY 的降级为"观察"(进 watch_items，不进 final_items)
watch_items = []
industry_count = {}
for r in all_rows:
    if not r["pass_"]:
        continue
    ind = r["industry"]
    cnt = industry_count.get(ind, 0)
    item = dict(name=r["name"], code=r["code"], setcode=setcode_of(r["code"]), board=r["board"],
                ma20=r["m"]["ma20"], priceMa=r["m"]["priceMa"], ma60=r["m"]["ma60"], rsi=r["m"]["rsi"],
                vol=r["m"]["vol"], struct=r["m"]["struct"], sector=r["m"]["sector"], atr=r["m"]["atr"],
                score=r["total"], win=r["strength"],
                category="final", date=DATA_DATE,
                stopPrice=r["stop"], targetPrice=r["target"],
                kline=dict(day=r["day"], min5=r["min5"]))
    if cnt < MAX_PER_INDUSTRY:
        final_items.append(item)
        industry_count[ind] = cnt + 1
    else:
        # 超行业上限 → 降级为观察
        item["category"] = "watch"
        watch_items.append(item)

final_items.sort(key=lambda x: -x["win"])
watch_items.sort(key=lambda x: -x["win"])

print("=== 全候选 6 维评分（P1-P7 改进版，11 只，按综合强度分降序）===")
print(f"{'code':6} {'name':8} {'indu':8} {'board':4} {'ma20':4} {'pMA':5} {'ma60':4} {'rsi':5} {'atr%':6} {'pct%':5} {'struct':9} {'vol':6} {'sector':6} {'fit':3} {'tot':3} {'str%':5} {'pass':4} {'reject'}")
for r in all_rows:
    m = r["m"]
    rej = r["reject_reason"][:18] if r["rejected"] else ""
    print(f"{r['code']:6} {r['q']['name']:8} {r['industry']:8} {r['board']:4} {m['ma20']:4} {m['priceMa']:5} {m['ma60']:4} {m['rsi']:<5} {m['atr']:<6} {r['pct']:<5.1f} {m['struct']:9} {m['vol']:6} {m['sector']:6} {r['fit']:<3} {r['total']:<3} {r['strength']:<5} {'Y' if r['pass_'] else 'N':<4} {rej}")

rejected_count = sum(1 for r in all_rows if r["rejected"])
print(f"\nP3/P4/P7 硬拒绝: {rejected_count} 只")
print(f"达标数(综合强度分>=70 且过行业上限): {len(final_items)} / 候选 {len(all_rows)}")
print(f"观察数(超行业上限降级): {len(watch_items)} 只 -> " + ", ".join(f"{w['name']}({w['industry']})" for w in watch_items))

# ---------- P8：walk-forward 标定回填 ----------
# 读取 backtest_walkforward.py 产出的 perStock 多笔真实胜率，
# 替代"全池平均"粗暴标定，使面板"成功概率(回测标定)"基于每票自身样本。
WF_CALIB = os.path.join(BASE, "选股结果", "walkforward_calib.json")
wf_per = {}
if os.path.exists(WF_CALIB):
    try:
        _wf = json.load(open(WF_CALIB, encoding="utf-8"))
        for p in _wf.get("calibration", {}).get("perStock", []):
            wf_per[p["code"]] = p.get("realized")
        print(f"[P8] 载入 walk-forward 标定: {len(wf_per)} 只（perStock 多笔真实胜率）")
    except Exception as e:
        print(f"[P8] 标定载入失败，回退公式分: {e}")

# 用 walk-forward 真实胜率覆盖 win 字段（保留 score=原始总分作达标门槛）
for _bucket in (final_items, watch_items):
    for _it in _bucket:
        _code = _it["code"]
        if _code in wf_per:
            _it["win"] = round(wf_per[_code] * 100, 1)   # 真实胜率(%)
            _it["winSource"] = "walkforward"
        else:
            _it["win"] = round(_it.get("score", 0), 1)     # 无回测样本→回退综合强度分
            _it["winSource"] = "formula"

# ---------- 写 import_final.json ----------
updated = datetime.datetime.now().astimezone().isoformat()
out = dict(updated=updated, items=final_items, watch=watch_items)
json.dump(out, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False)
print("wrote", OUT_JSON, "final=", len(final_items), "watch=", len(watch_items), "size~", os.path.getsize(OUT_JSON)//1024, "KB")

# 把全量明细存一份供生成 MD 用
json.dump(dict(all_rows=[{k:v for k,v in r.items() if k not in ('day','min5')} for r in all_rows],
               final_count=len(final_items), rejected_count=rejected_count, updated=updated),
          open(os.path.join(BASE, "_final_summary.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("wrote _final_summary.json")
