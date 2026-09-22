# -*- coding: utf-8 -*-
"""四方一致性核验 + 关键字段抽查 (2026-09-12 周六运行, 数据日 2026-09-11)"""
import json, os, datetime
BASE = 'D:/WorkBuddy/选股结果'
TODAY = '2026-09-11'

data = json.load(open(os.path.join(BASE, 'import_final.json'), encoding='utf-8'))
items = data['items'] if isinstance(data, dict) else data
print('候选池总数:', len(items))

# qualified (win>=70, 非次新, 非跳过)
q = [it for it in items if it.get('win', 0) >= 70 and not it.get('skipShort')]
print('import_final 达标数:', len(q))
print('前3:', '、'.join(['%s %s(win=%.1f)' % (it['code'], it['name'].split(' ')[0], it['win']) for it in q[:3]]))

# 末根日期覆盖
last = [it.get('kline', {}).get('day', [['']])[-1][0] for it in items if it.get('kline', {}).get('day')]
cov = sum(1 for d in last if d == TODAY)
print('末根日期==%s: %d/%d' % (TODAY, cov, len(last)))

# min5 覆盖
m5 = [(it.get('code'), len(it.get('kline', {}).get('min5', []) or [])) for it in items]
good = sum(1 for c, n in m5 if n >= 200)
print('min5 覆盖(>=200根, 约5日): %d/%d ; 平均 %.1f 根' % (good, len(m5), sum(n for _, n in m5)/max(1,len(m5))))
empties = [c for c, n in m5 if n == 0]
print('min5 为空:', empties[:10], '...共', len(empties) if empties else 0)

# category 字段一致性
cats = set(it.get('category') for it in items)
print('category 取值:', cats)

# MD 达标数
md = open(os.path.join(BASE, TODAY + '.md'), encoding='utf-8').read()
import re
m = re.search(r'共 \*\*(\d+)\*\* 只达标', md)
print('MD 达标数 N =', m.group(1) if m else 'N/A')

# briefing
bf = json.load(open(os.path.join(BASE, 'briefing_final.json'), encoding='utf-8'))
print('briefing_final.date =', bf.get('date'), '(应==%s)' % TODAY, '| warning=', bf.get('warning'))

# fundflow
ff = json.load(open(os.path.join(BASE, 'fundflow.json'), encoding='utf-8'))
print('fundflow: indices=%d style=%d heat=%d fundFlow=%d north.todayNet=%s recs=%d' % (
    len(ff.get('indices', [])), len(ff.get('styleFactors', [])), len(ff.get('heatSectors', [])),
    len(ff.get('fundFlow', [])), ff.get('northFlow', {}).get('todayNet'), len(ff.get('recommendations', []))))

# max drop / week gate
idx_line = md
print('---- 核验完成 ----')
