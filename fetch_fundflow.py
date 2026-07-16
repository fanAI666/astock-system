# -*- coding: utf-8 -*-
"""
盘后抓取真实资金流向数据 -> 选股结果/fundflow.json
数据源：指数/风格用腾讯行情(qt.gtimg.cn，稳定不限流)；行业主力净流入/北向用东方财富公开接口。
调用时机：每日 18:00 盘后（或随云端同步前）由自动化执行。
所有接口均带容错，失败部分降级为空，前端做友好提示。
"""
import urllib.request, json, os, datetime, time, re

OUT = 'D:/WorkBuddy/选股结果/fundflow.json'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
REF = 'https://quote.eastmoney.com/'

def get(url, enc='utf-8', timeout=15, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': UA, 'Referer': REF, 'Connection': 'close'})
            return urllib.request.urlopen(req, timeout=timeout).read().decode(enc, 'ignore')
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last

# ---------- 腾讯行情解析（指数 / 风格）----------
def tx(sec):
    txt = get('https://qt.gtimg.cn/q=' + sec, enc='gbk')
    m = re.search(r'"([^"]+)"', txt)
    if not m:
        return None
    p = m.group(1).split('~')
    try:
        name = p[1]
        price = float(p[3])
        prev = float(p[4])
        pct = (price - prev) / prev * 100
        return name, round(price, 2), round(pct, 2)
    except Exception:
        return None

# 指数（腾讯）
INDEX_MAP = [('sh000001', '上证指数'), ('sz399001', '深证成指'), ('sz399006', '创业板指')]
indices = []
for sec, _ in INDEX_MAP:
    try:
        r = tx(sec)
        if r:
            indices.append({'name': r[0], 'val': r[1], 'pct': r[2]})
    except Exception as e:
        print('INDEX ERR', sec, e)

# 风格因子（国证风格指数涨跌幅 -> 相对强弱分）
STYLE = [('sz399372', '大盘成长'), ('sz399373', '大盘价值'), ('sz399376', '小盘成长'), ('sz399377', '小盘价值')]
styleFactors = []
for sec, _ in STYLE:
    try:
        r = tx(sec)
        if r:
            pct = r[2]
            score = max(0, min(100, round(50 + pct * 8)))
            styleFactors.append({'name': r[0], 'score': score, 'up': pct >= 0})
    except Exception as e:
        print('STYLE ERR', sec, e)

# ---------- 申万/东财行业板块（涨跌幅 + 主力净流入/流入/流出）----------
sectors = []
try:
    d = json.loads(get('https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=80&po=1&np=1&fltt=2&invt=2&fs=m:90+t:2&fields=f12,f14,f3,f62,f66,f72,f184'))
    for it in d.get('data', {}).get('diff', []):
        net = float(it.get('f62') or 0) / 1e8            # 主力净流入（亿元）
        inflow = float(it.get('f66') or 0) / 1e8          # 主力流入（亿元）
        outflow = float(it.get('f72') or 0) / 1e8         # 主力流出（亿元）
        if inflow == 0 and outflow == 0:
            inflow = max(net, 0)
            outflow = min(net, 0)
        sectors.append({
            'name': it.get('f14'),
            'pct': round(float(it.get('f3') or 0), 2),
            'net': round(net, 1),
            'inflow': round(inflow, 1),
            'outflow': round(outflow, 1),
        })
except Exception as e:
    print('SECTOR ERR', e)

# ---------- 北向资金（沪股通 + 深股通当日净买入）----------
northFlow = {'todayNet': None, 'shNet': None, 'szNet': None, 'history': [], 'note': ''}
try:
    d = json.loads(get('https://push2.eastmoney.com/api/qt/kamt/get?fields1=f1,f3&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ut=7eea3edcaed734bea9cbfc24409ed989'))
    data = d.get('data', {})
    shNet = float((data.get('hk2sh') or {}).get('dayNetAmtIn') or 0) / 1e4
    szNet = float((data.get('hk2sz') or {}).get('dayNetAmtIn') or 0) / 1e4
    northFlow['shNet'] = round(shNet, 1)
    northFlow['szNet'] = round(szNet, 1)
    northFlow['todayNet'] = round(shNet + szNet, 1)
    northFlow['note'] = '沪股通+深股通当日净买入(亿元)；盘后较晚时段接口可能归零'
except Exception as e:
    print('NORTH ERR', e)
    northFlow['note'] = '北向数据获取失败，已留空'

# ---------- 自动生成资金主线描述 ----------
pos = sorted([s for s in sectors if s['pct'] > 0], key=lambda x: -x['pct'])
neg = sorted([s for s in sectors if s['pct'] < 0], key=lambda x: x['pct'])
top_net = sorted(sectors, key=lambda x: -x['net'])[:3]
idx_txt = '、'.join(['%s%s%%' % (i['name'].replace('指数', ''), ('+' if i['pct'] >= 0 else '') + str(i['pct'])) for i in indices]) if indices else '数据缺失'
fundThread = '今日盘面：%s。资金主攻方向为 %s' % (
    idx_txt,
    '、'.join(['%s(+%s%%)' % (s['name'], s['pct']) for s in pos[:3]]) or '无明显主线'
)
if top_net and top_net[0]['net'] > 0:
    fundThread += '；主力净流入居前：%s(+%s亿)' % (top_net[0]['name'], top_net[0]['net'])
if northFlow['todayNet'] is not None:
    if northFlow['todayNet'] != 0:
        fundThread += '。北向资金%s %.1f 亿元' % ('净买入' if northFlow['todayNet'] >= 0 else '净卖出', abs(northFlow['todayNet']))
    else:
        fundThread += '。北向当日净额接口归零（盘后）'
fundThread += '。'

# ---------- 自动生成行业配置研判（基于强弱）----------
recs = []
if pos[:1]:
    t = pos[0]
    recs.append({'tag': '加仓方向', 'cls': 'buy', 'title': '%s获资金聚焦' % t['name'],
                 'reason': '%s涨%s%%、主力净流入%s亿，资金主线明确，建议超配/持有板块龙头。' % (t['name'], ('+' + str(t['pct'])), t['net'])})
if neg[:1]:
    t = neg[0]
    recs.append({'tag': '谨慎规避', 'cls': 'sell', 'title': '%s资金持续流出' % t['name'],
                 'reason': '%s跌%s%%、主力净流出%s亿，建议低配或回避。' % (t['name'], t['pct'], abs(t['net']))})
flat = sorted(sectors, key=lambda x: abs(x['pct']))[:1]
if flat:
    t = flat[0]
    recs.append({'tag': '持有观察', 'cls': 'hold', 'title': '%s方向待明朗' % t['name'],
                 'reason': '%s涨%s%%、主力净流入%s亿，多空均衡，建议持有观察。' % (t['name'], ('+' + str(t['pct'])), t['net'])})

# ---------- 组装输出 ----------
out = {
    'updatedAt': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    'source': '腾讯行情(指数/风格) + 东方财富(行业主力净流入/北向)，盘后抓取',
    'indices': indices,
    'fundThread': fundThread,
    'heatSectors': [{'name': s['name'], 'pct': s['pct']} for s in sectors],
    'fundFlow': [
        {'sector': s['name'], 'net': s['net'], 'inflow': s['inflow'], 'outflow': s['outflow']}
        for s in sorted(sectors, key=lambda x: -x['net'])[:12]
    ],
    'styleFactors': styleFactors,
    'northFlow': northFlow,
    'recommendations': recs,
}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

print('OK written:', OUT)
print('  indices=%d  sectors=%d  style=%d  north(todayNet=%s)  recs=%d' % (
    len(indices), len(sectors), len(styleFactors), northFlow['todayNet'], len(recs)))
