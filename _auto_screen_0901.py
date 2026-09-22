# -*- coding: utf-8 -*-
"""
每日收盘选股定稿 (2026-09-01)
- 刷新 import_final.json 中全部候选股的日K线(≈800根, 含当日 09-01)
- 基于最新 K 线重算 6 维评分 + 胜率估算
- 仅保留达标(胜率>=70%)标的 -> 写入 选股结果/YYYY-MM-DD.md
- 合并去重写回 import_final.json (候选池只增不减)
- 数据源: 腾讯公开端点(与 westock-mcp 同源): web.ifzq.gtimg.cn fqkline, qt.gtimg.cn quote
- 铁律: MIN_BARS=250 过滤次新股(日K不足1年者不进达标清单)
"""
import urllib.request, json, os, datetime, time, re

BASE = 'D:/WorkBuddy/选股结果'
SRC = os.path.join(BASE, 'import_final.json')
TODAY = '2026-09-01'
MIN_BARS = 250          # 次新股过滤铁律
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

def get(url, enc='utf-8', timeout=12, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': 'https://gu.qq.com/'})
            return urllib.request.urlopen(req, timeout=timeout).read().decode(enc, 'ignore')
        except Exception as e:
            last = e
            time.sleep(0.8 * (i + 1))
    raise last

def prefix(code):
    c = str(code).strip()
    return 'sh' if c[0] in '69' else 'sz'

def tx_quote(sec):
    txt = get('https://qt.gtimg.cn/q=' + sec, enc='gbk')
    m = re.search(r'"([^"]+)"', txt)
    if not m: return None
    p = m.group(1).split('~')
    try:
        name = p[1]; price = float(p[3]); prev = float(p[4])
        return name, round(price, 2), round((price - prev) / prev * 100, 2)
    except Exception:
        return None

def fetch_day(code):
    full = prefix(code) + code
    url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s,day,2023-01-01,%s,800,qfq' % (full, TODAY)
    j = json.loads(get(url))
    node = j.get('data', {}).get(full, {})
    arr = node.get('qfqday') or node.get('day')
    if not arr:
        return None
    out = []
    for r in arr:
        if len(r) < 6:
            continue
        out.append([r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])])
    return out  # [date, open, last, high, low, volume]

def sma(vals, n):
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n

def ma_dir(closes, n):
    cur = sma(closes, n)
    prev = sma(closes[:-5], n) if len(closes) > n + 5 else None
    if cur is None or prev is None:
        return 'flat'
    if cur > prev * 1.001: return 'up'
    if cur < prev * 0.999: return 'down'
    return 'flat'

def rsi(closes, n=14):
    if len(closes) < n + 1:
        return 50.0
    gains = []; losses = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    g = sum(gains[-n:]) / n; l = sum(losses[-n:]) / n
    if l == 0:
        return 100.0
    rs = g / l
    return 100 - 100 / (1 + rs)

def atr_pct(bars, n=14):
    if len(bars) < n + 1:
        return 3.0
    tr = []
    for i in range(1, len(bars)):
        h = bars[i][3]; l = bars[i][4]; pc = bars[i-1][2]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    a = sum(tr[-n:]) / n
    return a / bars[-1][2] * 100

def vol_class(bars):
    if len(bars) < 21:
        return 'normal'
    vnow = bars[-1][5]; vma = sma([b[5] for b in bars], 20)
    if vma in (None, 0): return 'normal'
    r = vnow / vma
    if r > 1.5: return 'high'
    if r < 0.7: return 'low'
    return 'normal'

def stop_tgt_params(item, code):
    board = item.get('board', '')
    if board in ('cyb', 'chuang') or str(code).startswith(('300', '688')):
        return 0.03, 0.09, board or 'cyb'
    return 0.02, 0.06, board or 'main'

def classify_struct(closes, ma20v, priceMa):
    if len(closes) < 21:
        return 'none'
    prior_high = max(closes[-21:-1])
    if closes[-1] > prior_high and priceMa == 'above':
        return 'breakout'
    if priceMa == 'above' and ma20v and (ma20v * 0.97 <= closes[-1] <= ma20v * 1.02):
        return 'pullback'
    return 'none'

