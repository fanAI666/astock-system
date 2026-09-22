# -*- coding: utf-8 -*-
"""探测腾讯公开端点可用性 + 上证指数日K末根日期 (2026-09-03)"""
import urllib.request, json, time

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

def get(url, enc='utf-8', timeout=15, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': UA, 'Referer': 'https://gu.qq.com/'})
            return urllib.request.urlopen(req, timeout=timeout).read().decode(enc, 'ignore')
        except Exception as e:
            last = e; time.sleep(0.8 * (i + 1))
    raise last

# 1) qt 实时快照
try:
    raw = get('https://qt.gtimg.cn/q=sh000001,sz399001,sz399006', enc='gbk')
    for line in raw.split(';'):
        line = line.strip()
        if not line.startswith('v_'): continue
        f = line[line.index('"') + 1:line.rindex('"')].split('~')
        print('QT', f[2], f[1], 'cur=', f[3], 'prevClose=', f[4], 'open=', f[5], 'time=', f[30])
except Exception as e:
    print('QT FAIL', repr(e))

# 2) fqkline 上证日K
for host in ['https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',
             'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get']:
    try:
        u = host + '?param=sh000001,day,2026-06-01,2026-09-03,80,qfq'
        d = json.loads(get(u))
        node = d['data']['sh000001']
        k = node.get('qfqday') or node.get('day')
        print('KLINE OK', host.split('/')[2], 'bars=', len(k), 'last3=', [r[:3] for r in k[-3:]])
        break
    except Exception as e:
        print('KLINE FAIL', host.split('/')[2], repr(e))
