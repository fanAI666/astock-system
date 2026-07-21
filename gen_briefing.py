# -*- coding: utf-8 -*-
# 手动补救：基于 import_final.json 最新 24 只数据生成标准盘后简报 md
# （build_briefings.js 只取"纯日期"文件名的最新 md；此前最新的有效简报停在 7-16，
#  7-21 只有 phase0b 技术报告文件、不匹配正则，故简报陈旧。本脚本生成 2026-07-21.md 修复。）
import json, datetime

BASE = 'D:/WorkBuddy/选股结果'

def load(p):
    with open(f'{BASE}/{p}', encoding='utf-8') as f:
        return json.load(f)

d = load('import_final.json')
items = d['items']
idx = load('index_sh.json')
bars = idx['bars']
last, prev = bars[-1], bars[-2]
raw_date = last[0]                       # 形如 20260721（tdx 格式，无连字符）
data_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"  # 转 2026-07-21 以匹配 build_briefings 正则
sh_pct = (float(last[2]) - float(prev[2])) / float(prev[2]) * 100

def hard_reject(it):
    r = []
    if it.get('ma60') == 'down':
        r.append('MA60_DOWN')
    if (it.get('rsi') or 0) > 72:
        r.append('RSI_OVERBOUGHT')
    return r

def reason(it):
    m = {'up': '↑', 'down': '↓', 'flat': '→'}
    s = {'breakout': '突破', 'pullback': '回踩支撑', 'none': '无', '': '无'}
    v = {'high': '放量', 'normal': '平量', 'low': '缩量', '': '平量'}
    sec = {'strong': '强', 'mid': '中', 'weak': '弱', '': '中'}
    return (f"MA20{m.get(it.get('ma20'),'?')}·MA60{m.get(it.get('ma60'),'?')}·"
            f"{s.get(it.get('struct'), it.get('struct'))}·{v.get(it.get('vol'),'?')}·"
            f"板块{sec.get(it.get('sector'),'?')}·RSI{it.get('rsi')}·ATR{it.get('atr')}%")

rows = []
for it in items:
    name = it.get('name', '')
    code = it.get('code', '')
    board = it.get('board', '')
    score = it.get('score', 0)
    win = it.get('win', 0)
    rej = hard_reject(it)
    if rej:
        fs, fw, passed = 0, None, False
    else:
        fs, fw, passed = score, win, score >= 70
    rows.append({'name': name, 'code': code, 'board': board, 'score': fs, 'win': fw,
                 'ma20': it.get('ma20'), 'priceMa': it.get('priceMa'), 'ma60': it.get('ma60'),
                 'rsi': it.get('rsi'), 'atr': it.get('atr'), 'struct': it.get('struct'),
                 'vol': it.get('vol'), 'sector': it.get('sector'), 'reject': rej, 'passed': passed,
                 'reason': reason(it)})

def sortkey(r):
    if r['reject']:
        return (2, -r['score'])
    if r['passed']:
        return (0, -(r['win'] or 0))
    return (1, -r['score'])
rows.sort(key=sortkey)

passed_rows = [r for r in rows if r['passed']]

sh_pct_s = f'{sh_pct:+.2f}%'
if sh_pct <= -2:
    step8 = (f'⚠️ **Step-8 警示**：上证指数单日跌幅 >2%（{sh_pct_s}），属系统性回调环境。'
             f'建议**收缩或暂停新增开仓**，严格按 3:1 止损纪律执行。')
else:
    step8 = (f'✅ 大盘环境平稳（上证 {sh_pct_s}），无系统性回调警示，可按纪律正常选股。')

L = []
L.append(f'# 盘后定稿 · A股稳健选股策略（{data_date}）')
L.append('')
L.append(f'> 数据时间戳：{data_date} 15:30 收盘（通达信 HQDate={data_date.replace("-","")}）。所有胜率均为技术估计，非投资建议；仅选股并警示，不下单/交易。')
L.append('')
L.append('## 一、大盘环境（Step-8 风控）')
L.append('')
L.append('| 指数 | 代码 | 涨跌幅 |')
L.append('|------|------|--------|')
L.append(f'| 上证指数 | 000001 | {sh_pct_s} |')
L.append('')
L.append(step8)
L.append('')
L.append('## 二、达标清单（总分≥57 → 胜率≥70%，按胜率降序）')
L.append('')
L.append('| 排名 | 名称/代码 | 板块 | 综合分 | 胜率估计 | 止损价 | 目标价 | 一句话理由 |')
L.append('|------|-----------|------|--------|----------|--------|--------|------------|')
for i, r in enumerate(passed_rows, 1):
    L.append(f"| {i} | {r['name']} | {r['board']} | {r['score']} | {r['win']}% | "
             f"{r.get('stopPrice','')} | {r.get('targetPrice','')} | {r['reason']} |")
L.append('')
L.append('## 三、盘中简报')
L.append('')
L.append(f"- **达标数**：{len(passed_rows)} 只（候选池 {len(items)} 只，阈值 总分≥57）")
if passed_rows:
    top3 = '、'.join(f"{r['name'].split()[0]}({r['win']}%)" for r in passed_rows[:3])
    L.append(f"- **前 3**：{top3}")
L.append('- **风险提示**：')
L.append('  1. ATR% 偏高者固定比例止损易被扫损，建议按 ATR 动态止损或减仓。')
overbought = [r['name'].split()[0] for r in rows if 'RSI_OVERBOUGHT' in r['reject']]
if overbought:
    L.append(f"  2. RSI 超买（>72）：{('、'.join(overbought))}，追高风险大，宜等回踩 MA20 买点。")
ma60down = [r['name'].split()[0] for r in rows if 'MA60_DOWN' in r['reject']]
if ma60down:
    L.append(f"  3. MA60 向下（中长期趋势弱）被硬拒 {len(ma60down)} 只：{('、'.join(ma60down[:8]))}{' 等' if len(ma60down) > 8 else ''}。")
L.append('  4. 本周交易笔数请自行在「风控看板」核对是否超 5 笔。')
L.append('  5. 所有标的均为技术面筛选，板块强度多数偏弱，属题材轮动博弈，非长线价值仓。')
L.append('')
L.append('## 四、完整评分明细')
L.append('')
L.append('| 名称/代码 | 板块 | ma20 | 价/MA20 | ma60 | RSI | ATR% | 结构 | 量能 | 板块 | 综合分 | 胜率 |')
L.append('|-----------|------|------|---------|------|-----|------|------|------|------|--------|------|')
for r in rows:
    if r['reject']:
        win_s = '—'
        score_s = f"0 (⛔{'/'.join(r['reject'])})"
    else:
        win_s = f"{r['win']}% {'✅达标' if r['passed'] else ''}"
        score_s = str(r['score'])
    L.append(f"| {r['name']} | {r['board']} | {r['ma20']} | {r['priceMa']} | {r['ma60']} | "
             f"{r['rsi']} | {r['atr']} | {r['struct']} | {r['vol']} | {r['sector']} | {score_s} | {win_s} |")
L.append('')
L.append('---')
L.append('')
L.append(f"_生成时间：{datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}+08:00_  |  "
         f"引擎：6 维加权（趋势25/结构20/量能15/板块15/RSI15/止损适配10），胜率=min(88, 50+总分×0.35)。")

md = '\n'.join(L)
with open(f'{BASE}/{data_date}.md', 'w', encoding='utf-8') as f:
    f.write(md)
print(f'written {BASE}/{data_date}.md | passed={len(passed_rows)} | total={len(items)} | 上证{sh_pct_s}')
