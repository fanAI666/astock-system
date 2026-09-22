# -*- coding: utf-8 -*-
"""Re-score the existing 合格 pool on 07-30 using embedded day-K-line + 07-30 close overlay.
Read-only on import_final.json. Outputs 选股结果/_rescored_0730.json + console table.
Note: 07-28/29 gap ignored (only last close overlaid with 07-30 quote); MA/RSI/ATR approximate.
"""
import json

P = "选股结果/import_final.json"
data = json.load(open(P, encoding="utf-8"))
items = data["items"]

# 07-30 quotes: code(无前缀) -> {c,pc,o,h,l,v,vr}
Q = {
 "000999":{"c":25.92,"pc":25.47,"o":25.30,"h":26.00,"l":25.30,"v":201877,"vr":1.88},
 "301520":{"c":44.96,"pc":51.80,"o":50.00,"h":54.90,"l":44.85,"v":154162,"vr":0.99},
 "603127":{"c":40.05,"pc":43.94,"o":43.93,"h":44.00,"l":40.00,"v":552894,"vr":0.86},
 "002127":{"c":3.05,"pc":3.07,"o":3.05,"h":3.13,"l":3.03,"v":437265,"vr":0.80},
 "600664":{"c":5.56,"pc":5.36,"o":5.36,"h":5.69,"l":5.20,"v":4015252,"vr":0.81},
 "688621":{"c":56.75,"pc":57.78,"o":56.90,"h":57.50,"l":54.56,"v":2140574,"vr":0.81},
 "300149":{"c":8.60,"pc":8.94,"o":8.88,"h":9.16,"l":8.51,"v":291991,"vr":0.68},
 "000938":{"c":33.60,"pc":37.33,"o":35.00,"h":35.95,"l":33.60,"v":2539454,"vr":0.64},
 "600352":{"c":13.21,"pc":13.55,"o":13.29,"h":13.67,"l":13.04,"v":871491,"vr":1.29},
 "600690":{"c":23.27,"pc":22.98,"o":23.00,"h":23.49,"l":22.90,"v":546421,"vr":1.17},
 "603338":{"c":60.38,"pc":60.48,"o":59.86,"h":61.44,"l":59.44,"v":61486,"vr":0.76},
 "300039":{"c":5.41,"pc":5.59,"o":5.54,"h":5.93,"l":5.40,"v":790076,"vr":1.03},
 "300643":{"c":16.25,"pc":17.98,"o":17.66,"h":17.88,"l":16.11,"v":121815,"vr":0.83},
 "688237":{"c":54.95,"pc":67.90,"o":67.94,"h":67.94,"l":54.67,"v":6533860,"vr":1.15},
 "300779":{"c":72.28,"pc":76.76,"o":75.78,"h":77.40,"l":71.89,"v":179502,"vr":0.78},
 "001258":{"c":12.35,"pc":11.61,"o":11.85,"h":12.46,"l":11.21,"v":1868895,"vr":1.21},
 "605028":{"c":27.07,"pc":26.95,"o":27.49,"h":27.62,"l":26.50,"v":29975,"vr":0.42},
 "000011":{"c":7.99,"pc":7.82,"o":7.79,"h":8.35,"l":7.58,"v":327880,"vr":0.90},
 "002415":{"c":35.62,"pc":35.74,"o":35.59,"h":36.09,"l":35.13,"v":988175,"vr":0.70},
 "002900":{"c":11.56,"pc":11.80,"o":11.99,"h":12.70,"l":11.35,"v":310429,"vr":0.97},
 "001328":{"c":31.83,"pc":32.08,"o":32.08,"h":33.06,"l":31.70,"v":33586,"vr":1.10},
 "002879":{"c":16.14,"pc":17.93,"o":17.52,"h":18.78,"l":16.14,"v":388429,"vr":1.02},
 "301122":{"c":29.17,"pc":30.98,"o":31.02,"h":31.30,"l":29.01,"v":64596,"vr":0.64},
 "600369":{"c":4.17,"pc":4.16,"o":4.14,"h":4.19,"l":4.11,"v":465959,"vr":1.15},
 "000581":{"c":17.92,"pc":17.61,"o":17.60,"h":18.00,"l":17.55,"v":108160,"vr":1.52},
 "002345":{"c":10.70,"pc":10.66,"o":10.67,"h":11.08,"l":10.53,"v":302152,"vr":1.22},
 "300441":{"c":6.85,"pc":6.89,"o":6.94,"h":7.26,"l":6.84,"v":196016,"vr":1.94},
 "600155":{"c":6.00,"pc":5.91,"o":5.88,"h":6.03,"l":5.82,"v":433975,"vr":1.29},
}

QUAL = list(Q.keys())

def ma(vals, n):
    if len(vals) < 1: return 0.0
    if len(vals) < n: n = len(vals)
    return sum(vals[-n:]) / n

