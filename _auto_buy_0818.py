import json, sys

p = '选股结果/import_final.json'
d = json.load(open(p, encoding='utf-8'))
updated = d.get('updated')
items = d.get('items', [])
print('updated:', updated, '| items:', len(items))

# baselineDate = date part of updated (per spec step 6)
baseline_date = updated[:10]
print('baselineDate:', baseline_date)

# origin (today) - will be passed in
today = sys.argv[1] if len(sys.argv) > 1 else '2026-08-18'
print('date:', today)

# Top3 by win desc
def win_of(it):
    try:
        return float(it.get('win') or 0)
    except Exception:
        return 0.0

ranked = sorted(items, key=win_of, reverse=True)
top3 = ranked[:3]
print('\n=== TOP3 by win ===')
for it in top3:
    code = it['code']; name = it['name']; board = it['board']; win = win_of(it)
    day = it['kline']['day']
    last = day[-1]; prev = day[-2]
    baseline = float(last[2])
    print(f'{code} {name} board={board} win={win} baseline={baseline} lastDate={last[0]}')

    # 5b all-market filter (signal day = last bar)
    close = float(last[2]); openp = float(last[1]); prevClose = float(prev[2]); vol = float(last[5])
    n = len(day)
    if n < 20:
        print('  5b: SKIP (history<20)')
        continue
    ma5 = sum(float(b[2]) for b in day[-5:]) / 5
    ma20 = sum(float(b[2]) for b in day[-20:]) / 20
    ma20_prev = sum(float(b[2]) for b in day[-21:-1]) / 20
    ma20_vol = sum(float(b[5]) for b in day[-20:]) / 20
    trend_ok = (close > ma20) and (ma5 > ma20) and (ma20 > ma20_prev)
    vol_ok = vol >= 1.2 * ma20_vol
    gap = (openp - prevClose) / prevClose
    gap_ok = (-0.04 <= gap <= 0.06)
    passed = trend_ok and vol_ok and gap_ok
    print(f'  5b: close={close} ma5={ma5:.2f} ma20={ma20:.2f} ma20prev={ma20_prev:.2f} ma20vol={ma20_vol:.0f}')
    print(f'      trend_ok={trend_ok} vol_ok={vol_ok}(vol={vol:.0f} need>= {1.2*ma20_vol:.0f}) gap={gap*100:.2f}% gap_ok={gap_ok} => filter_passed={passed}')

# Dump top3 baseline for later decision
out = []
for it in top3:
    day = it['kline']['day']
    last = day[-1]; prev = day[-2]
    close = float(last[2]); openp = float(last[1]); prevClose = float(prev[2]); vol = float(last[5])
    n = len(day)
    ma5 = sum(float(b[2]) for b in day[-5:]) / 5
    ma20 = sum(float(b[2]) for b in day[-20:]) / 20
    ma20_prev = sum(float(b[2]) for b in day[-21:-1]) / 20
    ma20_vol = sum(float(b[5]) for b in day[-20:]) / 20
    gap = (openp - prevClose) / prevClose
    out.append({
        'code': it['code'], 'name': it['name'], 'board': it['board'], 'win': win_of(it),
        'baseline': close, 'prevClose': prevClose, 'vol': vol,
        'ma5': ma5, 'ma20': ma20, 'ma20_prev': ma20_prev, 'ma20_vol': ma20_vol, 'gap': gap,
        'n': n, 'lastDate': last[0]
    })
json.dump({'today': today, 'baseline_date': baseline_date, 'top3': out},
          open('_auto_top3_0818.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('\nwrote _auto_top3_0818.json')
