# -*- coding: utf-8 -*-
"""
东方财富行业接口 2026-08-14 盘后再次被阻断（sectors=0），改用腾讯自选股 westock data_sector(mode=ranking, scope=sw1)
的申万一级板块涨跌幅 + 主力净流入补齐 fundflow.json 的 heatSectors / fundFlow / fundThread / recommendations。
指数与风格因子仍来自 fetch_fundflow.py 原始腾讯源，不改动。
单位换算：westock zljlr 单位为万元 -> 亿元 = /10000。
派生自 patch_fundflow_0806.py，叙述已全动态（不硬编码行业名/数值）。
"""
import json, os, datetime

RES = r"D:/WorkBuddy/选股结果"
OUT = os.path.join(RES, "fundflow.json")

# (名称, 当日涨跌幅%, 主力净流入万元 或 None, 流入万元, 流出万元)
# 数据源：westock data_sector(mode=ranking, scope=sw1, date=2026-08-14)
SW1 = [
    ("玻璃玻纤",       4.31, None, None, None),
    ("通信设备",       3.63, 1221878.45, 8920578.92, 7698700.47),
    ("电子化学品Ⅱ",    3.44, None, None, None),
    ("小金属",         3.04, 157319.37, 1868857.03, 1711537.66),
    ("非金属材料Ⅱ",    3.01, None, None, None),
    ("游戏Ⅱ",          2.81, None, None, None),
    ("综合Ⅱ",          2.39, None, None, None),
    ("通信服务",       2.33, 206214.23, 929738.48, 723524.25),
    ("煤炭开采",       1.62, None, None, None),
    ("元件",           1.51, None, None, None),
    ("黑色家电",       1.46, None, None, None),
    ("照明设备Ⅱ",      1.34, None, None, None),
    ("半导体",         1.08, -547539.03, 13794290.29, 14341829.32),
    ("装修装饰Ⅱ",      0.61, None, None, None),
    ("贵金属",         0.52, None, None, None),
    ("医药商业",       0.36, None, None, None),
    ("航海装备Ⅱ",      0.02, None, None, None),
    ("地面兵装Ⅱ",     -0.13, None, None, None),
    ("计算机设备",    -0.44, None, None, None),
    ("休闲食品",      -0.81, None, None, None),
    ("教育",          -0.85, None, None, None),
    ("数字媒体",      -0.92, None, None, None),
    ("工程咨询服务Ⅱ", -1.13, None, None, None),
    ("医疗服务",      -1.18, None, None, None),
    ("证券Ⅱ",         -1.40, -308611.42, 902985.17, 1211596.59),
    ("房地产服务",    -1.45, None, None, None),
    ("电力",          -1.82, -469167.49, 1445363.90, 1914531.39),
    ("广告营销",      -2.05, None, None, None),
    ("化妆品",        -2.14, None, None, None),
    ("影视院线",      -2.71, None, None, None),
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
ft = "今日盘面：%s。资金主攻方向为 %s" % (
    idx_txt, "、".join("%s(%s%%)" % (s["name"], fmt_pct(s["pct"])) for s in pos[:3]))
if len(inflows) >= 2:
    ft += "；主力净流入居前：%s(+%s亿)、%s(+%s亿)" % (
        inflows[0]["name"], inflows[0]["net"], inflows[1]["name"], inflows[1]["net"])
elif inflows:
    ft += "；主力净流入居前：%s(+%s亿)" % (inflows[0]["name"], inflows[0]["net"])
if outflows:
    ft += "；净流出居前：%s(%s亿)" % (outflows[-1]["name"], outflows[-1]["net"])
ft += "。北向当日净额接口归零（盘后），东方财富行业接口当日被阻断，已用 westock 申万一级数据替代。"
d["fundThread"] = ft

recs = []
t = pos[0]
recs.append({"tag": "加仓方向", "cls": "buy", "title": "%s领涨为当日最强主线" % t["name"],
             "reason": "%s涨%s%%，居申万一级首位；%s 亦同步走强(%s%%)。资金主线明确，但注意多数强势标的当日已追高，宜等回踩不追板。"
                       % (t["name"], fmt_pct(t["pct"]), pos[1]["name"], fmt_pct(pos[1]["pct"]))})
if inflows:
    t = inflows[0]
    recs.append({"tag": "加仓方向", "cls": "buy", "title": "%s主力资金净流入居前" % t["name"],
                 "reason": "%s涨%s%%、主力净流入%s亿（流入%s亿/流出%s亿），为当日真实增量资金方向，可在回踩确认后配置板块龙头。"
                           % (t["name"], fmt_pct(t["pct"]), t["net"], t["inflow"], t["outflow"])})
if outflows:
    t = outflows[-1]
    recs.append({"tag": "谨慎规避", "cls": "sell", "title": "%s资金持续流出" % t["name"],
                 "reason": "%s跌%s%%、主力净流出%s亿，为当日净流出之首，资金外流未止，建议低配或回避。"
                           % (t["name"], fmt_pct(t["pct"]), abs(t["net"]))})
t = neg[0]
recs.append({"tag": "谨慎规避", "cls": "sell", "title": "%s跌幅居前" % t["name"],
             "reason": "%s跌%s%%、%s跌%s%%，为当日跌幅前二，短线情绪偏弱，不宜逆势介入。"
                       % (t["name"], fmt_pct(t["pct"]), neg[1]["name"], fmt_pct(neg[1]["pct"]))})
d["recommendations"] = recs

d["source"] = "腾讯行情(指数/风格) + 腾讯自选股 westock data_sector(申万一级行业涨跌幅/主力净流入)，盘后抓取；东方财富接口当日被阻断已降级替代"
d["updatedAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("fundflow.json 已补齐: indices=%d style=%d heatSectors=%d fundFlow=%d recs=%d" % (
    len(d.get("indices", [])), len(d.get("styleFactors", [])),
    len(d["heatSectors"]), len(d["fundFlow"]), len(d["recommendations"])))
print("fundThread:", d["fundThread"])
