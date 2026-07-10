import os, json, glob, datetime

KDIR = r"C:/Users/fanfan/.workbuddy/projects/d-WorkBuddy/925680f7-b88a-408a-b476-c3f88660e22f/tool-results"

# ---- live quotes captured via tdx_quotes (2026-07-10 14:5x) ----
# entry = Now price; pct = intraday %, LB = 量比, HYZAF = 所属板块当日涨跌幅
QUOTES = {
    "000779": dict(name="甘咨询", board="main", now=10.60, pct=8.05,  lb=1.9287, hyzaf=2.5179),
    "600288": dict(name="大恒科技", board="main", now=16.52, pct=-1.55, lb=1.3170, hyzaf=-0.0086),
    "603137": dict(name="恒尚节能", board="main", now=26.66, pct=5.79,  lb=2.9961, hyzaf=2.9157),
    "688722": dict(name="同益中", board="star", now=18.31, pct=19.99, lb=4.5297, hyzaf=0.6719),
    "300918": dict(name="南山智尚", board="cyb",  now=12.35, pct=19.32, lb=3.2669, hyzaf=0.8965),
    "688101": dict(name="三达膜", board="star", now=17.02, pct=10.81, lb=6.3522, hyzaf=0.5043),
    "301367": dict(name="瑞迈特", board="cyb",  now=44.99, pct=16.61, lb=2.1658, hyzaf=0.9278),
    "002414": dict(name="高德红外", board="main", now=14.64, pct=9.99,  lb=3.9661, hyzaf=1.1634),
    "002144": dict(name="宏达高科", board="main", now=10.77, pct=10.01, lb=5.2922, hyzaf=0.8965),
    "600718": dict(name="东软集团", board="main", now=8.03,  pct=9.55,  lb=3.8006, hyzaf=0.9526),
    "002841": dict(name="视源股份", board="main", now=52.53, pct=0.77,  lb=1.9726, hyzaf=-3.1327),
}

def load_file(f):
    txt = open(f, encoding="utf-8", errors="replace").read()
    i = txt.find("{")
    obj = json.loads(txt[i:])
    code = str(obj.get("Code"))
    rows = obj.get("Rows") or []
    stats = obj.get("Stats") or {}
    rbc = stats.get("RangeBarCount")
    # 通达信日线返回 240 根、5分钟返回 245 根；日线 bar 也带 Second(=0)，故以 RangeBarCount 区分
    if rbc == 245:
        period = "min5"
    elif rbc == 240:
        period = "day"
    else:
        period = "min5" if (rows and (rows[0].get("Second") or 0) > 0) else "day"
    return code, period, rows

# group files by code+period
groups = {}
for f in sorted(glob.glob(os.path.join(KDIR, "*.txt"))):
    if "chatcmpl" in f: continue
    try:
        code, period, rows = load_file(f)
    except Exception as e:
        print("skip", f, e); continue
    groups.setdefault(code, {})[period] = rows

def fnum(x):
    try: return float(x)
    except: return 0.0

def parse_day(rows):
    out=[]
    for b in rows:
        d=str(b.get("Data"))
        o=fnum(b.get("Open")); c=fnum(b.get("Close")); h=fnum(b.get("High")); l=fnum(b.get("Low")); v=fnum(b.get("Volume"))
        out.append([d,o,c,h,l,v])
    return out  # 老->新

def parse_min5(rows):
    out=[]
    for b in rows:
        d=str(b.get("Data"))
        s=int(b.get("Second") or 0)
        hh=s//3600; mm=(s%3600)//60
        dt=f"{d} {hh:02d}{mm:02d}"
        o=fnum(b.get("Open")); c=fnum(b.get("Close")); h=fnum(b.get("High")); l=fnum(b.get("Low")); v=fnum(b.get("Volume"))
        out.append([dt,o,c,h,l,v])
    return out

def sma(vals, n):
    if len(vals) < n: return sum(vals)/max(1,len(vals))
    return sum(vals[-n:])/n

def rsi(closes, n=14):
    if len(closes) < n+1: return 50.0
    gains=[]; losses=[]
    for i in range(1,len(closes)):
        ch=closes[i]-closes[i-1]
        gains.append(max(ch,0)); losses.append(max(-ch,0))
    # Wilder smoothing
    g=sum(gains[:n])/n; l=sum(losses[:n])/n
    for i in range(n,len(gains)):
        g=(g*(n-1)+gains[i])/n
        l=(l*(n-1)+losses[i])/n
    if l==0: return 100.0
    rs=g/l
    return 100 - 100/(1+rs)

