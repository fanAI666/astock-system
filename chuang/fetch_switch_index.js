'use strict';
// chuang/fetch_switch_index.js — 抓取并缓存「大盘开关」所需指数日K
// 圆桌结论（信号派首席 DRFR / 短线冲浪手 大盘环境开关）：
//   开门 = 创业板指 RS(5日) > 0 且 站上自身20日线 且 量 > 前20日均
//   停火 = RS<0 连5日 或 创业板指20日跌幅 < −10%
// 缓存到 switch_index.json（{ cyb:[...], hs300:[...] }，bars=[date,o,c,h,l,v]），
// 之后 loadSwitchIndex 直接读本地，回测离线可复现。
const fs = require('fs');
const { fetchKlineTencent } = require('./data');
const { Logger } = require('./logger');

const OUT = process.env.SW_OUT || 'D:/WorkBuddy/选股结果/switch_index.json';
// 🔴 区间可配：默认保持旧值以复现历史结果；要放开长历史回测需显式
//    SW_BEG=2022-01-01 SW_END=<今天> 重生成 —— 开关指数的覆盖范围就是回测区间的硬上限，
//    写死 20230828 会让 2022 起的长历史宇宙白白用不上（2026-09-22 实测确认）。
const BEG = process.env.SW_BEG || '2023-08-28';
const END = process.env.SW_END || '2026-06-30';

(async () => {
  // 注意：指数代码需带市场前缀直接传入（fetchKlineTencent 的前缀规则按股票 6xxxx=sz 判定，
  // 沪深300 代码 000300 虽在上交所但前缀为 0，会被误判为 sz，故这里直接给 tc）。
  Logger.info('SW', `拉取创业板指 sz399006 与 沪深300 sh000300 日K（${BEG} ~ ${END}）…`);
  const cyb = await fetchKlineTencent('sz399006', BEG, END);
  const hs = await fetchKlineTencent('sh000300', BEG, END);
  if (!cyb || !hs) { Logger.error('SW', '指数抓取失败（网络/反爬），请重试'); process.exit(1); }
  if (cyb.length < 60 || hs.length < 60) { Logger.error('SW', `数据过短 cyb=${cyb.length} hs=${hs.length}`); process.exit(1); }
  fs.writeFileSync(OUT, JSON.stringify({
    updated: new Date().toISOString().slice(0, 10),
    period: [BEG.replace(/-/g, ''), END.replace(/-/g, '')],
    cyb, hs300: hs,
  }, null, 2), 'utf8');
  Logger.info('SW', `创业板指 ${cyb.length} 根 / 沪深300 ${hs.length} 根 → ${OUT}`);
})();