def score_item(item):
    code = item['code']
    bars = item['kline']['day']
    closes = [b[2] for b in bars]
    ma20v = sma(closes, 20); ma60v = sma(closes, 60)
    ma20d = ma_dir(closes, 20); ma60d = ma_dir(closes, 60)
    priceMa = 'above' if (ma20v and closes[-1] >= ma20v) else 'below'
    r = rsi(closes)
    a = atr_pct(bars)
    v = vol_class(bars)
    struct = classify_struct(closes, ma20v, priceMa)
    sector = item.get('sector', 'mid')  # 板块强度沿用系统既有评估(无实时板块指数源)
    sp, tp, board = stop_tgt_params(item, code)

    s_trend = (10 if ma20d == 'up' else 5 if ma20d == 'flat' else 0) \
              + (8 if priceMa == 'above' else 0) \
              + (7 if ma60d == 'up' else 3 if ma60d == 'flat' else 0)
    s_struct = 20 if struct == 'breakout' else 10 if struct == 'pullback' else 0
    s_vol = 15 if v == 'high' else 8 if v == 'normal' else 0
    s_sector = 15 if sector == 'strong' else 8 if sector == 'mid' else 0
    if 45 <= r <= 65: s_rsi = 15
    elif 35 <= r <= 75: s_rsi = 8
    else: s_rsi = 0
    if a <= sp * 100 * 1.2: s_atr = 10
    elif a <= sp * 100 * 1.8: s_atr = 5
    else: s_atr = 0

    total = s_trend + s_struct + s_vol + s_sector + s_rsi + s_atr
    win = min(88.0, 50 + total * 0.35)
    entry = round(closes[-1], 2)
    stopP = round(entry * (1 - sp), 2)
    tgtP = round(entry * (1 + tp), 2)

    item.update({
        'board': board, 'ma20': ma20d, 'priceMa': priceMa, 'ma60': ma60d,
        'rsi': round(r, 1), 'vol': v, 'struct': struct, 'sector': sector,
        'atr': round(a, 2), 'score': total, 'win': round(win, 1),
        'entry': entry, 'stopPrice': stopP, 'targetPrice': tgtP,
        'date': TODAY, 'category': 'final', 'bars': len(bars)
    })
    return item, win

def reason(item):
    bits = []
    bits.append('MA20' + {'up': '向上', 'down': '向下', 'flat': '走平'}[item['ma20']])
    bits.append('股价' + ('站上' if item['priceMa'] == 'above' else '跌破') + 'MA20')
    if item['struct'] == 'breakout': bits.append('平台突破')
    elif item['struct'] == 'pullback': bits.append('回踩支撑')
    if item['vol'] == 'high': bits.append('量能放大')
    bits.append('RSI%s' % item['rsi'])
    if item['sector'] == 'strong': bits.append('板块强势')
    return '；'.join(bits)

# ================= MAIN =================
print('读取', SRC)
with open(SRC, 'r', encoding='utf-8') as f:
    data = json.load(f)
items = data['items'] if isinstance(data, dict) else data
print('候选总数:', len(items))

ok = 0; fail = 0; short_list = []
for idx, it in enumerate(items):
    code = it.get('code')
    if not code:
        m = re.search(r'(\d{6})', it.get('name', ''))
        if m:
            code = m.group(1); it['code'] = code
        else:
            fail += 1; continue
    try:
        day = fetch_day(code)
    except Exception as e:
        print('  K线失败 %s: %s' % (code, e)); fail += 1; continue
    if not day:
        print('  K线为空 %s' % code); fail += 1
        it.setdefault('kline', {}).setdefault('day', [])
        continue
    it.setdefault('kline', {})['day'] = day
    score_item(it)
    if len(day) < MIN_BARS:
        short_list.append('%s(%d根)' % (code, len(day)))
        it['win'] = 0.0
        it['skipShort'] = True
    else:
        it.pop('skipShort', None)
    ok += 1
    if (idx + 1) % 40 == 0:
        print('  进度 %d/%d' % (idx + 1, len(items)))
    time.sleep(0.05)

print('K线刷新成功 %d / 失败 %d' % (ok, fail))
if short_list:
    print('SKIP_SHORT(次新股剔除 %d 只): %s' % (len(short_list), ', '.join(short_list)))

qualified = [it for it in items if it.get('win', 0) >= 70 and not it.get('skipShort')]
qualified.sort(key=lambda x: -x.get('win', 0))
print('达标数量:', len(qualified))

