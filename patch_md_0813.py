# -*- coding: utf-8 -*-
"""
patch_md_0812.py — 为 2026-08-12.md 注入动态章节：
  二、大盘实况与资金主线（指数当日/5日/20日 + Step-8 判定 + 资金主线 + 风格）
  六、存量持仓破位警示（收盘已跌破历史签发止损价的老信号）
数据来源：选股结果/fundflow.json + import_final.json（K线末棒） + 腾讯指数K线(urllib)。
必须在 build_briefings.js 之前运行（briefing 读取最终 MD）。
"""
import os, json, urllib.request, datetime, time

BASE = r"D:/WorkBuddy"
RES = os.path.join(BASE, "选股结果")
DATE = "2026-08-13"
MD = os.path.join(RES, DATE + ".md")
FINAL = os.path.join(RES, "import_final.json")
FF = os.path.join(RES, "fundflow.json")
UA = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://gu.qq.com/'}

def get(u, enc='utf-8', timeout=25, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(u, headers=UA)
            return urllib.request.urlopen(req, timeout=timeout).read().decode(enc, 'ignore')
        except Exception as e:
            time.sleep(1.0 * (i + 1))
    return None

def pull_idx(code):
    u = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,2025-01-01,{DATE},400,qfq'
    try:
        j = json.loads(get(u)); node = j['data'].get(code)
        if not node: return None
        kl = node.get('qfqday') or node.get('day') or []
        out = [[str(b[0]), float(b[1]), float(b[2]), float(b[3]), float(b[4]), float(b[5])] for b in kl]
        return out
    except Exception:
        return None

# ---------- 指数趋势 ----------
idx_map = {'sh000001': '上证指数', 'sz399001': '深证成指', 'sz399006': '创业板指'}
idx_rows = []
for code, name in idx_map.items():
    kl = pull_idx(code)
    if not kl or len(kl) < 22:
        idx_rows.append((name, None, None, None)); continue
    closes = [b[2] for b in kl]
    last = closes[-1]
    d5 = (last - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0.0
    d20 = (last - closes[-21]) / closes[-21] * 100 if len(closes) >= 21 else 0.0
    idx_rows.append((name, last, d5, d20))

# ---------- 读 fundflow ----------
ff = json.load(open(FF, encoding='utf-8'))
indices = ff.get('indices', [])
ff_pct = {i['name'].replace('指数', ''): i['pct'] for i in indices}
down2 = any(i['pct'] <= -2 for i in indices)
step8 = '⚠️ **触发收缩/暂停新增**：上证/深证/创业板任一跌超2%，建议收缩或暂停新开仓。' if down2 else \
        '未触发收缩/暂停（三指均未见跌超2%）。'
fund_thread = ff.get('fundThread', '')
pos = sorted([s for s in ff.get('heatSectors', []) if s['pct'] > 0], key=lambda x: -x['pct'])
top_net = sorted(ff.get('fundFlow', []), key=lambda x: -x['net'])[:3]
styles = ff.get('styleFactors', [])

# ---------- 存量破位 ----------
blob = json.load(open(FINAL, encoding='utf-8'))
items = blob['items'] if isinstance(blob, dict) else blob
breaks = []
for it in items:
    kl = it.get('kline', {}).get('day')
    sp = it.get('stopPrice')
    if not kl or not sp: continue
    close = kl[-1][2]
    if close < sp:
        pct_below = (close - sp) / sp * 100
        breaks.append((it.get('name', ''), str(it.get('code', '')), round(close, 2), round(sp, 2), round(pct_below, 2), it.get('date', '')))
breaks.sort(key=lambda x: x[4])
total_break = len(breaks)

# ---------- 组装 大盘实况章节 ----------
L = []
L.append('## 二、大盘实况与资金主线')
L.append('')
L.append(f'- **Step-8 判定**：{step8}')
L.append('')
L.append('| 指数 | 收盘 | 当日% | 5日% | 20日% |')
L.append('| --- | --- | --- | --- | --- |')
for name, last, d5, d20 in idx_rows:
    if last is None:
        L.append(f'| {name} | - | - | - | - |')
    else:
        L.append(f'| {name} | {last:.2f} | {ff_pct.get(name.replace("指数",""), 0):+.2f}% | {d5:+.2f}% | {d20:+.2f}% |')
L.append('')
L.append(f'- **资金主线**：{fund_thread}')
if top_net:
    L.append('- **主力净流入居前**：' + '、'.join([f'{t["sector"]}(+{t["net"]}亿)' for t in top_net]) + '。')
if styles:
    L.append('- **风格因子**：' + '、'.join([f'{s["name"]}({"强" if s["up"] else "弱"})' for s in styles]) + '。')
L.append('')
market_section = '\n'.join(L)

# ---------- 组装 存量破位章节 ----------
B = []
B.append('## 六、存量持仓破位警示')
B.append('')
if total_break == 0:
    B.append('- 截至今日收盘，无存量信号跌破历史签发止损价。')
else:
    B.append(f'- 共 **{total_break}** 只存量信号收盘价已跌破其签发止损价，建议按纪律处理（减仓/止损）：')
    B.append('')
    B.append('| 名称/代码 | 收盘 | 止损价 | 低于止损 | 签发日 |')
    B.append('| --- | --- | --- | --- | --- |')
    for name, code, close, sp, pb, d in breaks[:22]:
        B.append(f'| {name} {code} | {close} | {sp} | {pb:.2f}% | {d} |')
    if total_break > 22:
        B.append(f'| … | | | | 其余 {total_break-22} 只略 |')
B.append('')
break_section = '\n'.join(B)

# ---------- 注入 MD ----------
md = open(MD, encoding='utf-8').read()
md = md.replace('## 二、前3名简评', market_section + '\n## 三、前3名简评')
md = md.replace('## 三、落选/排除（score<57 或涨停追高）', '## 四、落选/排除（score<57 或涨停追高）')
# 在「## 四、风险提示」前插入破位章节，并将其改为 五
md = md.replace('## 四、风险提示', break_section + '## 五、风险提示')
open(MD, 'w', encoding='utf-8').write(md)
print(f'MD 补丁完成：大盘实况+资金主线已注入；存量破位 {total_break} 只（展示 {min(total_break,22)}）。')
print('Step-8:', '触发' if down2 else '未触发')
print('idx 5日/20日:', [(n, (round(d5,2) if d5 is not None else None), (round(d20,2) if d20 is not None else None)) for n,_,d5,d20 in idx_rows])
