# -*- coding: utf-8 -*-
"""四方一致性核验 2026-09-11"""
import json, os, re, collections

BASE = 'D:/WorkBuddy/选股结果'
TODAY = '2026-09-11'

d = json.load(open(os.path.join(BASE, 'import_final.json'), encoding='utf-8'))
items = d['items'] if isinstance(d, dict) else d
total = len(items)

q = [it for it in items if it.get('date') == TODAY and it.get('win', 0) >= 70 and not it.get('skipShort')]
n_import = len(q)

md = open(os.path.join(BASE, TODAY + '.md'), encoding='utf-8').read()
m = re.search(r'共 \*\*(\d+)\*\* 只达标', md)
n_md = int(m.group(1)) if m else -1

bf = json.load(open(os.path.join(BASE, 'briefing_final.json'), encoding='utf-8'))
bdate = bf.get('date')

lasts = [it['kline']['day'][-1][0] for it in items if it.get('kline', {}).get('day')]
cov = sum(1 for x in lasts if x == TODAY)

m5days = []
for it in items:
    m5 = it.get('kline', {}).get('min5') or []
    m5days.append(len(set(r[0][:8] for r in m5 if r and r[0])))
avg_m5 = sum(m5days) / len(m5days) if m5days else 0
m5_ok = sum(1 for x in m5days if x >= 5)

ff = json.load(open(os.path.join(BASE, 'fundflow.json'), encoding='utf-8'))

brd = collections.Counter(it.get('board') for it in q)

print('=' * 56)
print('四方一致性核验  (%s)' % TODAY)
print('=' * 56)
print('1) import_final 达标数 (date=%s, win>=70, 非skipShort) : %d' % (TODAY, n_import))
print('2) MD 达标数 N                                        : %d' % n_md)
print('3) briefing_final.date                                 : %s' % bdate)
print('4) 日K末根 == %s 覆盖                              : %d/%d' % (TODAY, cov, total))
print('-' * 56)
ok1 = (n_import == n_md)
ok2 = (bdate == TODAY)
ok3 = (cov == total)
print('   [%s] 校验1 import_final == MD' % ('PASS' if ok1 else 'FAIL'))
print('   [%s] 校验2 briefing_final.date == 当日' % ('PASS' if ok2 else 'FAIL'))
print('   [%s] 校验3 日K全覆盖' % ('PASS' if ok3 else 'FAIL'))
print('-' * 56)
print('体检 min5: 平均交易日 %.1f ｜ >=5日覆盖 %d/%d' % (avg_m5, m5_ok, len(m5days)))
print('体检 fundflow: indices=%d styleFactors=%d heatSectors=%d fundFlow=%d recommendations=%d' % (
    len(ff.get('indices', [])), len(ff.get('styleFactors', [])), len(ff.get('heatSectors', [])),
    len(ff.get('fundFlow', [])), len(ff.get('recommendations', []))))
print('体检 板块分布: %s' % dict(brd))
print('体检 候选池总数: %d (只增不减)' % total)
print('=' * 56)
print('OVERALL: %s' % ('ALL PASS' if (ok1 and ok2 and ok3) else 'CHECK FAILED'))
