# -*- coding: utf-8 -*-
"""
东方财富行业接口 2026-08-06 盘后持续限流（sectors=0），改用腾讯自选股 westock data_sector(ranking, sw1)
的申万一级板块涨跌幅 + 主力净流入补齐 fundflow.json 的 heatSectors / fundFlow / fundThread / recommendations。
指数与风格因子仍来自 fetch_fundflow.py 原始腾讯源，不改动。
单位换算：westock zljlr/zllr/zllc 单位为万元 -> 亿元 = /10000。
"""
import json, os, datetime

RES = r"D:/WorkBuddy/选股结果"
OUT = os.path.join(RES, "fundflow.json")

# (名称, 当日涨跌幅%, 主力净流入万元 或 None, 流入万元, 流出万元)
SW1 = [
    ("电子化学品Ⅱ", 4.73, 161344.86, 2209339.51, 2047994.65),
    ("煤炭开采", 4.56, None, None, None),
    ("玻璃玻纤", 3.85, None, None, None),
    ("非金属材料Ⅱ", 3.19, None, None, None),
    ("小金属", 3.13, None, None, None),
    ("贵金属", 2.78, None, None, None),
    ("元件", 2.33, 191189.34, 6334899.49, 6143710.14),
    ("焦炭Ⅱ", 2.27, None, None, None),
    ("种植业", 1.98, None, None, None),
    ("通信设备", 1.49, 259286.64, 9604856.47, 9345569.83),
    ("半导体", 1.42, None, None, None),
    ("通用设备", 1.16, None, None, None),
    ("渔业", 1.12, None, None, None),
    ("装修装饰Ⅱ", 0.79, None, None, None),
    ("国有大型银行Ⅱ", 0.63, None, None, None),
    ("城商行Ⅱ", 0.39, None, None, None),
    ("股份制银行Ⅱ", 0.21, None, None, None),
    ("工业金属", 0.02, None, None, None),
    ("航海装备Ⅱ", -0.12, None, None, None),
    ("白色家电", -0.24, None, None, None),
    ("软件开发", -0.52, -399872.25, 2586530.67, 2986402.92),
    ("专业连锁Ⅱ", -1.02, None, None, None),
    ("证券Ⅱ", -1.20, -345076.31, 987911.75, 1332988.05),
    ("广告营销", -1.94, None, None, None),
    ("医疗服务", -2.20, None, None, None),
    ("教育", -2.56, None, None, None),
    ("电池", -2.74, -349386.23, 2549467.08, 2898853.31),
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

idx_txt = "、".join(["%s%s%%" % (i["name"].replace("指数", ""),
                                ("+" if i["pct"] >= 0 else "") + str(i["pct"])) for i in indices])
ft = "今日盘面：%s。资金主攻方向为 %s" % (
    idx_txt, "、".join(["%s(+%s%%)" % (s["name"], s["pct"]) for s in pos[:3]]))
if topnet and topnet[0]["net"] > 0:
    ft += "；主力净流入居前：%s(+%s亿)、%s(+%s亿)" % (
        topnet[0]["name"], topnet[0]["net"], topnet[1]["name"], topnet[1]["net"])
if topnet and topnet[-1]["net"] < 0:
    ft += "；净流出居前：%s(%s亿)" % (topnet[-1]["name"], topnet[-1]["net"])
ft += "。北向当日净额接口归零（盘后）。"
d["fundThread"] = ft

recs = []
t = pos[0]
recs.append({"tag": "加仓方向", "cls": "buy", "title": "%s获资金聚焦" % t["name"],
             "reason": "%s涨+%s%%，主力净流入%s亿，半导体材料/电子特气产业链资金主线明确，建议超配板块龙头（注意多数标的当日已追高）。"
                       % (t["name"], t["pct"], t["net"])})
t = neg[0]
recs.append({"tag": "谨慎规避", "cls": "sell", "title": "%s资金持续流出" % t["name"],
             "reason": "%s跌%s%%、主力净流出%s亿，新能源产业链资金外流未止，建议低配或回避。"
                       % (t["name"], t["pct"], abs(t["net"]))})
recs.append({"tag": "谨慎规避", "cls": "sell", "title": "软件开发/证券资金撤离",
             "reason": "软件开发主力净流出39.99亿、证券Ⅱ净流出34.51亿，为当日流出前二，题材与金融权重同步失血，短线不宜介入。"})
recs.append({"tag": "持有观察", "cls": "hold", "title": "银行/高股息方向待明朗",
             "reason": "国有大型银行+0.63%、股份制银行+0.21%、城商行+0.39%，微幅收涨但成交清淡（换手0.2%-0.65%），防御属性仍在，建议持有观察不追。"})
d["recommendations"] = recs

d["source"] = "腾讯行情(指数/风格) + 腾讯自选股 westock data_sector(申万一级行业涨跌幅/主力净流入)，盘后抓取；东方财富接口当日限流已降级替代"
d["updatedAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("fundflow.json 已补齐: heatSectors=%d fundFlow=%d recs=%d" % (
    len(d["heatSectors"]), len(d["fundFlow"]), len(d["recommendations"])))
print("fundThread:", d["fundThread"])
