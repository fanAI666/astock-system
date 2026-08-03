# -*- coding: utf-8 -*-
"""
2026-08-03 盘后定稿引擎（复刻 build_final.py 6维评分 + 任务 step3 ATR 规则 + 用户风控基线）
数据源：腾讯公开端点 web.ifzq.gtimg.cn 拉日K(qfq,800,末棒=2026-07-31)，评分全自 K线推导。
候选池：现有 import_final.json(50) + 07-31 tool_filter(main_inflow) 新候选(28)。
输出：选股结果/2026-07-31.md + 选股结果/import_final.json（合并去重，池只增不减）。
"""
import os, json, re, datetime, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = r"D:/WorkBuddy"
RES = os.path.join(BASE, "选股结果")
FINAL = os.path.join(RES, "import_final.json")
DATE = "2026-08-03"

UA = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://gu.qq.com/'}

def get(u, enc='utf-8', timeout=25, retries=3):
    last=None
    for i in range(retries):
        try:
            req=urllib.request.Request(u, headers=UA)
            return urllib.request.urlopen(req, timeout=timeout).read().decode(enc,'ignore')
        except Exception as e:
            last=e; time.sleep(1.0*(i+1))
    raise last

def prefix(code):
    c=code.strip()
    return 'sh' if c[0] in '69' else 'sz'

def board_of(code):
    c=code.strip()
    if c[:3] in ('300','301'): return 'cyb'
    if c[:3]=='688': return 'kcb'
    return 'main'

# ----- 指标 -----
def sma(v, n):
    if len(v)==0: return 0.0
    if len(v)<n: return sum(v)/len(v)
    return sum(v[-n:])/n

def rsi(closes, n=14):
    if len(closes)<n+1: return 50.0
    gains=[]; losses=[]
    for i in range(1,len(closes)):
        ch=closes[i]-closes[i-1]
        gains.append(max(ch,0)); losses.append(max(-ch,0))
    g=sum(gains[:n])/n; l=sum(losses[:n])/n
    for i in range(n,len(gains)):
        g=(g*(n-1)+gains[i])/n; l=(l*(n-1)+losses[i])/n
    if l==0: return 100.0
    return 100-100/(1+g/l)

def atr_pct(bars, n=14):
    if len(bars)<n+1: return 0.0
    trs=[]
    for i in range(1,len(bars)):
        h=bars[i][3]; l=bars[i][4]; cp=bars[i-1][2]
        trs.append(max(h-l, abs(h-cp), abs(l-cp)))
    return sma(trs,n)/bars[-1][2]*100

def metrics(day):
    closes=[b[2] for b in day]; vols=[b[5] for b in day]
    ma20=sma(closes,20); ma20_5=sma(closes[:-5],20) if len(closes)>25 else ma20
    ma60=sma(closes,60); ma60_5=sma(closes[:-60],60) if len(closes)>65 else ma60
    last=closes[-1]
    ma20_up=ma20>=ma20_5; price_above=last>=ma20; ma60_up=ma60>=ma60_5
    r=rsi(closes,14); a=atr_pct(day,14)
    mv=sma(vols,20); vratio=(vols[-1]/mv) if mv>0 else 1.0
    if vratio>=1.5: vol='high'
    elif vratio>=0.8: vol='normal'
    else: vol='low'
    highs=[b[3] for b in day]
    prev19=max(highs[-20:-1]) if len(highs)>=20 else max(highs)
    if highs[-1] > prev19*1.0001: struct='breakout'
    elif abs(last-ma20)/ma20 < 0.03 and closes[-1]<closes[-2]: struct='pullback'
    else: struct='neutral'
    return dict(ma20='up' if ma20_up else 'down', priceMa='above' if price_above else 'below',
                ma60='up' if ma60_up else 'down', rsi=round(r,1), atr=round(a,2),
                vol=vol, struct=struct, vratio=round(vratio,2),
                ma20v=round(ma20,2) if ma20 is not None else None)

def board_params(board):
    # 用户风控基线：主板 2/6；创业板(300)/科创板(688) 放宽50% -> 3/9
    if board=='main': return dict(loss=2.0, profit=6.0)
    return dict(loss=3.0, profit=9.0)  # cyb / kcb

