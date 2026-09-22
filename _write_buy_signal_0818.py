import json

# Load precomputed top3 baseline/filter info
meta = json.load(open('_auto_top3_0818.json', encoding='utf-8'))
top3_meta = {t['code']: t for t in meta['top3']}

# Today's actual open prices (westock data_quote, time=2026-08-18)
opens = {
    '600000': 9.07,    # sh600000
    '002415': 35.00,   # sz002415
    '002900': 14.71,   # sz002900
}

board = 'main'
tol = 0.02  # main ±2%

top3 = []
for code in ['600000', '002415', '002900']:
    m = top3_meta[code]
    name = m['name']  # import_final name already is "浦发银行 600000" format
    baseline = m['baseline']
    openp = opens[code]
    dev = (openp - baseline) / baseline
    # 5a tolerance
    tol_pass = abs(dev) <= tol
    # 5b all-market filter
    close = m['baseline']; ma20 = m['ma20']; ma5 = m['ma5']; ma20prev = m['ma20_prev']
    ma20_vol = m['ma20_vol']; vol = m['vol']; gap = m['gap']
    trend_ok = (close > ma20) and (ma5 > ma20) and (ma20 > ma20prev)
    vol_ok = vol >= 1.2 * ma20_vol
    gap_ok = (-0.04 <= gap <= 0.06)
    filter_pass = trend_ok and vol_ok and gap_ok
    if not tol_pass:
        decision = 'hold'
        reason = f"容差超±2%(开盘偏离{dev*100:+.2f}%>{tol*100:.0f}%)"
    elif not filter_pass:
        fail_parts = []
        if not trend_ok: fail_parts.append(f"趋势(close{baseline:.2f}<MA20{ma20:.2f})")
        if not vol_ok: fail_parts.append(f"量能(vol{vol:.0f}<1.2×MA20量{1.2*ma20_vol:.0f})")
        if not gap_ok: fail_parts.append(f"缺口({gap*100:+.2f}%)")
        decision = 'hold'
        reason = "过滤未过·" + "+".join(fail_parts)
    else:
        decision = 'buy'
        reason = None
    item = {
        'code': code, 'name': name, 'board': board,
        'win': m['win'], 'baseline': round(baseline, 2),
        'open': openp, 'dev': round(dev, 4), 'tol': tol,
        'decision': decision,
    }
    if reason:
        item['reason'] = reason
    top3.append(item)

trade = any(t['decision'] == 'buy' for t in top3)

out = {
    'date': meta['today'],
    'baselineDate': meta['baseline_date'],
    'top3': top3,
    'trade': trade,
}
json.dump(out, open('选股结果/buy_signal.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=2))
print('\nWROTE 选股结果/buy_signal.json | trade =', trade)
