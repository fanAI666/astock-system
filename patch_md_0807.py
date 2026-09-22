# -*- coding: utf-8 -*-
"""为盘后定稿 MD 补：大盘实况(含5日/20日趋势) + 存量持仓破位警示。

⭐ 2026-08-07 重构：此前版本把「指数收盘/当日涨跌幅」与「资金主线/风格」叙述**硬编码**成前一日数值，
   每日派生时极易漏改并把陈旧数据发布到站点。现全部改为从 选股结果/fundflow.json 动态读取，
   次日派生只需改 DATE 一处。
"""
import json, os, urllib.request

RES = r"D:/WorkBuddy/选股结果"
DATE = "2026-08-07"
MD = os.path.join(RES, DATE + ".md")

blob = json.load(open(os.path.join(RES, "import_final.json"), encoding="utf-8"))
items = blob["items"]
ff = json.load(open(os.path.join(RES, "fundflow.json"), encoding="utf-8"))

# ---- 存量持仓破位：当日收盘 < 签发止损价 ----
broken = []
for it in items:
    day = (it.get("kline") or {}).get("day") or []
    if not day or day[-1][0] != DATE:
        continue
    close = float(day[-1][2])
    sp = it.get("stopPrice")
    if sp and close < float(sp):
        prev = float(day[-2][2]) if len(day) > 1 else close
        pct = (close - prev) / prev * 100 if prev else 0.0
        broken.append((it.get("name", ""), it.get("date", ""), close, float(sp),
                       (close / float(sp) - 1) * 100, pct))
broken.sort(key=lambda x: x[4])

# ---- 指数 5日/20日 趋势：腾讯公开端点（与系统同源）----
# 注意：web.ifzq.gtimg.cn 盘后可能滞后1日，故校验末棒日期；不符则用 fundflow 当日收盘补齐再算。
def idx_trend(code, today_close):
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,2026-05-01,{DATE},320,qfq"
    try:
        txt = urllib.request.urlopen(url, timeout=15).read().decode("utf-8")
        d = json.loads(txt)
        node = d["data"][code]
        kl = node.get("qfqday") or node.get("day") or []
        if len(kl) < 22:
            return None
        closes = [float(b[2]) for b in kl]
        dates = [str(b[0]) for b in kl]
        if dates[-1] != DATE and today_close:      # 端点滞后1日 → 追加当日收盘
            closes.append(float(today_close))
        elif today_close:                           # 已含当日 → 用权威值覆盖
            closes[-1] = float(today_close)
        last = closes[-1]
        d5 = closes[-6]
        d20 = closes[-21]
        return round((last / d5 - 1) * 100, 2), round((last / d20 - 1) * 100, 2)
    except Exception as e:
        print("  idx fetch err", code, e)
        return None

# ---- 指数：动态取自 fundflow.json（腾讯实时源，权威当日值）----
CODE_MAP = {"上证指数": "sh000001", "深证成指": "sz399001", "创业板指": "sz399006"}
idx_rows, idx_pcts = [], {}
for e in ff.get("indices", []):
    name = e.get("name"); val = e.get("val"); pct = e.get("pct")
    idx_pcts[name] = pct
    t = idx_trend(CODE_MAP.get(name, ""), val) if name in CODE_MAP else None
    d5 = f"{t[0]:+.2f}%" if t else "—"
    d20 = f"{t[1]:+.2f}%" if t else "—"
    idx_rows.append(f"| {name} | {val} | {pct:+.2f}% | {d5} | {d20} |")

# ---- 大盘定性（动态）----
pv = list(idx_pcts.values())
if pv and all(p > 0 for p in pv):
    tone = "三大指数全线收涨"
elif pv and all(p < 0 for p in pv):
    tone = "三大指数全线收跌"
else:
    tone = "三大指数涨跌分化"
trig = [n for n, p in idx_pcts.items() if p <= -2.0]
step8 = (f"**⚠️ {('、'.join(trig))} 跌幅超2%，触发 Step-8 收缩警示，建议暂停新增仓位**"
         if trig else "**未触发 Step-8「单指数跌超2%」收缩警示**")

