import urllib.request, json, re
def get(u, enc='utf-8', timeout=20):
    req=urllib.request.Request(u, headers={'User-Agent':'Mozilla/5.0','Referer':'https://gu.qq.com/'})
    return urllib.request.urlopen(req, timeout=timeout).read().decode(enc,'ignore')
u='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,2023-01-01,2026-07-31,800,qfq'
try:
    j=json.loads(get(u))
    node=j['data']['sh600519']
    kl = node.get('qfqday') or node.get('day') or []
    print('KL bars:', len(kl))
    print('last 3 kline:', kl[-3:])
    print('first:', kl[0])
except Exception as e:
    print('KL ERR', e)
try:
    t=get('https://qt.gtimg.cn/q=sh600519', enc='gbk')
    m=re.search(r'"([^"]+)"', t)
    p=m.group(1).split('~')
    for i,k in [(1,'name'),(3,'price'),(4,'prev'),(5,'open'),(6,'vol_hand'),(15,'high'),(16,'low')]:
        print(k,'=',p[i])
except Exception as e:
    print('QT ERR', e)
