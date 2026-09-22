import json, io
p='选股结果/import_final.json'
d=json.load(io.open(p,encoding='utf-8'))
keys=[k for k in d.keys() if k!='items']
print('TOPKEYS:',keys)
for k in keys:
    v=d[k]
    if isinstance(v,(str,int,float)): print('  ',k,'=',v)
items=d.get('items',[])
print('ITEMS:',len(items))
from collections import Counter
print('BOARDS:',Counter([i.get('board') for i in items]))
# bars
b0=items[0]
print('SAMPLE keys:',list(b0.keys()))
kl=(b0.get('kline') or {}).get('day') or []
print('bars len sample:',len(kl),'last:',kl[-1] if kl else None)
top=sorted(items,key=lambda x: float(x.get('win') or 0),reverse=True)[:6]
print('--- TOP6 by win ---')
for i in top:
    k=(i.get('kline') or {}).get('day') or []
    print(i.get('code'), i.get('name'), i.get('board'), 'win=',i.get('win'), 'bars=',len(k), 'lastbar=',k[-1] if k else None)
