# -*- coding: utf-8 -*-
"""为 2026-08-06 盘后定稿 MD 补：大盘实况(含5日/20日趋势) + 存量持仓破位警示。"""
import json, os, urllib.request

RES = r"D:/WorkBuddy/选股结果"
DATE = "2026-08-06"
MD = os.path.join(RES, DATE + ".md")

blob = json.load(open(os.path.join(RES, "import_final.json"), encoding="utf-8"))
items = blob["items"]

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
def idx_trend(code):
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,2026-06-01,{DATE},320,qfq"
    try:
        txt = urllib.request.urlopen(url, timeout=15).read().decode("utf-8")
        d = json.loads(txt)
        node = d["data"][code]
        kl = node.get("qfqday") or node.get("day") or []
        if len(kl) < 21:
            return None
        last = float(kl[-1][2])
        d5 = float(kl[-6][2]) if len(kl) >= 6 else float(kl[0][2])
        d20 = float(kl[-21][2])
        return round((last / d5 - 1) * 100, 2), round((last / d20 - 1) * 100, 2)
    except Exception as e:
        print("  idx fetch err", code, e)
        return None

idx = {
    "上证指数": ("sh000001", 3900.35, 0.57),
    "深证成指": ("sz399001", 14110.12, -0.24),
    "创业板指": ("sz399006", 3515.56, -0.55),
}
rows = []
for name, (code, val, pct) in idx.items():
    t = idx_trend(code)
    d5 = f"{t[0]:+.2f}%" if t else "—"
    d20 = f"{t[1]:+.2f}%" if t else "—"
    rows.append(f"| {name} | {val} | {pct:+.2f}% | {d5} | {d20} |")

market = f"""
## 四、大盘实况（{DATE} 收盘）

| 指数 | 收盘 | 当日 | 5日 | 20日 |
| --- | --- | --- | --- | --- |
{chr(10).join(rows)}

- 三大指数分化收官，**上证微涨、深证/创业板小幅收跌，未触发 Step-8「单指数跌超2%」收缩警示**；20日维度创业板指仍处下行通道，中期节奏建议半仓内。
- **资金主线（申万一级·腾讯自选股 westock）**：涨幅居前 电子化学品Ⅱ(+4.73%)、煤炭开采(+4.56%)、玻璃玻纤(+3.85%)；主力净流入居前 通信设备(+25.93亿)、元件(+19.12亿)、电子化学品Ⅱ(+16.13亿)；净流出居前 软件开发(-39.99亿)、电池(-34.94亿)、证券Ⅱ(-34.51亿)。北向当日净额接口盘后归零，不纳入判断。
- **风格**：大盘价值(51)↑、小盘成长(51)↑ 走平偏强，大盘成长(48)↓、小盘价值(46)↓ 偏弱 —— 资金偏向低估值/小盘弹性，与达标清单防御回踩特征吻合。
- **⚠️ 风格背离提示**：当日主力净流入榜前列多被涨停/追高标的占据（通信设备、元件、电子化学品产业链），这些标的被「涨停/追高（当日涨幅>9.5%）」或「主板回踩带」硬规则全数剔除；本日达标清单集中在回踩型防御标的（银行/高股息/医药/消费），与当日热点主线方向相反。追主线需自行承担追高风险，本系统按纪律不追。
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
md = md.replace("## 四、风险提示", market.strip() + "\n" + "\n".join(lines) + "\n## 六、风险提示")
open(MD, "w", encoding="utf-8").write(md)
print(f"MD 已补充：破位 {len(broken)} 只")
for b in broken[:20]:
    print(f"  {b[0]:16} 收{b[2]:>9} < 止损{b[3]:>9}  {b[4]:+.1f}%  当日{b[5]:+.2f}%")
