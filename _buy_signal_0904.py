# -*- coding: utf-8 -*-
"""
买入信号生成 (2026-09-04 09:30 自动化)
与回测 backtest_winrate.js 同源：v1.0.4 全市场趋势+量能+缺口过滤 / v1.0.5 拉长历史 / v1.0.6 大盘硬过滤+同日上限3

⚠ 本环境 westock-mcp 不可用（Stock Analysis 技能为美股/港股专用，不适用 A 股）→ 沿用腾讯公开端点兜底：
   - 上证指数 / 个股日K：proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get (web.ifzq.gtimg.cn 曾整站 501)
   - 实时开盘价：qt.gtimg.cn/q= (gbk 解码)
⚠ import_final.json 仍陈旧（kline.day 末根 2026-09-01，updated 2026-08-28）：15:40 盘后定稿未刷新。
   为保持「信号日 = 前一交易日」与回测同源，重新拉取日K并丢弃当日盘中未完成棒，取 2026-09-03 完成棒作为基准日/信号日；
   候选排序仍沿用 import_final.json 的 win 字段（09-01 盘后评分，为当前可得最新）。
"""
import urllib.request, json, os, time, datetime

BASE = 'D:/WorkBuddy/选股结果'
SRC = os.path.join(BASE, 'import_final.json')
OUT = os.path.join(BASE, 'buy_signal.json')
TODAY = '2026-09-04'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
KL_HOST = 'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get'
MAX_BUY = 3          # ⑤ 同日上限
TOL_MAIN = 0.02
TOL_DYN = 0.03       # cyb/kcb 放宽 50%


def get(url, enc='utf-8', timeout=15, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': 'https://gu.qq.com/'})
            return urllib.request.urlopen(req, timeout=timeout).read().decode(enc, 'ignore')
        except Exception as e:
            last = e
            time.sleep(0.8 * (i + 1))
    raise last


def prefix(c):
    return 'sh' if str(c)[0] in '69' else 'sz'


def fetch_day(sym, start='2025-01-01', limit=800):
    u = '%s?param=%s,day,%s,%s,%d,qfq' % (KL_HOST, sym, start, TODAY, limit)
    d = json.loads(get(u))
    node = d['data'][sym]
    k = node.get('qfqday') or node.get('day') or []
    out = []
    for r in k:
        try:
            row = [r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])]
        except Exception:
            continue
        if row[0] >= TODAY:      # 丢弃当日盘中未完成棒
            continue
        out.append(row)
    return out


def qt_open(codes):
    """返回 {code: (open, date)}，取今日开盘价 f[5]，日期 f[30]"""
    res = {}
    syms = [prefix(c) + c for c in codes]
    for i in range(0, len(syms), 40):
        chunk = syms[i:i + 40]
        try:
            txt = get('https://qt.gtimg.cn/q=' + ','.join(chunk), enc='gbk')
        except Exception:
            continue
        for line in txt.split(';'):
            line = line.strip()
            if not line.startswith('v_'):
                continue
            try:
                f = line[line.index('"') + 1:line.rindex('"')].split('~')
                dt = f[30]
                d = dt[0:4] + '-' + dt[4:6] + '-' + dt[6:8]
                op = float(f[5])
                if op > 0:
                    res[f[2]] = (op, d)
            except Exception:
                continue
        time.sleep(0.15)
    return res


def sma(v, n):
    return None if len(v) < n else sum(v[-n:]) / n


# ---------- ⑤ 大盘硬过滤 ----------
try:
    idx = fetch_day('sh000001', start='2026-05-01', limit=120)
    assert idx, 'empty index'
except Exception as e:
    print('[⑤大盘] 上证日K获取失败 %r -> 写 trade:false' % e)
    result = {'date': TODAY, 'baselineDate': 'NA', 'top3': [],
              'trade': False, 'reason': '大盘数据获取失败(腾讯端点不可达)，当日不交易'}
    json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    raise SystemExit(0)

idx_closes = [r[2] for r in idx]
idx_last_date = idx[-1][0]
idx_last_close = idx_closes[-1]
idx_ma20 = sma(idx_closes, 20)
market_bull = idx_last_close >= idx_ma20
print('[⑤大盘] 上证末完成棒 %s 收 %.2f | MA20 %.2f | %s'
      % (idx_last_date, idx_last_close, idx_ma20, '多头' if market_bull else '空头'))

BASELINE_DATE = idx_last_date   # 前一交易日 = 信号日/基准日

# ---------- 候选池 ----------
data = json.load(open(SRC, encoding='utf-8'))
items = data.get('items') or []
pool_updated = data.get('updated')
ranked = sorted(items, key=lambda x: -(x.get('win') or 0))
print('[候选池] items=%d, updated=%s' % (len(items), pool_updated))
print('[排序前6]', [(x['code'], x.get('name'), x.get('win')) for x in ranked[:6]])

top = ranked[:MAX_BUY]

result = {'date': TODAY, 'baselineDate': BASELINE_DATE, 'top3': [], 'trade': False}