idx_info = {}
for sec, nm in [('sh000001', '上证指数'), ('sz399001', '深证成指'), ('sz399006', '创业板指')]:
    try:
        r = tx_quote(sec)
        if r: idx_info[nm] = r
    except Exception:
        pass
max_drop = min([v[2] for v in idx_info.values()], default=0)
idx_line = '、'.join(['%s %s%%' % (k, ('+' if v[2] >= 0 else '') + str(v[2])) for k, v in idx_info.items()])

with open(SRC, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print('已写回', SRC)

BOARD_CN = {'main': '主板', 'cyb': '创业板', 'chuang': '科创板', 'kcb': '科创板'}
lines = []
lines.append('# A股稳健选股 · 盘后定稿（%s）' % TODAY)
lines.append('')
lines.append('> 数据日：%s ｜ 生成时间：%s' % (TODAY, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
lines.append('> 数据源：腾讯行情（与 westock-mcp 同源公开端点）；评分引擎：6 维加权模型')
lines.append('')
lines.append('## 一、市场概览')
lines.append('')
lines.append('- 指数表现：%s' % (idx_line or '数据缺失'))
if max_drop <= -2:
    lines.append('- ⚠️ **风险警示：当日大盘跌超 2%**，建议暂停新增候选，等待企稳。')
else:
    lines.append('- 大盘波动处于常规区间，未触发强制暂停条件。')
lines.append('')
lines.append('## 二、达标候选（胜率 ≥ 70%，按胜率降序）')
lines.append('')
lines.append('共 **%d** 只达标（候选池 %d 只）。' % (len(qualified), len(items)))
lines.append('')
lines.append('| 名称/代码 | 板块 | 综合分 | 胜率估算 | 止损价 | 止盈价 | 入选理由 |')
lines.append('| --- | --- | --- | --- | --- | --- | --- |')
for it in qualified[:10]:
    board = BOARD_CN.get(it['board'], it['board'])
    lines.append('| %s %s | %s | %d | %.1f%% | %.2f | %.2f | %s |' % (
        it['name'].split(' ')[0], it['code'], board, it['score'], it['win'],
        it['stopPrice'], it['targetPrice'], reason(it)))
lines.append('')
lines.append('## 三、前 3 名速览')
lines.append('')
for it in qualified[:3]:
    board = BOARD_CN.get(it['board'], it['board'])
    lines.append('- **%s（%s，%s）** 综合分 %d / 胜率 %.1f%%：现价 %.2f，止损 %.2f / 止盈 %.2f。%s' % (
        it['name'].split(' ')[0], it['code'], board, it['score'], it['win'],
        it['entry'], it['stopPrice'], it['targetPrice'], reason(it)))
lines.append('')
lines.append('## 四、风险提示')
lines.append('')
lines.append('- 以上胜率为技术面 6 维模型估算，非收益承诺；仅作选股与提示，不下单、不交易。')
lines.append('- 双创（创业板/科创板）止损/止盈放宽 50%（止损 3% / 止盈 9%），波动更大，仓位需控制。')
lines.append('- 板块强度维度沿用系统既有评估（实时板块指数源暂未接入），如与当日盘面明显背离请以实盘为准。')
lines.append('- 已按铁律剔除日K不足 %d 根的次新股（本次剔除 %d 只），避免 MA60/ATR 失真。' % (MIN_BARS, len(short_list)))
lines.append('- 本清单由自动化在收盘后生成，需经人工复核后再决定是否纳入实盘观察。')
lines.append('')
lines.append('---')
lines.append('*免责声明：以上内容由 AI 基于腾讯行情数据整理生成，仅供参考，不构成任何投资建议或个股推荐。投资有风险，决策需谨慎。*')
md = '\n'.join(lines)
md_path = os.path.join(BASE, TODAY + '.md')
with open(md_path, 'w', encoding='utf-8') as f:
    f.write(md)
print('已写出', md_path)

print('=== SUMMARY ===')
print('total=%d qualified=%d skipshort=%d max_drop=%.2f idx=%s' % (len(items), len(qualified), len(short_list), max_drop, idx_line))
for it in qualified[:5]:
    print('TOP %s %s win=%.1f score=%d entry=%.2f' % (it['code'], it['name'].split(' ')[0], it['win'], it['score'], it['entry']))
