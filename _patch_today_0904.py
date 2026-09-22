# -*- coding: utf-8 -*-
"""
当日棒叠加 + 重评分 (2026-09-01)
腾讯 fqkline 日K在盘中/刚收盘时滞后1日 -> 用 qt.gtimg.cn 批量快照补当日收盘棒，
然后基于含当日棒的日K重算 6 维评分，重写 import_final.json 与 dated MD。
"""
import urllib.request, json, os, datetime, time, re

BASE = 'D:/WorkBuddy/选股结果'
SRC = os.path.join(BASE, 'import_final.json')
DATE = '2026-09-04'
MIN_BARS = 250
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
TODAY_BAR = {}

def get(url, enc='utf-8', timeout=12, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': 'https://gu.qq.com/'})
            return urllib.request.urlopen(req, timeout=timeout).read().decode(enc, 'ignore')
        except Exception as e:
            last = e; time.sleep(0.8 * (i + 1))
    raise last

def prefix(c):
    return 'sh' if str(c)[0] in '69' else 'sz'

def load_today_bars(codes):
    syms = [prefix(c) + c for c in codes]
    for i in range(0, len(syms), 40):
        chunk = syms[i:i+40]
        try:
            txt = get('https://qt.gtimg.cn/q=' + ','.join(chunk), enc='gbk')
        except Exception:
            continue
        for line in txt.split(';'):
            line = line.strip()
            if not line.startswith('v_'): continue
            try:
                sym = line[2:line.index('=')]
                body = line[line.index('"')+1:line.rindex('"')]
                f = body.split('~')
                dt = f[30]
                d = dt[0:4] + '-' + dt[4:6] + '-' + dt[6:8]
                if d != DATE: continue
                price = float(f[3]); openp = float(f[5])
                high = float(f[33]); low = float(f[34]); vol = float(f[36])
                if price <= 0: continue
                TODAY_BAR[sym[2:]] = [DATE, openp, price, high, low, vol]
            except Exception:
                continue
        time.sleep(0.1)
    print('当日收盘棒(qt.gtimg.cn) 获取 %d/%d' % (len(TODAY_BAR), len(codes)))

# ---- 指标 ----
def sma(v, n): return None if len(v) < n else sum(v[-n:]) / n

def ma_dir(closes, n):
    cur = sma(closes, n); prev = sma(closes[:-5], n) if len(closes) > n + 5 else None
    if cur is None or prev is None: return 'flat'
    if cur > prev * 1.001: return 'up'
    if cur < prev * 0.999: return 'down'
    return 'flat'

def rsi(closes, n=14):
    if len(closes) < n + 1: return 50.0
    g = []; l = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]; g.append(max(d, 0)); l.append(max(-d, 0))
    ag = sum(g[-n:]) / n; al = sum(l[-n:]) / n
    if al == 0: return 100.0
    return 100 - 100 / (1 + ag / al)

def atr_pct(bars, n=14):
    if len(bars) < n + 1: return 3.0
    tr = []
    for i in range(1, len(bars)):
        h = bars[i][3]; lo = bars[i][4]; pc = bars[i-1][2]
        tr.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    return (sum(tr[-n:]) / n) / bars[-1][2] * 100

def vol_class(bars):
    if len(bars) < 21: return 'normal'
    vnow = bars[-1][5]; vma = sma([b[5] for b in bars], 20)
    if not vma: return 'normal'
    r = vnow / vma
    return 'high' if r > 1.5 else ('low' if r < 0.7 else 'normal')

def classify_struct(closes, ma20v, priceMa):
    if len(closes) < 21: return 'none'
    if closes[-1] > max(closes[-21:-1]) and priceMa == 'above': return 'breakout'
    if priceMa == 'above' and ma20v and (ma20v * 0.97 <= closes[-1] <= ma20v * 1.02): return 'pullback'
    return 'none'

