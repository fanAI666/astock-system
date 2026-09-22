# -*- coding: utf-8 -*-
"""由 build_0818.py / patch_md_0814.py 派生 08-19 版本（仅改 DATE + NEW_SCREEN，patch 增末棒校验）"""
import re, io

# ---------- build_0819.py ----------
src = open('build_0818.py', encoding='utf-8').read()
src = src.replace('2026-08-18', '2026-08-19')
src = src.replace('import_final.json(137)', 'import_final.json(147)')

NEW = '''NEW_SCREEN={
 # 08-19 主力净流入 >=1.5亿（剔除涨停/追高 ChangePCT>9.5 与次新 N宇树-W 688836）
 '002202':'金风科技','301232':'飞沃科技','600219':'南山铝业','601609':'金田股份','601288':'农业银行',
 '600547':'山东黄金','000703':'恒逸石化','601857':'中国石油','688037':'芯源微','601872':'招商轮船',
 '600460':'士兰微','601318':'中国平安','600026':'中远海能','600367':'红星发展','300373':'扬杰科技',
 '600028':'中国石化','688036':'传音控股','600988':'赤峰黄金',
 # 08-19 高股息 >=4%（防御向补充；已在池者由脚本去重）
 '002763':'汇洁股份','603165':'荣晟环保','600329':'达仁堂','603508':'思维列控','603569':'长久物流',
 '603167':'渤海轮渡','300406':'九强生物','002004':'华邦健康','300533':'冰川网络','002572':'索菲亚',
 '000913':'钱江摩托','000915':'华特达因','603551':'奥普科技','600983':'惠而浦','600866':'星湖科技',
 '601216':'君正集团','300994':'久祺股份','600066':'宇通客车','300770':'新媒股份','601717':'中创智领',
 '688399':'硕世生物','600861':'北京人力','002616':'长青集团','301207':'华兰疫苗','600153':'建发股份',
 '002612':'朗姿股份','002271':'东方雨虹','002007':'华兰生物','603833':'欧派家居'}'''

m = re.search(r"NEW_SCREEN=\{.*?'002271':'东方雨虹'\}", src, re.S)
assert m, 'NEW_SCREEN 块未匹配'
src = src[:m.start()] + NEW + src[m.end():]
open('build_0819.py', 'w', encoding='utf-8').write(src)
print('build_0819.py 写入 OK, len=', len(src))

# ---------- patch_md_0819.py ----------
p = open('patch_md_0814.py', encoding='utf-8').read()
p = p.replace('DATE = "2026-08-14"', 'DATE = "2026-08-19"')

# 增末棒日期校验：web.ifzq 端点滞后1日时，用 fundflow.indices 当日收盘补末棒
old_loop = """idx_map = {'sh000001': '上证指数', 'sz399001': '深证成指', 'sz399006': '创业板指'}
idx_rows = []
for code, name in idx_map.items():
    kl = pull_idx(code)
    if not kl or len(kl) < 22:
        idx_rows.append((name, None, None, None)); continue
    closes = [b[2] for b in kl]"""
new_loop = """idx_map = {'sh000001': '上证指数', 'sz399001': '深证成指', 'sz399006': '创业板指'}
# 预读 fundflow 当日指数收盘（腾讯实时源，用于端点滞后1日时补末棒）
try:
    _ff0 = json.load(open(FF, encoding='utf-8'))
    _today_close = {i['name'].replace('指数', ''): i.get('price') for i in _ff0.get('indices', [])}
except Exception:
    _today_close = {}
idx_rows = []
for code, name in idx_map.items():
    kl = pull_idx(code)
    if not kl or len(kl) < 22:
        idx_rows.append((name, None, None, None)); continue
    # 末棒日期校验：滞后则补当日收盘棒，保证 5日/20日 口径含当日
    tc = _today_close.get(name.replace('指数', ''))
    if kl[-1][0] != DATE and tc:
        kl.append([DATE, tc, float(tc), float(tc), float(tc), 0.0])
        print(f'[idx] {name} 端点末棒={kl[-2][0]} 滞后 -> 已补 {DATE} 收盘 {tc}')
    closes = [b[2] for b in kl]"""
assert old_loop in p, 'patch 指数循环未匹配'
p = p.replace(old_loop, new_loop)
open('patch_md_0819.py', 'w', encoding='utf-8').write(p)
print('patch_md_0819.py 写入 OK, len=', len(p))