# P8: 主板回踩入场带（对齐 backtest_phase12.js ENTRY_PULLBACK=1 的回测验证入口）
# 主板仅在「上升趋势中、收盘价距 MA20 不超过 5%」时视为有效回踩入场；追高或跌破均不参与主板信号
MAIN_PULLBACK_BAND = 0.05

def atr_fit(a, board):
    stop=board_params(board)['loss']
    if a<=stop*1.2: return 10
    if a<=stop*1.8: return 5
    return 0

def score6(m, board, pool_20d):
    s=0; rs=[]
    t=0
    if m['ma20']=='up': t+=10
    if m['priceMa']=='above': t+=8
    if m['ma60']=='up': t+=7
    s+=t; rs.append(f'趋势{t}/25')
    st={'breakout':20,'pullback':16}.get(m['struct'],4); s+=st; rs.append(f'结构{st}/20')
    v={'high':15,'normal':8,'low':2}[m['vol']]; s+=v; rs.append(f'量能{v}/15')
    # 板块：20日相对强度在池内分位
    if pool_20d and len(pool_20d)>=3:
        srt=sorted(pool_20d); idx=srt.index(m['ret20']) if m['ret20'] in srt else 0
        rf=idx/(len(srt)-1) if len(srt)>1 else 0
        sector='strong' if rf<=1/3 else ('mid' if rf<=2/3 else 'weak')
    else:
        sector='mid'
    sec={'strong':15,'mid':9,'weak':3}[sector]; s+=sec; rs.append(f'板块{sec}/15')
    rr=m['rsi']
    if 40<=rr<=60: r=15
    elif (30<=rr<40) or (60<rr<=70): r=8
    else: r=3
    s+=r; rs.append(f'RSI{r}/15')
    fit=atr_fit(m['atr'], board); s+=fit; rs.append(f'ATR适配{fit}/10')
    strength=min(88, 50+s*0.35)
    return s, round(strength,1), sector, fit, rs

# ----- K线拉取 -----
def pull(code):
    c=prefix(code)+code
    u=f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={c},day,2023-01-01,{DATE},800,qfq'
    try:
        j=json.loads(get(u))
        node=j['data'].get(c)
        if not node: return None
        kl=node.get('qfqday') or node.get('day') or []
        if not kl: return None
        # 归一化 [date,open,close,high,low,volume]
        out=[]
        for b in kl:
            out.append([str(b[0]), float(b[1]), float(b[2]), float(b[3]), float(b[4]), float(b[5])])
        return out
    except Exception as e:
        return None


# ----- 当日收盘棒（腾讯实时快照 qt.gtimg.cn，批量） -----
TODAY_BAR={}
def load_today_bars(codes):
    syms=[prefix(c)+c for c in codes]
    for i in range(0,len(syms),40):
        chunk=syms[i:i+40]
        u='https://qt.gtimg.cn/q='+','.join(chunk)
        try:
            txt=get(u, enc='gbk')
        except Exception:
            continue
        for line in txt.split(';'):
            line=line.strip()
            if not line.startswith('v_'): continue
            try:
                sym=line[2:line.index('=')]
                body=line[line.index('"')+1:line.rindex('"')]
                f=body.split('~')
                dt=f[30]  # yyyymmddHHMMSS
                d=dt[0:4]+'-'+dt[4:6]+'-'+dt[6:8]
                if d!=DATE: continue
                price=float(f[3]); openp=float(f[5]); high=float(f[33]); low=float(f[34]); vol=float(f[36])
                if price<=0: continue
                TODAY_BAR[sym[2:]]=[DATE, openp, price, high, low, vol]
            except Exception:
                continue
    print(f'当日收盘棒(qt.gtimg.cn) 获取 {len(TODAY_BAR)}/{len(codes)}')

# ----- 候选 -----
blob=json.load(open(FINAL, encoding='utf-8'))
old_items=blob['items'] if isinstance(blob,dict) else blob
old_map={str(it['code']).strip(): it for it in old_items}

