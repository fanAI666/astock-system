import json, io
# ---- index MA20 two calibers ----
idx = [3894.01,3990.30,3982.65,3927.18,3926.96,3946.68,3934.09,3966.59,3940.04,3900.35,
       3878.43,3822.28,3809.66,3832.26,3804.69,3828.47,3813.31,3858.25,3814.20,3876.78,3867.03]
inc = idx[0:20]; exc = idx[1:21]
ma_inc = sum(inc)/20; ma_exc = sum(exc)/20
print('[INDEX] 含今日盘中棒: last=%.2f MA20=%.2f dev=%+.2f%% -> %s' % (idx[0], ma_inc, (idx[0]/ma_inc-1)*100, '多头' if idx[0]>ma_inc else '空头'))
print('[INDEX] 仅完成棒(08-18): last=%.2f MA20=%.2f dev=%+.2f%% -> %s' % (idx[1], ma_exc, (idx[1]/ma_exc-1)*100, '多头' if idx[1]>ma_exc else '空头'))

# ---- Top3 5b filter ----
d=json.load(io.open('选股结果/import_final.json',encoding='utf-8'))
items=d['items']
top=sorted(items,key=lambda x: float(x.get('win') or 0),reverse=True)[:3]
out=[]
for it in top:
    k=it['kline']['day']
    code=it['code']; name=it['name']; board=it['board']; win=float(it['win'])
    last=k[-1]; prev=k[-2]
    close=float(last[2]); op=float(last[1]); prevClose=float(prev[2]); vol=float(last[5])
    tol = 0.02 if board=='main' else 0.03
    res={'code':code,'name':name,'board':board,'win':win,'baseline':close,'tol':tol,'sigDate':last[0]}
    if len(k)<20:
        res.update({'trendOK':False,'volOK':False,'gapOK':False,'pass':False,'why':'历史根数不足20'})
    else:
        closes=[float(x[2]) for x in k]
        vols=[float(x[5]) for x in k]
        ma5=sum(closes[-5:])/5
        ma20=sum(closes[-20:])/20
        ma20p=sum(closes[-21:-1])/20
        ma20v=sum(vols[-20:])/20
        trendOK = (close>ma20) and (ma5>ma20) and (ma20>ma20p)
        volOK = vol >= 1.2*ma20v
        gap = (op-prevClose)/prevClose
        gapOK = (gap>=-0.04) and (gap<=0.06)
        res.update({'ma5':round(ma5,4),'ma20':round(ma20,4),'ma20p':round(ma20p,4),'ma20v':round(ma20v,1),
                    'vol':vol,'need':round(1.2*ma20v,1),'gap':round(gap,4),
                    'trendOK':trendOK,'volOK':volOK,'gapOK':gapOK,'pass':bool(trendOK and volOK and gapOK)})
    out.append(res)
    print('---',code,name,board,'win=',win,'sigDate=',last[0])
    print('   baseline(close)=%.2f  tol=%.0f%%' % (close, tol*100))
    if 'ma20' in res:
        print('   趋势: close %.3f vs MA20 %.3f (%s) | MA5 %.3f vs MA20 %.3f (%s) | MA20 %.3f vs MA20前 %.3f (%s) => %s'
              % (close,res['ma20'],'OK' if close>res['ma20'] else 'NG',res['ma5'],res['ma20'],'OK' if res['ma5']>res['ma20'] else 'NG',
                 res['ma20'],res['ma20p'],'OK' if res['ma20']>res['ma20p'] else 'NG', res['trendOK']))
        print('   量能: vol %.0f vs 1.2*MA20量 %.0f => %s' % (vol,res['need'],res['volOK']))
        print('   缺口: %+.2f%% (需 -4%%~+6%%) => %s' % (res['gap']*100,res['gapOK']))
    print('   FILTER_PASS =',res['pass'])
json.dump(out,io.open('_bs_top3_0819.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('saved _bs_top3_0819.json')
