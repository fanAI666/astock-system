import io, os
auto = r'.workbuddy/automations/automation-1783746752370/memory.md'
note = """
## 2026-08-19 (周三, 09:30 触发 — 交易日, 实际执行 ~14:03)
- 输入: import_final.json（updated=2026-08-18T15:38, 候选池 **147 支**(main82/cyb44/kcb21), 各 800 根日线, 末棒 2026-08-18, baselineDate=2026-08-18）。较 08-18 的 137 支扩容；定稿已刷新（08-18 盘后有跑）。
- Top3 by win: 600000 浦发银行(79.8,main)/002415 海康威视(79.0,main)/002900 哈三联(79.0,main)。基准收盘 8.97/35.18/14.21。
- ⑤ 大盘硬过滤: data_kline(sh000001,day,25) 一次成功, newest-first, 首根=2026-08-19 盘中棒(open3952.12 last3894.01, **今日大跌 −2.41%**)。含今日棒 MA20=3887.36 vs 3894.01 → **+0.17% 多头(极限卡边)**; 仅完成棒(08-18收3990.30) MA20=3886.01 → +2.68% 多头。两口径同向 → 进入个股评估。⚠️ 若今日收盘再跌 ~7 点即翻空, 多头序列(08-06 起)面临中断。
- 开盘价(data_quote 一次成功, time=2026-08-19 真实开盘): 600000 开 9.01(dev +0.45%)/002415 开 34.50(dev −1.93%)/002900 开 14.30(dev +0.63%)。**三只容差全过**(002415 −1.93% 卡边)。
- 5b 全市场过滤(基准日=08-18): 600000 趋势✗(close8.97<MA20 9.229; MA5 9.092<MA20)+量能✗(610627<900304); 002415 趋势✗(35.18<36.492; MA5 35.456<MA20)+量能✗(568941<1346962); 002900 趋势✓缺口✓(−1.41%) 但**量能✗(237585<388880)**。→ 三只 FILTER_PASS=False。
- 判定: **trade=false, 0 笔买入**(三只均 hold, 全部因 5b 过滤未过而非容差)。首次出现"容差全过但过滤全否"的组合。
- ⚠️ 漏单记录: 002900 哈三联 今日 **涨停 15.63(+9.99%, 换手 12.3%)**, 开盘 14.30 在容差内、趋势/缺口均过, 仅量能(基准日 08-18 缩量 23.8万 < 门槛 38.9万)一项否掉 → 错过一个涨停。可作为"量能门槛是否对缩量整理后启动形态过严"的样本, 但单例不足以调参。
- 6.5 双创新信号: `node chuang/index.js signals` exit 0, 窗口内 **60 条 / 新警报 5**(与 08-18 一致, config.src=universe_klines.json)。线上 chuang_signals stats.total=199/newAlerts=5。
- 推送: 固化处置对齐 gh-pages(04abfd8→**7b2e6f8**, Actions 08-18 部署) → sync_pages.js 重建 deploy(12 处路径替换, data 10 文件齐全, gate 注入 OK) → **push 两次均失败**(`Empty reply from server` / `Recv failure: Connection was reset`, git over HTTPS 不通) → 按约束停止重试, 走 **GitHub Contents API 兜底**(`_api_push.py`, 已把 message 日期改 2026-08-19): PUT data/buy_signal.json=9868d07 + data/chuang_signals.json=44b01f1 均 ok。
- 线上复验(等 75s): github.io 与 raw 两路均 date=2026-08-19 / baselineDate=2026-08-18 / trade=false / top3=3(全 hold, open 与本地一致) → **云端已生效**。
- ⚠️ 遗留: 本地 pages 工作仓有未推送提交 a4ac394, 远程经 API 前进 → **历史已分叉**。下次手动 sync_pages.js 前必须 `cd pages && git fetch origin gh-pages && git reset --hard origin/gh-pages`。
- 结论: 08-19 大盘多头但已弱化至 +0.17%(今日盘中 −2.41%), Top3 容差全过、5b 全否 → 不交易；双创 60/5；云端经 API 兜底同步成功。
"""
with io.open(auto,'a',encoding='utf-8') as f: f.write(note)
print('auto memory appended', os.path.getsize(auto))

day = r'.workbuddy/memory/2026-08-19.md'
os.makedirs(os.path.dirname(day), exist_ok=True)
dnote = """
## 买入信号自动化 (automation-1783746752370) — 2026-08-19 执行
- 基准: import_final.json 08-18 定稿(147 支)；Top3 600000/002415/002900(win 79.8/79/79)。
- 大盘: 上证今日盘中 −2.41%(3894.01)，含今日棒 MA20=3887.36 → 仅 +0.17% 多头(卡边)；完成棒口径 +2.68%。多头序列已明显弱化。
- 结果: trade=false，三只容差全过但 5b 过滤全否(2 趋势+量能 / 1 量能)。002900 当日涨停 +9.99% 属漏单，因基准日缩量未过量能门槛。
- 双创信号刷新 60 条/新警报 5。
- 推送: git push 两次失败(git over HTTPS Empty reply / Connection reset) → 用 `_api_push.py` 走 GitHub Contents API 兜底成功；线上双路复验通过。
- 遗留: 本地 pages 工作仓与远程 gh-pages 历史分叉(本地 a4ac394 未推)，下次 sync 前需 reset --hard origin/gh-pages。
"""
mode = 'a' if os.path.exists(day) else 'w'
with io.open(day,mode,encoding='utf-8') as f:
    if mode=='w': f.write('# 2026-08-19 工作日志\n')
    f.write(dnote)
print('daily log written', os.path.getsize(day))