NEW_SCREEN={
 '600396':'华电辽能','688017':'绿的谐波','600438':'通威股份','300757':'罗博特科',
 '000636':'风华高科','301396':'宏景科技','300857':'协创数据','300620':'光库科技',
 '300570':'太辰光','300613':'富瀚微','688313':'仕佳光子','000815':'美利云',
 '002138':'顺络电子','002149':'西部材料','600875':'东方电气','600406':'国电南瑞',
 '002471':'中超控股','001270':'铖昌科技','688167':'炬光科技','601991':'大唐发电',
 '601939':'建设银行','688048':'长光华芯','300548':'长芯博创','002361':'神剑股份',
 '601611':'中国核建','300214':'日科化学','300394':'天孚通信','688825':'长鑫科技',
 '002763':'汇洁股份','603165':'荣晟环保','600329':'达仁堂','603508':'思维列控',
 '603167':'渤海轮渡','300406':'九强生物','000915':'华特达因','600219':'南山铝业',
 '002572':'索菲亚','000913':'钱江摩托','603551':'奥普科技','688399':'硕世生物'}

existing_codes=list(old_map.keys())
new_codes=[c for c in NEW_SCREEN if c not in old_map]
all_codes=existing_codes+new_codes

print(f'候选总数={len(all_codes)} (现有{len(existing_codes)} + 新{len(new_codes)})')

# 并发拉K线
kl_map={}
def worker(code):
    return code, pull(code)
with ThreadPoolExecutor(max_workers=8) as ex:
    futs=[ex.submit(worker,c) for c in all_codes]
    for f in as_completed(futs):
        c,k=f.result()
        kl_map[c]=k

load_today_bars(all_codes)
_app=0
for c,k in kl_map.items():
    if not k: continue
    tb=TODAY_BAR.get(c)
    if not tb: continue
    if k[-1][0]==DATE:
        k[-1]=tb
    elif k[-1][0]<DATE:
        k.append(tb); _app+=1
print(f'叠加当日收盘棒: 新增 {_app} 只；末棒日期样本={[kl_map[c][-1][0] for c in all_codes[:5] if kl_map[c]]}')

ok=sum(1 for v in kl_map.values() if v)
print(f'K线拉取成功 {ok}/{len(all_codes)}')

# 计算 20日收益（板块分位用）
def ret20(day):
    if len(day)<21: return 0.0
    return (day[-1][2]-day[-21][2])/day[-21][2]*100
pool_20d=[ret20(kl_map[c]) for c in all_codes if kl_map[c]]

# ----- 评分 -----
def evaluate(code, name, is_new):
    day=kl_map[code]
    if not day or len(day)<30: return None
    m=metrics(day)
    m['ret20']=ret20(day)
    board=board_of(code)
    total, strength, sector, fit, rs=score6(m, board, pool_20d)
    close=day[-1][2]
    prev=day[-2][2] if len(day)>1 else close
    pct=(close-prev)/prev*100 if prev else 0.0
    bp=board_params(board)
    entry=round(close,2)
    stop=round(entry*(1-bp['loss']/100),2)
    target=round(entry*(1+bp['profit']/100),2)
    # caveats
    caveats=[]
    if m['rsi']>72: caveats.append('RSI超买%.1f'%m['rsi'])
    if m['ma60']!='up': caveats.append('MA60%s(中长期趋势弱)'%m['ma60'])
    if pct>6: caveats.append('追高+%.1f%%'%pct)
    # 达标判定（盘后定稿）：score>=57 且 非涨停追高(pct<=9.5)
    pass_ = (total>=57) and (pct<=9.5)
    # P8: 主板回踩入场硬约束（对齐 backtest_phase12.js ENTRY_PULLBACK=1 的验证入口）
    # 仅在「上升趋势中、收盘价距 MA20 不超过 5%」时作为有效回踩入场；追高或跌破 MA20 均不参与主板信号
    if board=='main' and m.get('ma20v') is not None:
        band=m['ma20v']*(1+MAIN_PULLBACK_BAND)
        pullback_ok=(m['priceMa']=='above') and (close<=band)
        if not pullback_ok:
            caveats.append('主板回踩拒: 需价在MA20上且收盘<=MA20×1.05=%.2f' % band)
            pass_=False
    return dict(code=code, name=name, board=board, m=m, total=total, strength=strength,
                sector=sector, fit=fit, rs=rs, entry=entry, stop=stop, target=target,
                pct=round(pct,2), caveats=caveats, pass_=pass_, is_new=is_new, day=day)

