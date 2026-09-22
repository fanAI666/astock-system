# -*- coding: utf-8 -*-
"""
每日收盘选股定稿 (2026-09-14, 15:40)
- 刷新 import_final.json 中全部候选股日K线：用 proxy.finance.qq.com 镜像取近窗(保留3年历史)，按日期合并去重
- 叠加当日(09-14)收盘棒(qt.gtimg.cn 权威源)
- 基于含当日棒的日K重算 6 维评分 + 胜率估算
- 仅保留达标(胜率>=70%)标的 -> 写入 选股结果/2026-09-14.md
- 合并去重写回 import_final.json (候选池只增不减)
- 铁律: MIN_BARS=250 过滤次新股
"""
import urllib.request, json, os, datetime, time, re

BASE = 'D:/WorkBuddy/选股结果'
SRC = os.path.join(BASE, 'import_final.json')
TODAY = '2026-09-14'
WIN_START = '2026-08-20'   # 近窗起点，足够覆盖 09-11 之后新增棒
WIN_COUNT = 40             # 近窗取最近 40 根
MIN_BARS = 250
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

def fetch_recent(code):
    """取近窗日K(最新在前)，返回 [date,open,last,high,low,volume] 老->新；None 表示失败/空。"""
    full = prefix(code) + code
    url = 'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get?param=%s,day,%s,%s,%d,qfq' % (
        full, WIN_START, TODAY, WIN_COUNT)
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
    out.sort(key=lambda x: x[0])  # 老->新
    return out

TODAY_BAR = {}
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
            if not line.startswith('v_'):
                continue
            try:
                sym = line[2:line.index('=')]
                body = line[line.index('"')+1:line.rindex('"')]
                f = body.split('~')
                dt = f[30]
                d = dt[0:4] + '-' + dt[4:6] + '-' + dt[6:8]
                if d != TODAY:
                    continue
                price = float(f[3]); openp = float(f[5])
                high = float(f[33]); low = float(f[34]); vol = float(f[36])
                if price <= 0:
                    continue
                TODAY_BAR[sym[2:]] = [TODAY, openp, price, high, low, vol]
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

def board_of(code):
    c = str(code).strip()
    if c.startswith('300'): return 'cyb'
    if c.startswith('688'): return 'kcb'
    return 'main'

def stop_tgt_params(code):
    b = board_of(code)
    if b in ('cyb', 'kcb'): return 3.0, 9.0, b
    return 2.0, 6.0, 'main'

def score_item(item):
    code = item['code']; bars = item['kline']['day']
    closes = [b[2] for b in bars]
    ma20v = sma(closes, 20)
    ma20d = ma_dir(closes, 20); ma60d = ma_dir(closes, 60)
    priceMa = 'above' if (ma20v and closes[-1] >= ma20v) else 'below'
    r = rsi(closes); a = atr_pct(bars); v = vol_class(bars)
    struct = classify_struct(closes, ma20v, priceMa)
    sector = item.get('sector', 'mid')
    sp, tp, board = stop_tgt_params(code)

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
    item.update({'board': board, 'ma20': ma20d, 'priceMa': priceMa, 'ma60': ma60d,
                 'rsi': round(r, 1), 'vol': v, 'struct': struct, 'sector': sector,
                 'atr': round(a, 2), 'score': total, 'win': round(win, 1),
                 'entry': entry, 'stopPrice': round(entry * (1 - sp / 100), 2),
                 'targetPrice': round(entry * (1 + tp / 100), 2),
                 'date': TODAY, 'category': 'final', 'bars': len(bars)})
    return item

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

