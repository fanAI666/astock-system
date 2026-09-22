# -*- coding: utf-8 -*-
"""
东方财富行业接口 2026-08-19 盘后再次被阻断（sectors=0），改用腾讯自选股 westock data_sector(mode=ranking, scope=sw1)
的申万行业涨跌幅 + 主力净流入补齐 fundflow.json 的 heatSectors / fundFlow / fundThread / recommendations。
指数与风格因子仍来自 fetch_fundflow.py 原始腾讯源，不改动。
单位换算：westock zljlr 单位为万元 -> 亿元 = /10000。
派生自 patch_fundflow_0814.py；新增：任一指数跌超2%时在 recommendations 首位插入 Step-8 系统性风险条目。
"""
import json, os, datetime

RES = r"D:/WorkBuddy/选股结果"
OUT = os.path.join(RES, "fundflow.json")

# (名称, 当日涨跌幅%, 主力净流入万元 或 None, 流入万元, 流出万元)
# 数据源：westock data_sector(mode=ranking, scope=sw1, date=2026-08-19)
SW1 = [
    ("焦炭Ⅱ",          7.56,   68911.82,  138916.62,   70004.80),
    ("厨卫电器",        4.56, None, None, None),
    ("炼化及贸易",      2.08, None, None, None),
    ("股份制银行Ⅱ",     1.91, None, None, None),
    ("城商行Ⅱ",         1.80, None, None, None),
    ("国有大型银行Ⅱ",   1.70, None, None, None),
    ("白色家电",        1.63, None, None, None),
    ("房地产服务",      1.34, None, None, None),
    ("航运港口",        1.11,   59461.58,  474277.79,  414816.21),
    ("保险Ⅱ",           1.08, None, None, None),
    ("贵金属",          0.68, None, None, None),
    ("煤炭开采",        0.32, None, None, None),
    ("白酒Ⅱ",          -0.17, None, None, None),
    ("饮料乳品",       -0.29, None, None, None),
    ("农产品加工",     -1.54, None, None, None),
    ("商用车",         -1.57, None, None, None),
    ("种植业",         -1.80, None, None, None),
    ("动物保健Ⅱ",      -2.46, None, None, None),
    ("饲料",           -2.81, None, None, None),
    ("教育",           -3.18, None, None, None),
    ("医疗服务",       -3.33, None, None, None),
    ("风电设备",       -3.35,   60182.66,  719963.13,  659780.47),
    ("渔业",           -4.00, None, None, None),
    ("工程咨询服务Ⅱ",  -4.98, None, None, None),
    ("装修装饰Ⅱ",      -5.20, None, None, None),
    ("航天装备Ⅱ",      -5.83, None, None, None),
    ("半导体",         -7.57, -3554534.45, 18744661.02, 22299195.47),
    ("通信设备",       -8.66, -2557987.90,  7718028.21, 10276016.11),
    ("玻璃玻纤",       -8.96, None, None, None),
    ("元件",           -9.04, -1682606.22,  4902440.08,  6585046.30),
    ("电子化学品Ⅱ",    -9.07, None, None, None),
]

W2Y = lambda v: round(v / 10000.0, 2) if v is not None else None

d = json.load(open(OUT, encoding="utf-8"))
indices = d.get("indices", [])

sectors = []
for name, pct, net, inf, outf in SW1:
    sectors.append({"name": name, "pct": pct, "net": W2Y(net),
                    "inflow": W2Y(inf), "outflow": W2Y(outf)})

d["heatSectors"] = [{"name": s["name"], "pct": s["pct"]} for s in sectors]
withnet = [s for s in sectors if s["net"] is not None]
d["fundFlow"] = [{"sector": s["name"], "net": s["net"], "inflow": s["inflow"], "outflow": s["outflow"]}
                 for s in sorted(withnet, key=lambda x: -x["net"])]

pos = sorted([s for s in sectors if s["pct"] > 0], key=lambda x: -x["pct"])
neg = sorted([s for s in sectors if s["pct"] < 0], key=lambda x: x["pct"])
topnet = sorted(withnet, key=lambda x: -x["net"])
inflows = [s for s in topnet if s["net"] > 0]
outflows = [s for s in topnet if s["net"] < 0]

fmt_pct = lambda v: ("+" if v >= 0 else "") + str(v)

