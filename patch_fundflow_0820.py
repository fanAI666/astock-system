# -*- coding: utf-8 -*-
"""
东方财富行业接口 2026-08-20 盘后再次被阻断（sectors=0），改用腾讯自选股 westock data_sector
(mode=ranking, scope=sw1) 的申万行业涨跌幅 + 主力净流入补齐 fundflow.json 的
heatSectors / fundFlow / fundThread / recommendations。
指数与风格因子仍来自 fetch_fundflow.py 原始腾讯源，不改动。
单位：westock zljlr/zllr/zllc 单位为万元 -> 亿元 = /10000。
派生自 patch_fundflow_0819.py；08-20 三指均未见跌超2%，故不插入 Step-8 系统性风险条目。
"""
import json, os, datetime

RES = r"D:/WorkBuddy/选股结果"
OUT = os.path.join(RES, "fundflow.json")

# (名称, 当日涨跌幅%, 主力净流入亿元, 主力流入亿元, 主力流出亿元)
# 数据源：westock data_sector(mode=ranking, scope=sw1, date=2026-08-20) 的 fundflow.plate.top/bottom
SW = [
    ("医疗服务",  4.24,  38.72, 273.91, 235.19),
    ("生物制品",  7.85,  33.05, 147.14, 114.08),
    ("化学制药",  2.55,  27.71, 352.20, 324.49),
    ("半导体",   -0.36, -69.98, 1361.86, 1431.84),
    ("电池",      -0.84, -15.60, 163.44, 179.04),
    ("小金属",    -1.08, -15.51, 122.01, 137.51),
]

d = json.load(open(OUT, encoding="utf-8"))
indices = d.get("indices", [])

sectors = [{"name": n, "pct": p} for n, p, *_ in SW]
withnet = [s for s in SW if s[2] is not None]
d["heatSectors"] = sectors
d["fundFlow"] = [{"sector": s[0], "net": s[2], "inflow": s[3], "outflow": s[4]}
                 for s in sorted(withnet, key=lambda x: -x[2])]

pos = sorted([s for s in SW if s[1] > 0], key=lambda x: -x[1])
neg = sorted([s for s in SW if s[1] < 0], key=lambda x: x[1])
topnet = sorted(withnet, key=lambda x: -x[2])
inflows = [s for s in topnet if s[2] > 0]
outflows = [s for s in topnet if s[2] < 0]

fmt_pct = lambda v: ("+" if v >= 0 else "") + str(v)
idx_txt = "、".join("%s%s%%" % (i["name"].replace("指数", ""), fmt_pct(i["pct"])) for i in indices)
ft = "今日盘面：%s。" % idx_txt
ft += "医药链条（医疗服务/生物制品/化学制药）逆势获主力净流入居前，为当日最强资金主线。"
if inflows:
    ft += "；主力净流入居前：%s(+%s亿)、%s(+%s亿)、%s(+%s亿)" % (
        inflows[0][0], inflows[0][2], inflows[1][0], inflows[1][2], inflows[2][0], inflows[2][2])
if outflows:
    ft += "；净流出居前：%s(%s亿)" % (outflows[-1][0], outflows[-1][2])
ft += "。北向当日净额接口归零（盘后），东方财富行业接口当日被阻断，已用 westock 申万行业数据替代。"
d["fundThread"] = ft

recs = []
if pos:
    t = pos[0]
    recs.append({"tag": "防御方向", "cls": "buy", "title": "%s领涨为当日最强主线" % t[0],
                 "reason": "%s涨%s%%，居行业首位；%s、%s 亦走强(%s%%/%s%%)。医药链条（医疗服务/生物制品/化学制药）集体获主力净流入，为当日唯一清晰资金主线，可列入观察。"
                           % (t[0], fmt_pct(t[1]), pos[1][0], pos[2][0], fmt_pct(pos[1][1]), fmt_pct(pos[2][1]))})
if inflows:
    t = inflows[0]
    recs.append({"tag": "资金流向", "cls": "buy", "title": "%s主力资金净流入居前" % t[0],
                 "reason": "%s涨%s%%、主力净流入%s亿（流入%s亿/流出%s亿），为当日净流入之首，资金真实介入，可等大盘企稳后回踩确认再配置。"
                           % (t[0], fmt_pct(t[1]), t[2], t[3], t[4])})
if outflows:
    t = outflows[-1]
    recs.append({"tag": "谨慎规避", "cls": "sell", "title": "%s资金大幅出逃" % t[0],
                 "reason": "%s跌%s%%、主力净流出%s亿，为当日净流出之首，机构筹码持续松动，短期不宜逆势抄底。"
                           % (t[0], fmt_pct(t[1]), abs(t[2]))})
if len(neg) >= 2:
    t = neg[0]
    recs.append({"tag": "谨慎规避", "cls": "sell", "title": "%s跌幅居前" % t[0],
                 "reason": "%s跌%s%%、%s跌%s%%，为当日跌幅前二（成长/制造链条承压），情绪偏弱，不宜逆势介入。"
                           % (t[0], fmt_pct(t[1]), neg[1][0], fmt_pct(neg[1][1]))})
d["recommendations"] = recs

d["source"] = "腾讯行情(指数/风格) + 腾讯自选股 westock data_sector(申万行业涨跌幅/主力净流入)，盘后抓取；东方财富接口当日被阻断已降级替代"
d["updatedAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("fundflow.json 已补齐: indices=%d style=%d heatSectors=%d fundFlow=%d recs=%d" % (
    len(d.get("indices", [])), len(d.get("styleFactors", [])),
    len(d["heatSectors"]), len(d["fundFlow"]), len(d["recommendations"])))
print("fundThread:", d["fundThread"])
