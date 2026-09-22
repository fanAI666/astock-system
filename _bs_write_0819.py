import json, io
top3raw=json.load(io.open('_bs_top3_0819.json',encoding='utf-8'))
opens={'600000':9.01,'002415':34.50,'002900':14.30}
out=[]
for r in top3raw:
    c=r['code']; base=r['baseline']; tol=r['tol']
    op=opens.get(c)
    item={'code':c,'name':r['name'],'board':r['board'],'win':r['win'],
          'baseline':round(base,4),'open':op,'tol':tol}
    if op is None:
        item['dev']=None; item['decision']='hold'; item['reason']='未取到开盘价'
    else:
        dev=(op-base)/base
        item['dev']=round(dev,4)
        if abs(dev)>tol:
            item['decision']='hold'; item['reason']='开盘偏离 %+.2f%% 超容差 ±%.0f%%'%(dev*100,tol*100)
        elif not r['pass']:
            ng=[]
            if not r['trendOK']: ng.append('趋势')
            if not r['volOK']: ng.append('量能')
            if not r['gapOK']: ng.append('缺口')
            item['decision']='hold'; item['reason']='过滤未过·'+'+'.join(ng)
        else:
            item['decision']='buy'
    out.append(item)
sig={'date':'2026-08-19','baselineDate':'2026-08-18','top3':out,
     'trade': any(x['decision']=='buy' for x in out)}
json.dump(sig,io.open('选股结果/buy_signal.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print(json.dumps(sig,ensure_ascii=False,indent=1))
