import urllib.request, json, zlib, gzip, sys

def get(url, ref=None, gbk=False):
    req = urllib.request.Request(url)
    req.add_header('User-Agent','Mozilla/5.0')
    if ref: req.add_header('Referer', ref)
    raw = urllib.request.urlopen(req, timeout=20).read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    try:
        return raw.decode('utf-8' if not gbk else 'gbk')
    except:
        return raw.decode('utf-8','ignore')

# 1) fqkline mirror
url = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get?param=sh600519,day,2026-08-25,2026-09-10,20,qfq"
try:
    t = get(url, ref="https://gu.qq.com/")
    d = json.loads(t)
    node = d.get('code',0)
    qfq = d.get('data',{}).get('sh600519',{}).get('qfqday') or d.get('data',{}).get('sh600519',{}).get('day')
    print("KLINES last 6 dates:")
    for r in (qfq or [])[-6:]:
        print(r)
    print("total bars returned:", len(qfq) if qfq else 0)
except Exception as e:
    print("KLINE ERR", repr(e)[:200])

# 2) qt snapshot
try:
    q = get("https://qt.gtimg.cn/q=sh600519", gbk=True)
    print("QT raw:", q[:200])
    f = q.split('~')
    print("QT date(f[30]):", f[30], "name(f[1]):", f[1], "price(f[3]):", f[3], "open(f[5]):", f[5], "prevclose(f[4]):", f[4],"high(f[33]):",f[33],"low(f[34]):",f[34],"vol(f[36]):",f[36])
except Exception as e:
    print("QT ERR", repr(e)[:200])
