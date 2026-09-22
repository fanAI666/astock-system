# -*- coding: utf-8 -*-
"""为 2026-08-04 盘后定稿 MD 补：大盘实况 + 存量持仓破位警示。"""
import json, os

RES = r"D:/WorkBuddy/选股结果"
DATE = "2026-08-04"
MD = os.path.join(RES, DATE + ".md")

blob = json.load(open(os.path.join(RES, "import_final.json"), encoding="utf-8"))
items = blob["items"]

broken = []
for it in items:
    day = (it.get("kline") or {}).get("day") or []
    if not day:
        continue
    if day[-1][0] != DATE:
        continue
    close = float(day[-1][2])
    sp = it.get("stopPrice")
    if sp and close < float(sp):
        prev = float(day[-2][2]) if len(day) > 1 else close
        pct = (close - prev) / prev * 100 if prev else 0.0
        broken.append((it["name"], it.get("date", ""), close, float(sp),
                       (close / float(sp) - 1) * 100, pct))
broken.sort(key=lambda x: x[4])

md = open(MD, encoding="utf-8").read()

market = """
## 四、大盘实况（2026-08-04 收盘）

| 指数 | 收盘 | 当日 | 5日 | 20日 |
| --- | --- | --- | --- | --- |
| 上证指数 | 3822.28 | +0.33% | +0.24% | -4.21% |
| 深证成指 | 13885.71 | +3.25% | +2.78% | -8.80% |
| 创业板指 | 3488.97 | +5.64% | +4.87% | -10.81% |

- 未触发 Step-8「跌超2%」收缩警示；今日为 AI 算力/光模块/PCB 主线强势普涨日（创业板指 +5.64%）。
- **风格背离提示**：主力净流入前列几乎全为光模块/CPO/半导体（中际旭创 +13.2%、新易盛 +13.7%、天孚通信 +17.5%、光库科技 +20%），但这些标的因「涨停/追高（当日涨幅>9.5%）」或「主板回踩带」硬规则被系统剔除；本日达标清单反而集中在回踩型防御标的（银行/医药/高股息），与当日热点主线方向相反。追主线需自行承担追高风险，本系统不追。
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

md = md.replace("## 四、风险提示", market.strip() + "\n" + "\n".join(lines) + "\n## 六、风险提示")
open(MD, "w", encoding="utf-8").write(md)
print(f"MD 已补充：破位 {len(broken)} 只")
for b in broken[:20]:
    print(f"  {b[0]:16} 收{b[2]:>9} < 止损{b[3]:>9}  {b[4]:+.1f}%  当日{b[5]:+.2f}%")