if not market_bull:
    result['reason'] = ('大盘空头(上证<MA20)：%s 收盘 %.2f < MA20 %.2f，当日全市场不交易'
                        % (idx_last_date, idx_last_close, idx_ma20))
    json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('[写出] trade=false 大盘空头')
    raise SystemExit(0)

# ---------- 逐个抓开盘价 + 过滤 ----------
codes = [x['code'] for x in top]
opens = qt_open(codes)
print('[开盘价] 抓到 %d/%d -> %s' % (len(opens), len(codes), opens))

for it in top:
    code = it['code']
    board = it.get('board') or 'main'
    tol = TOL_DYN if board in ('cyb', 'kcb', 'kc') else TOL_MAIN
    rec = {'code': code, 'name': it.get('name') or code, 'board': board,
           'win': it.get('win'), 'tol': tol}

    # 信号日日K（重新拉取，含 09-03 完成棒）
    try:
        day = fetch_day(prefix(code) + code)
    except Exception as e:
        day = []
        print('  ! %s 日K失败 %r' % (code, e))
    if len(day) < 21 or day[-1][0] != BASELINE_DATE:
        rec.update({'baseline': (day[-1][2] if day else None), 'open': None,
                    'dev': None, 'decision': 'hold',
                    'reason': '基准日K缺失或不对齐(末根=%s, 期望=%s)' % (day[-1][0] if day else 'NA', BASELINE_DATE)})
        result['top3'].append(rec)
        print('  %s %s -> hold (日K不对齐)' % (code, rec['name']))
        continue

    sig = day[-1]
    baseline = sig[2]
    rec['baseline'] = round(baseline, 3)

    op = opens.get(code, (None, None))
    if op[0] is None or op[1] != TODAY:
        rec.update({'open': None, 'dev': None, 'decision': 'hold',
                    'reason': '无法获取今日(09-04)开盘价(实得日期=%s)' % (op[1] if op else 'NA')})
        result['top3'].append(rec)
        print('  %s %s -> hold (无开盘价)' % (code, rec['name']))
        continue

    open_px = op[0]
    dev = (open_px - baseline) / baseline
    rec['open'] = round(open_px, 3)
    rec['dev'] = round(dev, 4)

    # 5a 容差
    if abs(dev) > tol:
        rec.update({'decision': 'hold',
                    'reason': '偏离超容差(dev=%.2f%% > ±%.0f%%)' % (dev * 100, tol * 100)})
        result['top3'].append(rec)
        print('  %s %s -> hold (超容差 dev=%.2f%%)' % (code, rec['name'], dev * 100))
        continue

    # 5b 全市场过滤
    closes = [r[2] for r in day]
    vols = [r[5] for r in day]
    close = sig[2]; s_open = sig[1]; s_vol = sig[5]
    prev_close = day[-2][2]
    ma5 = sma(closes, 5)
    ma20 = sma(closes, 20)
    ma20_prev = sma(closes[:-1], 20)
    ma20v = sma(vols, 20)
    trend_ok = (close > ma20) and (ma5 > ma20) and (ma20 > ma20_prev)
    vol_ok = s_vol >= 1.2 * ma20v
    gap = (s_open - prev_close) / prev_close
    gap_ok = (-0.04 <= gap <= 0.06)
    ok = trend_ok and vol_ok and gap_ok

    detail = ('趋势%s(C%.2f/MA20 %.2f, MA5 %.2f, MA20前 %.2f) 量能%s(%.0f vs 1.2xMA20量 %.0f) 缺口%s(%.2f%%)'
              % ('OK' if trend_ok else 'NG', close, ma20, ma5, ma20_prev,
                 'OK' if vol_ok else 'NG', s_vol, 1.2 * ma20v,
                 'OK' if gap_ok else 'NG', gap * 100))
    print('  %s %s base=%.2f open=%.2f dev=%.2f%% tol=%.0f%% | %s -> %s'
          % (code, rec['name'], baseline, open_px, dev * 100, tol * 100, detail,
             'BUY' if ok else 'hold'))

    if ok:
        rec['decision'] = 'buy'
    else:
        rec['decision'] = 'hold'
        why = []
        if not trend_ok: why.append('趋势不过')
        if not vol_ok: why.append('量能不足(%.0f<%.0f)' % (s_vol, 1.2 * ma20v))
        if not gap_ok: why.append('缺口越界(%.2f%%)' % (gap * 100))
        rec['reason'] = '过滤未过：' + '、'.join(why)
    result['top3'].append(rec)

buys = [x for x in result['top3'] if x['decision'] == 'buy']
result['trade'] = len(buys) > 0
result['reason'] = ('大盘多头(上证 %s 收 %.2f ≥ MA20 %.2f)；Top3 中 %d 笔通过容差+全市场过滤（同日上限 %d 笔）'
                    % (idx_last_date, idx_last_close, idx_ma20, len(buys), MAX_BUY))
if not result['trade']:
    result['reason'] += '；无标的同时满足容差与趋势/量能/缺口过滤，今日不交易'

assert len(buys) <= MAX_BUY, '超出同日上限'
json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('[写出] %s  trade=%s  buy=%d/%d' % (OUT, result['trade'], len(buys), len(result['top3'])))