ok = 0; fail = 0; missing = []
for idx, it in enumerate(items):
    code = it.get('code')
    if not code:
        m = re.search(r'(\d{6})', it.get('name', ''))
        if m: code = m.group(1); it['code'] = code
        else: fail += 1; continue
    base = (it.get('kline', {}) or {}).get('day') or []
    try:
        recent = fetch_recent(code)
    except Exception as e:
        print('  K线失败 %s: %s' % (code, e)); fail += 1
        if not base:
            it.setdefault('kline', {})['day'] = []
            missing.append(code)
        continue
    if not recent:
        print('  K线为空 %s' % code); fail += 1
        if not base:
            it.setdefault('kline', {})['day'] = []
            missing.append(code)
        continue
    # 历史保留合并：base 旧历史 + recent 近窗覆盖（按日期去重）
    merged = {}
    for b in base: merged[b[0]] = b
    for b in recent: merged[b[0]] = b
    day = [merged[k] for k in sorted(merged)]
    it.setdefault('kline', {})['day'] = day
    ok += 1
    if (idx + 1) % 40 == 0:
        print('  进度 %d/%d' % (idx + 1, len(items)))
    time.sleep(0.05)

print('K线刷新成功 %d / 失败 %d' % (ok, fail))

# 叠加当日收盘棒
codes = [str(it.get('code', '')).strip() for it in items if it.get('code')]
load_today_bars(codes)
added = 0; replaced = 0; already = 0; nobar = 0
for it in items:
    c = str(it.get('code', '')).strip()
    day = it.get('kline', {}).get('day') or []
    if not day: continue
    bar = TODAY_BAR.get(c)
    if day[-1][0] == TODAY:
        if bar:
            day[-1] = bar; replaced += 1
        else:
            already += 1
    elif bar:
        day.append(bar); added += 1
    else:
        nobar += 1
print('当日棒: 新增叠加 %d ｜ 替换 %d ｜ 原已含 %d ｜ 无棒 %d' % (added, replaced, already, nobar))

# 评分 + 次新过滤
short_list = []
for it in items:
    day = it.get('kline', {}).get('day') or []
    if not day:
        it['win'] = 0.0; it['skipShort'] = True; continue
    score_item(it)
    if len(day) < MIN_BARS:
        short_list.append('%s(%d根)' % (it['code'], len(day)))
        it['win'] = 0.0; it['skipShort'] = True
    else:
        it.pop('skipShort', None)

qualified = [it for it in items if it.get('win', 0) >= 70 and not it.get('skipShort')]
qualified.sort(key=lambda x: -x.get('win', 0))
print('达标数量:', len(qualified))

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
    except Exception:
        pass
max_drop = min([v[2] for v in idx_info.values()], default=0)
idx_line = '、'.join(['%s %s（%s%%）' % (k, v[1], ('+' if v[2] >= 0 else '') + str(v[2])) for k, v in idx_info.items()])

# 每周笔数闸门(步骤8)：本周一=2026-09-14
week_buys = 0
try:
    led = json.load(open(os.path.join(BASE, 'signal_ledger.json'), encoding='utf-8'))
    for dstr, v in led.get('days', {}).items():
        if dstr >= '2026-09-14':
            week_buys += int(v.get('buys', 0))
    for e in led.get('entries', []):
        if e.get('date', '') >= '2026-09-14':
            week_buys += 1
except Exception as e:
    print('LEDGER ERR', e)
week_gate = week_buys > 5