def rsi(closes, n=14):
    if len(closes) < n + 1: return 50.0
    gains = []; losses = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    g = gains[-n:]; l = losses[-n:]
    ag = sum(g)/n; al = sum(l)/n
    if al == 0: return 100.0
    rs = ag/al
    return 100 - 100/(1+rs)

def metrics(item, q):
    day = (item.get("kline") or {}).get("day") or []
    if not day: return None
    closes = [float(b[2]) for b in day]
    highs = [float(b[3]) for b in day]
    lows = [float(b[4]) for b in day]
    vols = [float(b[5]) for b in day]
    last = float(q["c"])
    closes[-1] = last
    highs[-1] = max(highs[-1], float(q["h"]))
    lows[-1] = min(lows[-1], float(q["l"]))
    vols[-1] = float(q["v"])
    ma20 = ma(closes, 20); ma60 = ma(closes, 60)
    ma20_prev = ma(closes[:-5], 20) if len(closes) > 25 else ma20
    ma60_prev = ma(closes[:-5], 60) if len(closes) > 65 else ma60
    ma20_dir = "up" if ma20 > ma20_prev else ("down" if ma20 < ma20_prev else "flat")
    ma60_dir = "up" if ma60 > ma60_prev else ("down" if ma60 < ma60_prev else "flat")
    priceMa = "above" if last > ma20 else "below"
    r = rsi(closes, 14)
    w = min(14, len(closes)-1)
    trs = []
    for i in range(len(closes)-w, len(closes)):
        hh = highs[i]; ll = lows[i]; pc = closes[i-1]
        trs.append(max(hh-ll, abs(hh-pc), abs(ll-pc)))
    atr = sum(trs)/len(trs)
    atr_pct = atr/last*100
    avgv = ma(vols[:-1], 20) if len(vols) > 1 else vols[-1]
    vr = float(q["vr"]) if q.get("vr") else (vols[-1]/avgv if avgv else 1)
    vol = "high" if vr >= 1.5 else ("low" if vr < 0.8 else "normal")
    struct = item.get("struct", "neutral")
    if priceMa == "below":
        struct = "neutral"
    elif priceMa == "above" and ma20_dir == "up":
        struct = "breakout" if last > ma20*1.03 else "pullback"
    sector = item.get("sector", "weak")
    return dict(ma20_dir=ma20_dir, ma60_dir=ma60_dir, priceMa=priceMa,
                rsi=round(r,1), atr=round(atr_pct,2), vol=vol, struct=struct,
                sector=sector, last=round(last,2), pct=round((last-float(q["pc"]))/float(q["pc"])*100,2))

def score(m, board):
    stop = 2.0 if board == "main" else 3.0
    s = 0
    s += {"up":12,"flat":6,"down":0}[m["ma20_dir"]]
    s += 8 if m["priceMa"] == "above" else 0
    s += {"up":5,"flat":2,"down":0}[m["ma60_dir"]]
    s += {"breakout":20,"pullback":14,"neutral":6}.get(m["struct"],6)
    s += {"high":15,"normal":9,"low":4}.get(m["vol"],9)
    s += {"strong":15,"mid":9,"weak":3}.get(m["sector"],3)
    r = m["rsi"]
    if 40 <= r <= 65: s += 15
    elif (30 <= r < 40) or (65 < r <= 70): s += 9
    elif (20 <= r < 30) or (70 < r <= 80): s += 4
    if m["atr"] <= stop*1.2: s += 10
    elif m["atr"] <= stop*1.8: s += 5
    return min(100, s)

out = []
for it in items:
    code = it.get("code")
    if code not in QUAL: continue
    q = Q.get(code)
    m = metrics(it, q)
    if not m: continue
    sc = score(m, it.get("board"))
    win = min(88, 50 + sc*0.35)
    out.append(dict(code=code, name=it.get("name"), board=it.get("board"),
        old_score=it.get("score"), old_win=it.get("win"), **m,
        score=sc, win=round(win,1), passd=sc >= 57))

out.sort(key=lambda x: -x["win"])
json.dump(out, open("选股结果/_rescored_0730.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("RE-SCORED EXISTING POOL (07-30 overlay)  n=%d" % len(out))
print("%-8s %-15s %-4s %5s %4s %5s %-4s %-6s %-4s %6s %6s %-7s %-9s %-5s %s" % (
    "code","name","bd","old","sc","win","ma20","pMa","ma60","rsi","atr","vol","struct","sect","PASS"))
for o in out:
    print("%-8s %-15s %-4s %5s %4d %5.1f %-4s %-6s %-4s %6.1f %6.2f %-7s %-9s %-5s %s" % (
        o["code"], o["name"][:14], o["board"], o["old_score"], o["score"], o["win"],
        o["ma20_dir"], o["priceMa"], o["ma60_dir"], o["rsi"], o["atr"], o["vol"],
        o["struct"], o["sector"], "Y" if o["passd"] else "n"))