# ---- 资金主线（动态，取自 fundflow.json）----
hot = sorted([s for s in ff.get("heatSectors", []) if s.get("pct") is not None],
             key=lambda x: -x["pct"])[:3]
flows = [f for f in ff.get("fundFlow", []) if f.get("net") is not None]
inflow = sorted(flows, key=lambda x: -x["net"])[:3]
# 数据源 fundFlow 多数情况下只给「净流入 Top-N」，故净流出须显式过滤 net<0，
# 否则会把最小的正值误标成「净流出」（2026-08-07 曾出现此错）。
outflow = [f for f in sorted(flows, key=lambda x: x["net"])[:3] if f["net"] < 0]
hot_s = "、".join(f"{s['name']}({s['pct']:+.2f}%)" for s in hot) or "—"
in_s = "、".join(f"{f['sector']}({f['net']:+.1f}亿)" for f in inflow) or "—"
out_s = ("；净流出居前 " + "、".join(f"{f['sector']}({f['net']:+.1f}亿)" for f in outflow)
         ) if outflow else "；数据源本日仅提供净流入榜（无净流出行业明细）"

sf = ff.get("styleFactors", [])
up_s = "、".join(f"{s['name']}({s['score']})↑" for s in sf if s.get("up")) or "—"
dn_s = "、".join(f"{s['name']}({s['score']})↓" for s in sf if not s.get("up")) or "—"

# ---- 达标清单特征（动态）----
today = [i for i in items if i.get("date") == DATE]
n_strong = sum(1 for i in today if i.get("sector") == "strong")
n_pull = sum(1 for i in today if i.get("struct") == "pullback")
feat = (f"本日达标 {len(today)} 只中，{n_strong} 只属强势板块、{n_pull} 只为回踩结构")

market = f"""
## 四、大盘实况（{DATE} 收盘）

| 指数 | 收盘 | 当日 | 5日 | 20日 |
| --- | --- | --- | --- | --- |
{chr(10).join(idx_rows)}

- {tone}，{step8}；20日维度多数指数仍处下行通道，中期节奏建议半仓内。
- **资金主线（申万一级 + 东财行业资金）**：涨幅居前 {hot_s}；主力净流入居前 {in_s}{out_s}。北向当日净额接口盘后归零，不纳入判断。
- **风格**：{up_s} 走强；{dn_s} 偏弱。
- **⚠️ 追高剔除说明**：当日主力净流入榜前列多被涨停/追高标的占据，这些标的被「涨停/追高（当日涨幅>9.5%）」或「主板回踩带（须价在MA20上方且收盘≤MA20×1.05）」硬规则剔除。{feat}。追主线需自行承担追高风险，本系统按纪律不追。
"""

lines = ["", "## 五、存量持仓破位警示（收盘价已跌破签发止损价）", ""]
if broken:
    lines.append("| 名称/代码 | 签发日 | 收盘价 | 止损价 | 偏离 | 当日涨跌 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for n, d, c, s, dev, pct in broken:
        lines.append(f"| {n} | {d} | {c} | {s} | {dev:+.1f}% | {pct:+.2f}% |")
    lines.append("")
    lines.append(f"- 共 **{len(broken)}** 只存量标的收盘价低于当初签发的止损价，若已按信号建仓应按纪律止损/减仓，勿扛单。")
else:
    lines.append("- 本日无存量标的跌破签发止损价。")
lines.append("")

md = open(MD, encoding="utf-8").read()
if "## 四、风险提示" not in md:
    raise SystemExit("MD 未含『## 四、风险提示』锚点——可能已被 patch 过，请先重跑 build 脚本重建 MD。")
md = md.replace("## 四、风险提示", market.strip() + "\n" + "\n".join(lines) + "\n## 六、风险提示")
open(MD, "w", encoding="utf-8").write(md)

print(f"MD 已补充：破位 {len(broken)} 只")
print(f"  指数(动态): " + " | ".join(f"{n}{p:+.2f}%" for n, p in idx_pcts.items()))
print(f"  热点: {hot_s}")
print(f"  净流入: {in_s}")
for b in broken[:20]:
    print(f"  {b[0]:16} 收{b[2]:>9} < 止损{b[3]:>9}  {b[4]:+.1f}%  当日{b[5]:+.2f}%")
