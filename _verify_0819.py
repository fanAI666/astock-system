import urllib.request, json
for url in ['https://fanai666.github.io/astock-system/data/buy_signal.json',
            'https://raw.githubusercontent.com/fanAI666/astock-system/gh-pages/data/buy_signal.json']:
    try:
        r=urllib.request.urlopen(url,timeout=40)
        d=json.loads(r.read().decode('utf-8'))
        print('[OK]',url.split('/')[2])
        print('   date=',d.get('date'),'baselineDate=',d.get('baselineDate'),'trade=',d.get('trade'),'top3=',len(d.get('top3',[])))
        for t in d.get('top3',[]):
            print('    ',t['code'],t['name'],'open=',t.get('open'),'dev=',t.get('dev'),'->',t.get('decision'),t.get('reason',''))
    except Exception as e:
        print('[FAIL]',url.split('/')[2],e)
try:
    r=urllib.request.urlopen('https://fanai666.github.io/astock-system/data/chuang_signals.json',timeout=40)
    d=json.loads(r.read().decode('utf-8'))
    st=d.get('stats',{})
    print('[chuang online] stats=',{k:st.get(k) for k in ('total','newAlerts','window') if k in st} or st)
except Exception as e:
    print('[chuang online FAIL]',e)
