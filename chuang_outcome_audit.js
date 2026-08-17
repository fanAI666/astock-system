'use strict';
// chuang_outcome_audit.js — 出场标签口径审计（只读诊断，不写任何生产文件）
//
// 起因：双创回测长期报「胜率 2.6% / PF 0.29 / 期望 -1.37%」，与常识严重背离。
// 怀疑点（strategy.js line 284-295）：
//   ① E3 跟踪止损 curSL = max(sl, high*(1-trailPct))，从持仓第1天起生效、无盈利触发门槛；
//   ② 触及 curSL 一律 outcome='loss'，不判断 exitPrice 与 entry 的大小关系
//      → 出场价高于成本的跟踪止盈单被记成「亏损」。
// 本脚本重算真实口径：真实胜率 = ret>0 占比；真实期望 = mean(ret)；真实 PF = Σ正ret / Σ|负ret|
// 并给出出场原因分布（sl_initial / trail / tp / time）。

const path = require('path');
process.chdir('D:/WorkBuddy');
const { CHUANG_CONFIG, buildGrid } = require('./chuang/config');
const { loadUniverse, loadIndex, loadSwitchIndex } = require('./chuang/data');
const { loadG5, loadFundStore, generateSignals, resetPreStats, getPreStats } = require('./chuang/strategy');
const { applyPortfolio } = require('./chuang/risk');

const config = CHUANG_CONFIG;
const items = loadUniverse(config.src);
const index = loadIndex(config.indexFile);
const g5 = loadG5(config.fundFile);
const fund = loadFundStore(config.fundFile);
let switchIndex = null;
try { switchIndex = loadSwitchIndex(config.marketSwitch.indexFile, config.marketSwitch); } catch (e) {}
const ctx = { items, index, switchIndex, g5, fund, config, sectors: { byCode: {}, bySector: {} } };

if (config.factors && config.factors.enabled) {
  const { buildFactorPass } = require('./chuang/factors');
  const built = buildFactorPass(config);
  ctx.factorPass = built.passByDate;
  console.log('因子层已构建:', JSON.stringify(built.stats));
}

const cfg = {
  kAtrDyn: +(process.env.BT_K || 2.5), maxHoldDyn: +(process.env.BT_H || 8),
  maxHoldMain: config.main.maxHold, boards: 'chuang_only', regime: process.env.BT_R || 'none',
  from: config.period.from, to: process.env.BT_TO || config.period.to,
};

resetPreStats();
let cands = [];
items.forEach(s => { cands = cands.concat(generateSignals(s, cfg, ctx)); });
const port = applyPortfolio(cands, config, index);
const trades = port.trades;

// ---- 官方口径（backtest.js summarize）----
const wL = trades.filter(t => t.outcome === 'win'), lL = trades.filter(t => t.outcome === 'loss');
const offWin = trades.length ? wL.length / trades.length : 0;
const offAvgWin = wL.length ? wL.reduce((s, t) => s + t.ret, 0) / wL.length : 0;
const offAvgLoss = lL.length ? lL.reduce((s, t) => s + Math.abs(t.ret), 0) / lL.length : 0;
const offExp = offWin * offAvgWin - (1 - offWin) * offAvgLoss;
const offPf = lL.reduce((s, t) => s + Math.abs(t.ret), 0) ? wL.reduce((s, t) => s + t.ret, 0) / lL.reduce((s, t) => s + Math.abs(t.ret), 0) : null;

// ---- 真实口径（按 ret 符号）----
const pos = trades.filter(t => t.ret > 0), neg = trades.filter(t => t.ret <= 0);
const trueWin = trades.length ? pos.length / trades.length : 0;
const trueExp = trades.length ? trades.reduce((s, t) => s + t.ret, 0) / trades.length : 0;
const sumP = pos.reduce((s, t) => s + t.ret, 0), sumN = neg.reduce((s, t) => s + Math.abs(t.ret), 0);
const truePf = sumN ? sumP / sumN : null;
const trueAvgWin = pos.length ? sumP / pos.length : 0, trueAvgLoss = neg.length ? sumN / neg.length : 0;

// ---- 错标样本：outcome=loss 但 ret>0 ----
const misLabel = trades.filter(t => t.outcome === 'loss' && t.ret > 0);
const misLabel2 = trades.filter(t => t.outcome === 'win' && t.ret <= 0);

const pct = (x) => (x * 100).toFixed(2) + '%';
console.log('\n===== 出场标签口径审计 (n=' + trades.length + ', kAtr=' + cfg.kAtrDyn + ' h=' + cfg.maxHoldDyn + ' to=' + cfg.to + ') =====');
console.log('官方口径(summarize)  : 胜率 ' + pct(offWin) + '  期望 ' + pct(offExp) + '  PF ' + (offPf == null ? 'n/a' : offPf.toFixed(3))
  + '  avgWin ' + pct(offAvgWin) + '  avgLoss ' + pct(offAvgLoss));
console.log('真实口径(ret符号)    : 胜率 ' + pct(trueWin) + '  期望 ' + pct(trueExp) + '  PF ' + (truePf == null ? 'n/a' : truePf.toFixed(3))
  + '  avgWin ' + pct(trueAvgWin) + '  avgLoss ' + pct(trueAvgLoss));
console.log('错标 outcome=loss 但 ret>0 : ' + misLabel.length + ' 笔 (' + pct(trades.length ? misLabel.length / trades.length : 0)
  + ')  这些笔平均收益 ' + pct(misLabel.length ? misLabel.reduce((s, t) => s + t.ret, 0) / misLabel.length : 0));
console.log('错标 outcome=win  但 ret<=0: ' + misLabel2.length + ' 笔');

// ---- 出场价 vs 关键价位，反推出场原因 ----
let cSl = 0, cTp = 0, cTrail = 0, cTime = 0;
trades.forEach(t => {
  const nearTp = Math.abs(t.exit - t.tp) / t.entry < 1e-6;
  const nearSl = Math.abs(t.exit - t.sl) / t.entry < 1e-6;
  if (nearTp) cTp++;
  else if (nearSl) cSl++;
  else if (t.outcome === 'loss' || t.outcome === 'win') {
    // 触及 curSL 出场（跟踪止损抬升后的价位）vs 到期收盘
    if (t.holdDays >= cfg.maxHoldDyn) cTime++; else cTrail++;
  }
});
console.log('出场原因分布: 初始止损 ' + cSl + ' | 止盈TP ' + cTp + ' | 跟踪止损(含抬升) ' + cTrail + ' | 到期收盘 ' + cTime);

// ---- 收益分布 ----
const buckets = [[-1, -0.10], [-0.10, -0.05], [-0.05, -0.02], [-0.02, 0], [0, 0.02], [0.02, 0.05], [0.05, 0.10], [0.10, 99]];
console.log('收益分档:');
buckets.forEach(([a, b]) => {
  const n = trades.filter(t => t.ret > a && t.ret <= b).length;
  console.log('  (' + (a * 100).toFixed(0) + '%, ' + (b * 100).toFixed(0) + '%] : ' + n + '  ' + pct(trades.length ? n / trades.length : 0));
});
const ps = getPreStats();
console.log('preStats: 候选=' + ps.total + ' 通过预过滤=' + ps.pass + ' FACTOR剔除=' + ps.skipFactor);