def score_item(it):
    code = it['code']; bars = it['kline']['day']
    closes = [b[2] for b in bars]
    ma20v = sma(closes, 20)
    ma20d = ma_dir(closes, 20); ma60d = ma_dir(closes, 60)
    priceMa = 'above' if (ma20v and closes[-1] >= ma20v) else 'below'
    r = rsi(closes); a = atr_pct(bars); v = vol_class(bars)
    struct = classify_struct(closes, ma20v, priceMa)
    sector = it.get('sector', 'mid')
    board = it.get('board', '')
    if board in ('cyb', 'chuang', 'kcb') or str(code).startswith(('300', '688')):
        sp, tp = 3.0, 9.0
        board = board or 'cyb'
    else:
        sp, tp = 2.0, 6.0
        board = board or 'main'

    s_trend = (10 if ma20d == 'up' else 5 if ma20d == 'flat' else 0) + \
              (8 if priceMa == 'above' else 0) + \
              (7 if ma60d == 'up' else 3 if ma60d == 'flat' else 0)
    s_struct = 20 if struct == 'breakout' else 10 if struct == 'pullback' else 0
    s_vol = 15 if v == 'high' else 8 if v == 'normal' else 0
    s_sector = 15 if sector == 'strong' else 8 if sector == 'mid' else 0
    s_rsi = 15 if 45 <= r <= 65 else (8 if 35 <= r <= 75 else 0)
    s_atr = 10 if a <= sp * 1.2 else (5 if a <= sp * 1.8 else 0)

    total = s_trend + s_struct + s_vol + s_sector + s_rsi + s_atr
    win = min(88.0, 50 + total * 0.35)
    entry = round(closes[-1], 2)
    it.update({'board': board, 'ma20': ma20d, 'priceMa': priceMa, 'ma60': ma60d,
               'rsi': round(r, 1), 'vol': v, 'struct': struct, 'sector': sector,
               'atr': round(a, 2), 'score': total, 'win': round(win, 1),
               'entry': entry, 'stopPrice': round(entry * (1 - sp / 100), 2),
               'targetPrice': round(entry * (1 + tp / 100), 2),
               'date': DATE, 'category': 'final', 'bars': len(bars)})
    return it

def reason(it):
    b = ['MA20' + {'up': '向上', 'down': '向下', 'flat': '走平'}[it['ma20']],
         '股价' + ('站上' if it['priceMa'] == 'above' else '跌破') + 'MA20']
    if it['struct'] == 'breakout': b.append('平台突破')
    elif it['struct'] == 'pullback': b.append('回踩支撑')
    if it['vol'] == 'high': b.append('量能放大')
    b.append('RSI%s' % it['rsi'])
    if it['sector'] == 'strong': b.append('板块强势')
    return '；'.join(b)

# ================= MAIN =================
blob = json.load(open(SRC, encoding='utf-8'))
items = blob['items'] if isinstance(blob, dict) else blob
codes = [str(it['code']).strip() for it in items if it.get('code')]
print('候选池 %d 只' % len(items))

load_today_bars(codes)

added = 0; already = 0; missing = []
for it in items:
    c = str(it.get('code', '')).strip()
    day = it.get('kline', {}).get('day') or []
    if not day:
        missing.append(c); continue
    if day[-1][0] == DATE:
        already += 1; continue
    bar = TODAY_BAR.get(c)
    if not bar:
        missing.append(c); continue
    day.append(bar); added += 1
print('当日棒: 新增叠加 %d ｜ 原已含 %d ｜ 缺失 %d' % (added, already, len(missing)))
if missing:
    print('  缺当日棒(按 08-31 收盘评分): %s' % ', '.join(missing[:20]))

short = []
for it in items:
    day = it.get('kline', {}).get('day') or []
    if not day: it['win'] = 0.0; it['skipShort'] = True; continue
    score_item(it)
    if len(day) < MIN_BARS:
        short.append(it['code']); it['win'] = 0.0; it['skipShort'] = True
    else:
        it.pop('skipShort', None)

qual = [it for it in items if it.get('win', 0) >= 70 and not it.get('skipShort')]
qual.sort(key=lambda x: -x['win'])
print('重评分后达标: %d (次新剔除 %d)' % (len(qual), len(short)))