def atr_pct(bars, n=14):
    # bars: [d,o,c,h,l,v]  daily
    if len(bars) < n+1: return 0.0
    trs=[]
    for i in range(1,len(bars)):
        h=bars[i][3]; l=bars[i][4]; c_prev=bars[i-1][2]
        tr=max(h-l, abs(h-c_prev), abs(l-c_prev))
        trs.append(tr)
    a=sma(trs,n)
    return a/bars[-1][2]*100

def metrics(code, q):
    g=groups.get(code)
    day = parse_day(g["day"]) if g and g.get("day") else []
    min5 = parse_min5(g["min5"]) if g and g.get("min5") else []
    closes=[b[2] for b in day]
    # MA
    ma20=sma(closes,20); ma20_5=sma(closes[:-5],20) if len(closes)>25 else ma20
    ma60=sma(closes,60); ma60_5=sma(closes[:-5],60) if len(closes)>65 else ma60
    last=closes[-1]
    ma20_up = ma20>=ma20_5
    price_above = last>=ma20
    ma60_up = ma60>=ma60_5
    # RSI
    r = rsi(closes,14)
    # ATR%
    a = atr_pct(day,14)
    # volume ratio
    vols=[b[5] for b in day]
    ma20v=sma(vols,20)
    vratio = (vols[-1]/ma20v) if ma20v>0 else 1.0
    # structure
    highs=[b[3] for b in day]
    prev19=max(highs[-20:-1]) if len(highs)>=20 else max(highs)
    if highs[-1] > prev19*1.0001:
        struct="breakout"
    elif abs(last-ma20)/ma20 < 0.03 and closes[-1] < closes[-2]:
        struct="pullback"
    else:
        struct="neutral"
    # vol label
    if vratio>=1.5 or q["lb"]>=2.5:
        vol="high"
    elif vratio>=0.8:
        vol="normal"
    else:
        vol="low"
    # sector from HYZAF (板块当日涨跌幅)
    hz=q["hyzaf"]
    if hz>=1.0: sector="strong"
    elif hz>=0.0: sector="mid"
    else: sector="weak"
    return dict(ma20="up" if ma20_up else "down", priceMa="above" if price_above else "below",
               ma60="up" if ma60_up else "down", rsi=round(r,1), atr=round(a,2),
               struct=struct, vol=vol, sector=sector, day=day, min5=min5,
               ma20v=ma20, last=last)

def score(m, q):
    s=0
    s+= 10 if m["ma20"]=="up" else 0
    s+= 8 if m["priceMa"]=="above" else 0
    s+= 7 if m["ma60"]=="up" else 0
    s+= {"breakout":20,"pullback":16}.get(m["struct"],4)
    s+= {"high":15,"normal":8,"low":2}[m["vol"]]
    s+= {"strong":15,"mid":9,"weak":3}[m["sector"]]
    rs=m["rsi"]
    if 40<=rs<=60: s+=15
    elif (30<=rs<40) or (60<rs<=70): s+=8
    else: s+=3
    loss = 3.0 if q["board"] in ("cyb","star") else 2.0
    if m["atr"]<=loss*1.2: s+=10
    elif m["atr"]<=loss*1.8: s+=5
    else: s+=0
    win=min(88, 50+s*0.35)
    return s, round(win,1), loss

items=[]
for code,q in QUOTES.items():
    m=metrics(code,q)
    total,win,loss=score(m,q)
    entry=q["now"]
    stop=round(entry*(1-loss/100),2)
    target=round(entry*(1+(loss*3)/100),2)  # 主板止盈6%(loss*3), 创业板/科创板9%
    items.append(dict(code=code,q=q,m=m,total=total,win=win,loss=loss,entry=entry,stop=stop,target=target))

# sort by win desc
items.sort(key=lambda x:(-x["win"], -x["total"]))
print(f"{'code':6} {'name':6} {'board':5} {'ma20':5} {'pMA':5} {'ma60':5} {'rsi':5} {'atr%':6} {'struct':9} {'vol':6} {'sector':6} {'tot':3} {'win%':5} {'stop':8} {'tgt':8}")
for it in items:
    m=it["m"]; q=it["q"]
    print(f"{it['code']:6} {q['name']:6} {q['board']:5} {m['ma20']:5} {m['priceMa']:5} {m['ma60']:5} {m['rsi']:<5} {m['atr']:<6} {m['struct']:9} {m['vol']:6} {m['sector']:6} {it['total']:<3} {it['win']:<5} {it['stop']:<8} {it['target']:<8}")

# save intermediate for MD generation
json.dump(items, open(r"D:/WorkBuddy/_intermediate.json","w"), ensure_ascii=False)
print("\nwrote _intermediate.json; n=", len(items))