rows=[]
for c in existing_codes:
    if kl_map[c] is None: continue
    name=old_map[c]['name']
    r=evaluate(c, name, False)
    if r: rows.append(r)
for c in new_codes:
    if kl_map[c] is None: continue
    r=evaluate(c, NEW_SCREEN[c]+' '+c, True)
    if r: rows.append(r)

rows.sort(key=lambda x:(-x['strength'], -x['total']))

# ----- 写 import_final.json -----
new_final=[]
for r in rows:
    if r['pass_'] and r['is_new']:
        new_final.append(dict(name=r['name'], code=r['code'], board=r['board'],
            ma20=r['m']['ma20'], priceMa=r['m']['priceMa'], ma60=r['m']['ma60'],
            rsi=r['m']['rsi'], vol=r['m']['vol'], struct=r['m']['struct'], sector=r['sector'],
            atr=r['m']['atr'], entry=r['entry'], category='final', date=DATE,
            stopPrice=r['stop'], targetPrice=r['target'],
            kline=dict(day=r['day'][-800:], min5=old_map.get(r['code'],{}).get('kline',{}).get('min5',[]))))

updated_items=[]
for it in old_items:
    c=str(it['code']).strip()
    k=kl_map.get(c)
    if k is None:
        updated_items.append(it); continue
    # 找该股的评分
    rr=next((x for x in rows if x['code']==c), None)
    if rr is None:
        updated_items.append(it); continue
    new_it=dict(it)
    new_it['kline']=dict(day=k[-800:], min5=it.get('kline',{}).get('min5',[]))
    new_it.update(dict(ma20=rr['m']['ma20'], priceMa=rr['m']['priceMa'], ma60=rr['m']['ma60'],
        rsi=rr['m']['rsi'], vol=rr['m']['vol'], struct=rr['m']['struct'], sector=rr['sector'],
        atr=rr['m']['atr']))
    if rr['pass_']:
        # 重新签发当日信号
        new_it.update(dict(date=DATE, entry=rr['entry'], stopPrice=rr['stop'], targetPrice=rr['target']))
    updated_items.append(new_it)

all_final=updated_items+new_final
out=dict(updated=datetime.datetime.now().astimezone().isoformat(), items=all_final)
json.dump(out, open(FINAL,'w',encoding='utf-8'), ensure_ascii=False)
print(f'import_final.json 写入: 总{len(all_final)}项 (现有{len(updated_items)} + 新达标{len(new_final)})')

# ----- 生成 MD -----
passing=[r for r in rows if r['pass_']]
passing.sort(key=lambda x:-x['strength'])
now=datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
lines=[]
lines.append(f'# A股稳健选股 · 盘后定稿（{DATE}）')
lines.append('')
lines.append(f'- **数据日**：{DATE}')
lines.append(f'- **生成时间**：{now}')
lines.append(f'- **候选池**：{len(rows)} 只（现有重评 {len(existing_codes)} + 新筛 {len(new_codes)}）')
lines.append(f'- **达标数量**：{len(passing)} 只（综合强度分≥70% 且非涨停追高）')
lines.append(f'- **风控基线**：主板 止损2%/止盈6%；创业板(300)/科创板(688) 止损3%/止盈9%；目标胜率≥70%')
lines.append('')
lines.append('## 一、达标候选清单（按胜率降序）')
lines.append('')
lines.append('| 名称/代码 | 板块 | 综合分 | 胜率估算 | 止损价 | 止盈价 | 入选理由 |')
lines.append('| --- | --- | --- | --- | --- | --- | --- |')
for r in passing:
    reason=''
    if r['m']['struct']=='breakout': reason+='突破;'
    if r['m']['ma20']=='up' and r['m']['priceMa']=='above': reason+='多头排列;'
    if r['m']['vol']=='high': reason+='放量;'
    if r['sector']=='strong': reason+='板块强;'
    if not reason: reason='技术面达标'
    reason=reason.rstrip(';')
    cav=''
    if r['caveats']: cav='（⚠️'+'、'.join(r['caveats'])+'）'
    lines.append(f"| {r['name']} | {r['board']} | {r['total']} | {r['strength']:.1f}% | {r['stop']} | {r['target']} | {reason}{cav} |")
