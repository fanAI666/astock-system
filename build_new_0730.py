# -*- coding: utf-8 -*-
"""Fetch ~3yr day-K-line for fresh 07-30 candidates via Tencent public endpoint (no MCP context cost),
overlay 07-30 close, score (6-dim), and embed NEW items into import_final.json (pool grows, never shrinks).
"""
import json, urllib.request, time

P = "选股结果/import_final.json"
data = json.load(open(P, encoding="utf-8"))
items = data["items"]
existing_codes = {it.get("code") for it in items}

def market_prefix(code):
    return "sh" if code[0] in "69" else "sz"

# 07-30 quotes + sector(strong/mid/weak from fundflow heatSectors)
NEW = {
 "600000": {"name":"浦发银行","c":9.71,"pc":9.28,"o":9.26,"h":9.72,"l":9.25,"v":1617462,"vr":2.19,"sector":"strong","board":"main"},
 "601288": {"name":"农业银行","c":7.11,"pc":6.93,"o":6.91,"h":7.11,"l":6.90,"v":5518245,"vr":1.26,"sector":"strong","board":"main"},
 "600036": {"name":"招商银行","c":40.55,"pc":39.66,"o":39.66,"h":40.55,"l":39.55,"v":1374580,"vr":1.46,"sector":"strong","board":"main"},
 "000858": {"name":"五 粮 液","c":78.56,"pc":75.17,"o":75.10,"h":78.84,"l":75.01,"v":729039,"vr":2.27,"sector":"mid","board":"main"},
 "600519": {"name":"贵州茅台","c":1361.76,"pc":1321,"o":1323,"h":1362,"l":1322,"v":71873,"vr":1.66,"sector":"mid","board":"main"},
 "601857": {"name":"中国石油","c":11.27,"pc":10.89,"o":10.94,"h":11.27,"l":10.94,"v":2052531,"vr":1.04,"sector":"mid","board":"main"},
 "600900": {"name":"长江电力","c":29.49,"pc":28.93,"o":28.85,"h":29.53,"l":28.81,"v":1930634,"vr":1.50,"sector":"weak","board":"main"},
 "601899": {"name":"紫金矿业","c":32.70,"pc":32.15,"o":32.63,"h":33.18,"l":32.01,"v":2842980,"vr":0.96,"sector":"weak","board":"main"},
 "300750": {"name":"宁德时代","c":401.88,"pc":396.84,"o":390,"h":403.8,"l":389.8,"v":452390,"vr":1.21,"sector":"weak","board":"cyb"},
}

def fetch_day(code):
    full = market_prefix(code) + code
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s,day,2023-01-01,2026-07-30,800,qfq" % full
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Referer':'https://gu.qq.com/'})
            j = json.loads(urllib.request.urlopen(req, timeout=15).read().decode('utf-8','ignore'))
            node = j["data"][full]
            arr = node.get("qfqday") or node.get("day")
            if not arr: return None
            day = []
            for b in arr:
                try:
                    day.append([b[0], float(b[1]), float(b[2]), float(b[3]), float(b[4]), float(b[5])])
                except Exception:
                    pass
            return day
        except Exception as e:
            if attempt == 2:
                print("  FETCH ERR %s: %s" % (code, e))
            time.sleep(0.5)
    return None

def ma(vals, n):
    if len(vals) < 1: return 0.0
    if len(vals) < n: n = len(vals)
    return sum(vals[-n:])/n

def rsi(closes, n=14):
    if len(closes) < n+1: return 50.0
    g=[]; l=[]
    for i in range(1,len(closes)):
        d=closes[i]-closes[i-1]; g.append(max(d,0)); l.append(max(-d,0))
    ag=sum(g[-n:])/n; al=sum(l[-n:])/n
    if al==0: return 100.0
    return 100-100/(1+ag/al)

