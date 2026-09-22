# -*- coding: utf-8 -*-
"""盘后四方一致性核验 (2026-09-01)"""
import json, os, re
BASE = 'D:/WorkBuddy/选股结果'
TODAY = '2026-09-01'
TODAY_C = TODAY.replace('-', '')

d = json.load(open(os.path.join(BASE, 'import_final.json'), 'r', encoding='utf-8'))
items = d['items'] if isinstance(d, dict) else d
today_items = [i for i in items if i.get('date') == TODAY]
qual = [i for i in today_items if i.get('win', 0) >= 70 and not i.get('skipShort')]

day_ok = sum(1 for i in items if len(i.get('kline', {}).get('day') or []) >= 250)
day_today = sum(1 for i in items if (i.get('kline', {}).get('day') or [])
                and i['kline']['day'][-1][0] == TODAY)
m5_ok = 0; m5_days = []; m5_today = 0; m5_bars = 0
for i in items:
    m5 = i.get('kline', {}).get('min5') or []
    if m5:
        m5_ok += 1; m5_bars += len(m5)
        ds = set(x[0].split(' ')[0] for x in m5)
        m5_days.append(len(ds))
        if any(x[0].startswith(TODAY_C) for x in m5): m5_today += 1
avg = sum(m5_days) / len(m5_days) if m5_days else 0

print('=== import_final.json ===')
print('候选池总数 %d ｜ 本日重评分 %d ｜ 本日达标 %d' % (len(items), len(today_items), len(qual)))
print('日K >=250根 %d/%d ｜ 末根含当日 %d/%d' % (day_ok, len(items), day_today, len(items)))
print('min5 非空 %d/%d ｜ 平均覆盖交易日 %.1f ｜ 含当日 %d ｜ 总根数 %d' % (
    m5_ok, len(items), avg, m5_today, m5_bars))
sample = items[0]
print('样本 %s: day末根=%s ｜ min5末根=%s' % (
    sample['code'], sample['kline']['day'][-1], (sample['kline'].get('min5') or [['-']])[-1]))

print('=== briefing_final.json ===')
b = json.load(open(os.path.join(BASE, 'briefing_final.json'), encoding='utf-8'))
print('date=%s ｜ warning=%s' % (b.get('date'), b.get('warning')))

print('=== %s.md ===' % TODAY)
md = open(os.path.join(BASE, TODAY + '.md'), encoding='utf-8').read()
m = re.search(r'共 \*\*(\d+)\*\* 只达标', md)
md_n = int(m.group(1)) if m else -1
print('声明达标数 %d ｜ 残留转义 %s' % (md_n, '有' if '%%' in md else '无'))

print('=== fundflow.json ===')
ff = json.load(open(os.path.join(BASE, 'fundflow.json'), encoding='utf-8'))
print('updatedAt=%s' % ff.get('updatedAt'))
print('indices=%d ｜ styleFactors=%d ｜ heatSectors=%d ｜ fundFlow=%d ｜ recs=%d' % (
    len(ff.get('indices') or []), len(ff.get('styleFactors') or []),
    len(ff.get('heatSectors') or []), len(ff.get('fundFlow') or []),
    len(ff.get('recommendations') or [])))
print('资金主线:', ff.get('fundThread'))
print('行业主力净流入 TOP5:')
for s in (ff.get('fundFlow') or [])[:5]:
    print('   %-8s 净额 %+.1f亿' % (s.get('sector'), s.get('net', 0)))
print('风格因子:', ' ｜ '.join('%s %s' % (s['name'], s['score']) for s in (ff.get('styleFactors') or [])))
print('北向:', (ff.get('northFlow') or {}).get('note', ''))
for r in (ff.get('recommendations') or []):
    print('研判[%s] %s — %s' % (r.get('tag'), r.get('title'), r.get('reason')))

print('=== 四方一致性 ===')
print('OK' if (md_n == len(qual) and b.get('date') == TODAY and day_today == len(items))
      else 'FAIL 需检查')

print('=== 达标 TOP12 ===')
qual.sort(key=lambda x: -x['win'])
for i in qual[:12]:
    print('%-10s %s %-4s 分%-3d 胜%.1f%% 现%.2f 损%.2f 盈%.2f ATR%.2f%% RSI%.1f' % (
        i['name'].split(' ')[0], i['code'], i['board'], i['score'], i['win'],
        i['entry'], i['stopPrice'], i['targetPrice'], i['atr'], i['rsi']))
brd = {}
for i in qual: brd[i['board']] = brd.get(i['board'], 0) + 1
print('板块分布:', brd)