json.dump(blob, open(SRC, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('已写回', SRC)

# 指数
def tx_idx(sec):
    txt = get('https://qt.gtimg.cn/q=' + sec, enc='gbk')
    m = re.search(r'"([^"]+)"', txt)
    if not m: return None
    p = m.group(1).split('~')
    return p[1], round(float(p[3]), 2), round((float(p[3]) - float(p[4])) / float(p[4]) * 100, 2)

idx_info = {}
for sec, nm in [('sh000001', '上证指数'), ('sz399001', '深证成指'), ('sz399006', '创业板指')]:
    try:
        r = tx_idx(sec)
        if r: idx_info[nm] = r
    except Exception: pass
max_drop = min([v[2] for v in idx_info.values()], default=0)
idx_line = '、'.join(['%s %s（%s%%）' % (k, v[1], ('+' if v[2] >= 0 else '') + str(v[2])) for k, v in idx_info.items()])

BCN = {'main': '主板', 'cyb': '创业板', 'chuang': '科创板', 'kcb': '科创板'}
L = []
L.append('# A股稳健选股 · 盘后定稿（%s）' % DATE)
L.append('')
L.append('> 数据日：%s ｜ 生成时间：%s' % (DATE, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
L.append('> 数据源：腾讯行情（与 westock-mcp 同源公开端点，日K已叠加当日收盘棒）；评分引擎：6 维加权模型')
L.append('')
L.append('## 一、市场概览')
L.append('')
L.append('- 指数表现：%s' % (idx_line or '数据缺失'))
if max_drop <= -2:
    L.append('- ⚠️ **风险警示：当日大盘跌超 2%**，建议暂停新增候选，等待企稳。')
else:
    L.append('- 大盘波动处于常规区间（最大跌幅 %.2f%%），未触发强制暂停条件。' % max_drop)
L.append('')
L.append('## 二、达标候选（胜率 ≥ 70%，按胜率降序）')
L.append('')
L.append('共 **%d** 只达标（候选池 %d 只）。' % (len(qual), len(items)))
L.append('')
L.append('| 名称/代码 | 板块 | 综合分 | 胜率估算 | 现价 | 止损价 | 止盈价 | 入选理由 |')
L.append('| --- | --- | --- | --- | --- | --- | --- | --- |')
for it in qual[:10]:
    L.append('| %s %s | %s | %d | %.1f%% | %.2f | %.2f | %.2f | %s |' % (
        it['name'].split(' ')[0], it['code'], BCN.get(it['board'], it['board']),
        it['score'], it['win'], it['entry'], it['stopPrice'], it['targetPrice'], reason(it)))
L.append('')
L.append('## 三、前 3 名速览')
L.append('')
for it in qual[:3]:
    L.append('- **%s（%s，%s）** 综合分 %d / 胜率 %.1f%%：现价 %.2f，止损 %.2f / 止盈 %.2f。%s' % (
        it['name'].split(' ')[0], it['code'], BCN.get(it['board'], it['board']),
        it['score'], it['win'], it['entry'], it['stopPrice'], it['targetPrice'], reason(it)))
L.append('')
L.append('## 四、板块分布')
L.append('')
brd = {}
for it in qual: brd[BCN.get(it['board'], it['board'])] = brd.get(BCN.get(it['board'], it['board']), 0) + 1
L.append('- ' + '｜'.join(['%s %d 只' % (k, v) for k, v in sorted(brd.items(), key=lambda x: -x[1])]))
L.append('')
L.append('## 五、风险提示')
L.append('')
L.append('- 以上胜率为技术面 6 维模型估算，非收益承诺；仅作选股与提示，不下单、不交易。')
L.append('- 双创（创业板/科创板）止损/止盈放宽 50%（止损 3% / 止盈 9%），波动更大，仓位需控制。')
L.append('- 板块强度维度沿用系统既有评估（实时板块指数源暂未接入），如与当日盘面明显背离请以实盘为准。')
L.append('- 已按铁律剔除日K不足 %d 根的次新股（本次剔除 %d 只），避免 MA60/ATR 失真。' % (MIN_BARS, len(short)))
if missing:
    L.append('- 有 %d 只未取到当日收盘棒，其评分基于上一交易日收盘，已标注不臆造数据。' % len(missing))
L.append('- 达标数量偏多（%d 只）属技术面广度指标，实盘每周仅取 3-5 笔，请从前列择优并结合基本面复核。' % len(qual))
L.append('')
L.append('---')
L.append('*免责声明：以上内容由 AI 基于腾讯行情数据整理生成，仅供参考，不构成任何投资建议或个股推荐。投资有风险，决策需谨慎。*')
open(os.path.join(BASE, DATE + '.md'), 'w', encoding='utf-8').write('\n'.join(L))
print('已重写', os.path.join(BASE, DATE + '.md'))

print('=== SUMMARY ===')
print('total=%d qualified=%d todaybar_added=%d missing=%d maxdrop=%.2f' % (
    len(items), len(qual), added, len(missing), max_drop))
for it in qual[:5]:
    print('TOP %s %s win=%.1f score=%d entry=%.2f' % (it['code'], it['name'].split(' ')[0], it['win'], it['score'], it['entry']))