def metrics(day, q):
    closes=[b[2] for b in day]; highs=[b[3] for b in day]; lows=[b[4] for b in day]; vols=[b[5] for b in day]
    last=float(q["c"])
    closes[-1]=last; highs[-1]=max(highs[-1],float(q["h"])); lows[-1]=min(lows[-1],float(q["l"])); vols[-1]=float(q["v"])
    ma20=ma(closes,20); ma60=ma(closes,60)
    ma20p=ma(closes[:-5],20) if len(closes)>25 else ma20
    ma60p=ma(closes[:-5],60) if len(closes)>65 else ma60
    ma20_dir="up" if ma20>ma20p else ("down" if ma20<ma20p else "flat")
    ma60_dir="up" if ma60>ma60p else ("down" if ma60<ma60p else "flat")
    priceMa="above" if last>ma20 else "below"
    r=rsi(closes,14)
    w=min(14,len(closes)-1); trs=[]
    for i in range(len(closes)-w,len(closes)):
        hh=highs[i]; ll=lows[i]; pc=closes[i-1]; trs.append(max(hh-ll,abs(hh-pc),abs(ll-pc)))
    atr=sum(trs)/len(trs); atr_pct=atr/last*100
    avgv=ma(vols[:-1],20) if len(vols)>1 else vols[-1]
    vr=float(q["vr"]) if q.get("vr") else (vols[-1]/avgv if avgv else 1)
    vol="high" if vr>=1.5 else ("low" if vr<0.8 else "normal")
    if priceMa=="below": struct="neutral"
    elif priceMa=="above" and ma20_dir=="up": struct="breakout" if last>ma20*1.03 else "pullback"
    else: struct="neutral"
    sector=q["sector"]
    return dict(ma20_dir=ma20_dir,ma60_dir=ma60_dir,priceMa=priceMa,rsi=round(r,1),
                atr=round(atr_pct,2),vol=vol,struct=struct,sector=sector,last=round(last,2),
                pct=round((last-float(q["pc"]))/float(q["pc"])*100,2))

def score(m, board):
    stop=2.0 if board=="main" else 3.0
    s=0
    s+={"up":12,"flat":6,"down":0}[m["ma20_dir"]]
    s+=8 if m["priceMa"]=="above" else 0
    s+={"up":5,"flat":2,"down":0}[m["ma60_dir"]]
    s+={"breakout":20,"pullback":14,"neutral":6}.get(m["struct"],6)
    s+={"high":15,"normal":9,"low":4}.get(m["vol"],9)
    s+={"strong":15,"mid":9,"weak":3}.get(m["sector"],3)
    r=m["rsi"]
    if 40<=r<=65: s+=15
    elif (30<=r<40) or (65<r<=70): s+=9
    elif (20<=r<30) or (70<r<=80): s+=4
    if m["atr"]<=stop*1.2: s+=10
    elif m["atr"]<=stop*1.8: s+=5
    return min(100,s)

added=[]; skipped=[]
for code, q in NEW.items():
    if code in existing_codes:
        skipped.append((code, "already in pool")); continue
    day = fetch_day(code)
    if not day:
        skipped.append((code, "kline fetch failed")); continue
    # append 07-30 bar if last date stale
    if day[-1][0] < "2026-07-30":
        day.append(["2026-07-30", float(q["o"]), float(q["c"]), float(q["h"]), float(q["l"]), float(q["v"])])
    m = metrics(day, q)
    sc = score(m, q["board"])
    win = min(88, 50 + sc*0.35)
    board = q["board"]
    stop_pct = 0.98 if board=="main" else 0.97
    tgt_pct = 1.06 if board=="main" else 1.09
    entry = float(q["c"])
    item = {
        "name": q["name"]+" "+code, "code": code,
        "setcode": "1" if code[0] in "69" else "0", "board": board,
        "ma20": m["ma20_dir"], "ma60": m["ma60_dir"], "priceMa": m["priceMa"],
        "rsi": m["rsi"], "vol": m["vol"], "struct": m["struct"], "sector": m["sector"],
        "atr": m["atr"], "score": sc, "win": round(win,1), "category": "final",
        "date": "2026-07-30",
        "stopPrice": round(entry*stop_pct, 2), "targetPrice": round(entry*tgt_pct, 2),
        "kline": {"day": day, "min5": []},
    }
    items.append(item)
    added.append((code, q["name"], sc, round(win,1), m, item["stopPrice"], item["targetPrice"]))

# write back (backup first)
import shutil
shutil.copyfile(P, P + ".bak")
json.dump(data, open(P,"w",encoding="utf-8"), ensure_ascii=False)
json.dump([a[0] for a in added], open("选股结果/_newcodes_0730.json","w"), ensure_ascii=False)

print("ADDED NEW 07-30 CANDIDATES: %d" % len(added))
print("%-8s %-12s %4s %5s %-4s %-6s %-4s %6s %6s %-7s %-9s %-5s  stop/tgt" % (
    "code","name","sc","win","ma20","pMa","ma60","rsi","atr","vol","struct","sect"))
for code,name,sc,win,m,sp,tp in added:
    print("%-8s %-12s %4d %5.1f %-4s %-6s %-4s %6.1f %6.2f %-7s %-9s %-5s  %.2f/%.2f" % (
        code,name,sc,win,m["ma20_dir"],m["priceMa"],m["ma60_dir"],m["rsi"],m["atr"],m["vol"],m["struct"],m["sector"],sp,tp))
print("SKIPPED: %s" % skipped)
print("TOTAL items now: %d" % len(items))