idx_txt = "、".join("%s%s%%" % (i["name"].replace("指数", ""), fmt_pct(i["pct"])) for i in indices)
down2 = [i for i in indices if i["pct"] <= -2]
ft = "今日盘面：%s。" % idx_txt
if down2:
    ft += "⚠️ %s 跌超2%%，系统性回调，触发收缩/暂停新增。" % "、".join(i["name"].replace("指数", "") for i in down2)
ft += "逆势抗跌方向为 %s" % "、".join("%s(%s%%)" % (s["name"], fmt_pct(s["pct"])) for s in pos[:3])
if len(inflows) >= 2:
    ft += "；主力净流入居前：%s(+%s亿)、%s(+%s亿)" % (
        inflows[0]["name"], inflows[0]["net"], inflows[1]["name"], inflows[1]["net"])
elif inflows:
    ft += "；主力净流入居前：%s(+%s亿)" % (inflows[0]["name"], inflows[0]["net"])
if outflows:
    ft += "；净流出居前：%s(%s亿)" % (outflows[-1]["name"], outflows[-1]["net"])
ft += "。北向当日净额接口归零（盘后），东方财富行业接口当日被阻断，已用 westock 申万行业数据替代。"
d["fundThread"] = ft

recs = []
# Step-8 系统性风险优先
if down2:
    worst = min(indices, key=lambda x: x["pct"])
    recs.append({"tag": "系统性风险", "cls": "sell",
                 "title": "%s跌%s%%，触发收缩/暂停新增" % (worst["name"].replace("指数", ""), fmt_pct(worst["pct"])),
                 "reason": "%s 均跌超2%%，属系统性回调而非个股问题。按风控基线应暂停或大幅收缩新开仓，已持仓严格执行止损纪律，等指数企稳（收复5日线且量能回升）再考虑加仓。"
                           % "、".join(i["name"].replace("指数", "") + fmt_pct(i["pct"]) + "%" for i in down2)})
if pos:
    t = pos[0]
    recs.append({"tag": "防御方向", "cls": "buy", "title": "%s逆势领涨为当日最强主线" % t["name"],
                 "reason": "%s涨%s%%，居申万行业首位；%s 亦逆势走强(%s%%)。暴跌日的抗跌方向通常是资金避险去处，但普跌市中不宜重仓追涨，宜小仓试探或等指数稳住。"
                           % (t["name"], fmt_pct(t["pct"]), pos[1]["name"], fmt_pct(pos[1]["pct"]))})
if inflows:
    t = inflows[0]
    recs.append({"tag": "资金流向", "cls": "buy", "title": "%s主力资金净流入居前" % t["name"],
                 "reason": "%s涨%s%%、主力净流入%s亿（流入%s亿/流出%s亿），为当日为数不多的真实增量资金方向，可列入观察，待大盘止跌后回踩确认再配置。"
                           % (t["name"], fmt_pct(t["pct"]), t["net"], t["inflow"], t["outflow"])})
if outflows:
    t = outflows[-1]
    recs.append({"tag": "谨慎规避", "cls": "sell", "title": "%s资金大幅出逃" % t["name"],
                 "reason": "%s跌%s%%、主力净流出%s亿，为当日净流出之首，机构筹码持续松动，短期不宜逆势抄底。"
                           % (t["name"], fmt_pct(t["pct"]), abs(t["net"]))})
if len(neg) >= 2:
    t = neg[0]
    recs.append({"tag": "谨慎规避", "cls": "sell", "title": "%s跌幅居前" % t["name"],
                 "reason": "%s跌%s%%、%s跌%s%%，为当日跌幅前二（科技/成长链条集体重挫），情绪极弱，不宜逆势介入。"
                           % (t["name"], fmt_pct(t["pct"]), neg[1]["name"], fmt_pct(neg[1]["pct"]))})
d["recommendations"] = recs

d["source"] = "腾讯行情(指数/风格) + 腾讯自选股 westock data_sector(申万行业涨跌幅/主力净流入)，盘后抓取；东方财富接口当日被阻断已降级替代"
d["updatedAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("fundflow.json 已补齐: indices=%d style=%d heatSectors=%d fundFlow=%d recs=%d" % (
    len(d.get("indices", [])), len(d.get("styleFactors", [])),
    len(d["heatSectors"]), len(d["fundFlow"]), len(d["recommendations"])))
print("fundThread:", d["fundThread"])