data['updated'] = TODAY
with open(SRC, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print('已写回', SRC)

BOARD_CN = {'main': '主板', 'cyb': '创业板', 'chuang': '科创板', 'kcb': '科创板'}
lines = []
lines.append('# A股稳健选股 · 盘后定稿（%s）' % TODAY)
lines.append('')
lines.append('> 数据日：%s ｜ 生成时间：%s' % (TODAY, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
lines.append('> 数据源：腾讯行情（proxy.finance.qq.com 镜像 + qt.gtimg.cn 当日收盘棒，与 westock-mcp 同源公开端点；日K已叠加当日 %s 收盘棒）；评分引擎：6 维加权模型' % TODAY)
lines.append('')
lines.append('## 一、市场概览')
lines.append('')
lines.append('- 指数表现：%s' % (idx_line or '数据缺失'))
if max_drop <= -2:
    lines.append('- ⚠️ **风险警示：当日大盘跌超 2%**，建议暂停新增候选，等待企稳。')
elif week_gate:
    lines.append('- ⚠️ **本周已成交 %d 笔（>5 笔上限）**，建议暂停新增候选，控制节奏。' % week_buys)
else:
    lines.append('- 大盘波动处于常规区间（最大跌幅 %.2f%%），未触发强制暂停条件。' % max_drop)
lines.append('- 本周成交笔数（含今日，据 signal_ledger）：%d 笔（上限 5 笔）。' % week_buys)
lines.append('')
lines.append('## 二、达标候选（胜率 ≥ 70%，按胜率降序）')
lines.append('')
lines.append('共 **%d** 只达标（候选池 %d 只）。' % (len(qualified), len(items)))
lines.append('')
lines.append('| 名称/代码 | 板块 | 综合分 | 胜率估算 | 现价 | 止损价 | 止盈价 | 入选理由 |')
lines.append('| --- | --- | --- | --- | --- | --- | --- | --- |')
for it in qualified[:10]:
    lines.append('| %s %s | %s | %d | %.1f%% | %.2f | %.2f | %.2f | %s |' % (
        it['name'].split(' ')[0], it['code'], BOARD_CN.get(it['board'], it['board']),
        it['score'], it['win'], it['entry'], it['stopPrice'], it['targetPrice'], reason(it)))
lines.append('')
lines.append('## 三、前 3 名速览')
lines.append('')
for it in qualified[:3]:
    lines.append('- **%s（%s，%s）** 综合分 %d / 胜率 %.1f%%：现价 %.2f，止损 %.2f / 止盈 %.2f。%s' % (
        it['name'].split(' ')[0], it['code'], BOARD_CN.get(it['board'], it['board']),
        it['score'], it['win'], it['entry'], it['stopPrice'], it['targetPrice'], reason(it)))
lines.append('')
lines.append('## 四、板块分布')
lines.append('')
brd = {}
for it in qualified: brd[BOARD_CN.get(it['board'], it['board'])] = brd.get(BOARD_CN.get(it['board'], it['board']), 0) + 1
lines.append('- ' + '｜'.join(['%s %d 只' % (k, v) for k, v in sorted(brd.items(), key=lambda x: -x[1])]))
lines.append('')
lines.append('## 五、风险提示')
lines.append('')
lines.append('- 以上胜率为技术面 6 维模型估算，非收益承诺；仅作选股与提示，不下单、不交易。')
lines.append('- 双创（创业板/科创板）止损/止盈放宽 50%（止损 3% / 止盈 9%），波动更大，仓位需控制。')
lines.append('- 板块强度维度沿用系统既有评估（实时板块指数源暂未接入），如与当日盘面明显背离请以实盘为准。')
lines.append('- 已按铁律剔除日K不足 %d 根的次新股（本次剔除 %d 只），避免 MA60/ATR 失真。' % (MIN_BARS, len(short_list)))
if missing:
    lines.append('- 有 %d 只未取到日K线，已标注不臆造数据。' % len(missing))
lines.append('- 达标数量偏多（%d 只）属技术面广度指标，实盘每周仅取 3-5 笔，请从前列择优并结合基本面复核。' % len(qualified))
lines.append('- 本清单为盘后观察候选，非实盘指令；仅 9:30 买入信号自动化在满足条件时触发交易。')
lines.append('')
lines.append('---')
lines.append('*免责声明：以上内容由 AI 基于腾讯行情数据整理生成，仅供参考，不构成任何投资建议或个股推荐。投资有风险，决策需谨慎。*')
md = '\n'.join(lines)
md_path = os.path.join(BASE, TODAY + '.md')
with open(md_path, 'w', encoding='utf-8') as f:
    f.write(md)
print('已写出', md_path)

print('=== SUMMARY ===')
print('total=%d qualified=%d added=%d replaced=%d nobar=%d missing=%d short=%d maxdrop=%.2f week_buys=%d' % (
    len(items), len(qualified), added, replaced, nobar, len(missing), len(short_list), max_drop, week_buys))
last_dates = [it.get('kline',{}).get('day',[['']])[-1][0] for it in items if it.get('kline',{}).get('day')]
print('末根日期覆盖 %d/%d == %s' % (sum(1 for d in last_dates if d==TODAY), len(last_dates), TODAY))
for it in qualified[:5]:
    print('TOP %s %s win=%.1f score=%d entry=%.2f' % (it['code'], it['name'].split(' ')[0], it['win'], it['score'], it['entry']))