lines.append('')
lines.append('## 二、前3名简评')
lines.append('')
for i,r in enumerate(passing[:3],1):
    lines.append(f"{i}. **{r['name']}**（{r['board']}）：综合分 {r['total']}/胜率 {r['strength']:.1f}%。"
                 f" MA20={r['m']['ma20']}、股价{r['m']['priceMa']}MA20、MA60={r['m']['ma60']}；"
                 f" RSI={r['m']['rsi']}、ATR={r['m']['atr']}%、量能={r['m']['vol']}、结构={r['m']['struct']}、板块={r['sector']}。"
                 + (' 注意：'+'、'.join(r['caveats'])+'。' if r['caveats'] else ' 技术面健康。'))
lines.append('')
lines.append('## 三、落选/排除（score<57 或涨停追高）')
lines.append('')
fails=[r for r in rows if not r['pass_']]
fails.sort(key=lambda x:-x['strength'])
for r in fails[:25]:
    why=[]
    if r['pct']>9.5: why.append(f"涨停/追高+{r['pct']:.1f}%")
    if r['total']<57: why.append(f"综合分{r['total']}<57")
    why_s='、'.join(why) or '技术面未达标'
    lines.append(f"- {r['name']}（{r['board']}）：{why_s} 〔分{r['total']}/胜率{r['strength']:.1f}%〕")
lines.append('')
lines.append('## 四、风险提示')
lines.append('')
# 大盘
lines.append('- 大盘：见 fundflow.json（资金动态面板）。若上证/深证/创业板任一跌超2%，建议收缩或暂停新增。')
n_overbought=sum(1 for r in passing if r['m']['rsi']>72)
n_ma60down=sum(1 for r in passing if r['m']['ma60']!='up')
n_atr0=sum(1 for r in passing if r['fit']==0)
if n_overbought: lines.append(f'- 超买警示：{n_overbought} 只达标股 RSI>72，追高风险大，宜等回踩 MA20 买点。')
if n_ma60down: lines.append(f'- 趋势根基：{n_ma60down} 只达标股 MA60 未向上，中长期趋势偏弱，按实盘 P7 规则应剔除，盘后仅作技术面达标保留。')
if n_atr0: lines.append(f'- 波动率：{n_atr0} 只达标股 ATR% 高于止损×1.8，「止损适配」维度得 0 分，固定止损易被扫损，建议放大止损或减仓。')
lines.append('- 本周交易笔数需用户在系统「风控看板」自行核对（自动化无法读取 localStorage）。')
lines.append('- 以上为技术面估算模型，非投资建议；仅做选股与提示，不下单、不交易。')
lines.append('')
md='\n'.join(lines)
open(os.path.join(RES, DATE+'.md'),'w',encoding='utf-8').write(md)
print(f'MD 写入: {DATE}.md，达标 {len(passing)} 只')

# 控制台摘要
print('\n=== 达标清单（前15）===')
print(f"{'name':14} {'board':4} {'tot':>3} {'win%':>5} {'entry':>8} {'stop':>8} {'tgt':>8} {'rsi':>5} {'atr%':>5} {'struct':9} {'vol':6} {'sector':6}")
for r in passing[:15]:
    print(f"{r['name'][:14]:14} {r['board']:4} {r['total']:>3} {r['strength']:>5.1f} {r['entry']:>8} {r['stop']:>8} {r['target']:>8} {r['m']['rsi']:>5} {r['m']['atr']:>5} {r['m']['struct']:9} {r['m']['vol']:6} {r['sector']:6}")
print(f"\n达标 {len(passing)} / 候选 {len(rows)}；新达标 {len(new_final)}")
