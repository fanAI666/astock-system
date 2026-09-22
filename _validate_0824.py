# -*- coding: utf-8 -*-
"""Validate the existing 2026-08-21 finalized deliverables (intraday 08-24 trigger -> deliver existing)."""
import json, os, sys

DIR = 'D:/WorkBuddy/选股结果'

def load(name):
    with open(os.path.join(DIR, name), 'r', encoding='utf-8') as f:
        return json.load(f)

print('=' * 60)
print('VALIDATE import_final.json')
imp = load('import_final.json')
items = imp['items'] if isinstance(imp, dict) and 'items' in imp else imp
print('top-level type:', type(imp).__name__, '| items:', len(items))
boards = {}
dates = {}
miss_day = miss_min5 = miss_score = 0
bad_stop = 0
dated_pass = []
for it in items:
    b = it.get('board'); dates[it.get('date')] = dates.get(it.get('date'),0)+1
    boards[b] = boards.get(b,0)+1
    kl = it.get('kline') or {}
    if not (kl.get('day')): miss_day += 1
    if not (kl.get('min5')): miss_min5 += 1
    if 'score' not in it: miss_score += 1
    if it.get('date') == '2026-08-21':
        dated_pass.append(it)
        # stop/target math check
        try:
            entry = float(it['entry']); stop = float(it['stopPrice']); tgt = float(it['targetPrice'])
            if b in ('cyb','kcb'):
                exp_stop = round(entry*0.97,2); exp_tgt = round(entry*1.09,2)
            else:
                exp_stop = round(entry*0.98,2); exp_tgt = round(entry*1.06,2)
            if abs(stop-exp_stop) > 0.02 or abs(tgt-exp_tgt) > 0.02: bad_stop += 1
        except Exception:
            bad_stop += 1
print('boards:', boards)
print('dates:', dict(sorted(dates.items())))
print('missing kline.day:', miss_day, '| missing kline.min5:', miss_min5, '| missing score:', miss_score)
print('dated 2026-08-21 items:', len(dated_pass))
ok = sum(1 for x in dated_pass if (x.get('score') or 0) >= 57)
print('  dated score>=57:', ok, '| score missing among dated:', sum(1 for x in dated_pass if 'score' not in x))
print('  stop/target math deviations (dated):', bad_stop)

print('=' * 60)
print('VALIDATE fundflow.json')
ff = load('fundflow.json')
print('updatedAt:', ff.get('updatedAt'))
print('indices:', len(ff.get('indices',[])), '->', [(i['name'], i['pct']) for i in ff.get('indices',[])])
print('styleFactors:', len(ff.get('styleFactors',[])))
print('heatSectors:', len(ff.get('heatSectors',[])), '| fundFlow:', len(ff.get('fundFlow',[])))
print('northFlow todayNet:', (ff.get('northFlow') or {}).get('todayNet'))
print('recommendations:', len(ff.get('recommendations',[])))
print('  indices/style non-empty (required):', bool(ff.get('indices')) and bool(ff.get('styleFactors')))

print('=' * 60)
print('VALIDATE briefing_final.json')
bf = load('briefing_final.json')
print('date:', bf.get('date'), '| type:', bf.get('type'), '| warning:', bf.get('warning'))
print('title:', bf.get('title'))
print('md length:', len(bf.get('md','')))
# verify md contains 2026-08-21 section
print('md has 2026-08-21 marker:', '2026-08-21' in bf.get('md',''))

print('=' * 60)
print('DAILY BRIEFING roll-up file check (每日简报.md)')
mb = os.path.join(DIR, '每日简报.md')
if os.path.exists(mb):
    txt = open(mb, 'r', encoding='utf-8').read()
    import re
    secs = re.findall(r'^##\s+(\d{4}-\d{2}-\d{2})', txt, re.M)
    print('sections (latest 5):', secs[-5:])
    print('contains 2026-08-21 section:', '2026-08-21' in secs)
else:
    print('每日简报.md NOT FOUND')
print('=' * 60)
print('VALIDATION COMPLETE')
