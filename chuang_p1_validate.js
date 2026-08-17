'use strict';
// chuang_p1_validate.js — P1 波动率目标叠加层验证（在 P0 修正引擎上）
// 对同一批修正后候选，依次开启波动率叠加层（多种阈值），对比基线（VT off）。
// 不改选股 → 纯 regime 择时贡献。
process.chdir('D:/WorkBuddy');
const { CHUANG_CONFIG } = require('./chuang/config');
const { loadUniverse, loadIndex, loadSwitchIndex } = require('./chuang/data');
const { loadG5, loadFundStore, generateSignals, resetPreStats } = require('./chuang/strategy');
const { applyPortfolio } = require('./chuang/risk');
const { buildVolTarget } = require('./chuang/voltarget');

const config = CHUANG_CONFIG;
config.portfolio.ddPause = 9.9;          // 干净对照：实际关闭回撤暂停（0 会每笔亏损后都暂停，反而过滤更多）
config.portfolio.maxBuyPerDay = 999;     // 抬高每日上限，VT 仅做 regime 减法（n 必 ≤ 基线）
const items = loadUniverse(config.src);
const index = loadIndex(config.indexFile);
const g5 = loadG5(config.fundFile);
const fund = loadFundStore(config.fundFile);
let switchIndex = null;
try { switchIndex = loadSwitchIndex(config.marketSwitch.indexFile, config.marketSwitch); } catch (e) {}
const baseCtx = { items, index, switchIndex, g5, fund, config, sectors: { byCode: {}, bySector: {} } };

const K = +(process.env.BT_K || config.execution.kAtr);
const H = +(process.env.BT_H || config.execution.maxHold);
const cfg = { kAtrDyn: K, maxHoldDyn: H, maxHoldMain: config.main.maxHold, boards: 'chuang_only',
              regime: process.env.BT_R || 'none', from: config.period.from, to: process.env.BT_TO || config.period.to };

function runWithVolTarget(vtCfg) {
  config.volTarget = Object.assign({}, config.volTarget, vtCfg, { enabled: true });
  const built = buildVolTarget(config);
  const ctx = Object.assign({}, baseCtx, { volTargetOK: built.okByDate });
  resetPreStats();
  let cands = [];
  items.forEach(s => { cands = cands.concat(generateSignals(s, cfg, ctx)); });
  const trades = applyPortfolio(cands, config, index).trades;
  return { trades, stats: built.stats, ps: getPreStatsSafe() };
}
function runBaseline() {
  config.volTarget = Object.assign({}, config.volTarget, { enabled: false });
  const ctx = Object.assign({}, baseCtx);
  resetPreStats();
  let cands = [];
  items.forEach(s => { cands = cands.concat(generateSignals(s, cfg, ctx)); });
  const trades = applyPortfolio(cands, config, index).trades;
  return { trades };
}
function getPreStatsSafe() { try { return require('./chuang/strategy').getPreStats(); } catch (e) { return {}; } }

function stat(trades) {
  const n = trades.length; if (!n) return null;
  const pos = trades.filter(t => t.ret > 0), neg = trades.filter(t => t.ret <= 0);
  const sp = pos.reduce((s, t) => s + t.ret, 0), sn = neg.reduce((s, t) => s + Math.abs(t.ret), 0);
  return { n, win: pos.length / n, exp: trades.reduce((s, t) => s + t.ret, 0) / n,
           pf: sn ? sp / sn : null };
}
const p = x => (x * 100).toFixed(2) + '%';
function showRow(label, s, base) {
  if (!s) { console.log(label.padEnd(40) + ': 无样本'); return; }
  const dExp = base ? (s.exp - base.exp) * 100 : 0;
  const dPf = (base && base.pf && s.pf) ? s.pf - base.pf : null;
  console.log(label.padEnd(40) + ': n=' + String(s.n).padStart(4) + '  胜率 ' + p(s.win).padStart(7)
    + '  期望 ' + p(s.exp).padStart(7) + (base ? ' (' + (dExp >= 0 ? '+' : '') + dExp.toFixed(2) + 'pp)' : '').padStart(9)
    + '  PF ' + (s.pf == null ? 'n/a' : s.pf.toFixed(3)).padStart(6)
    + (dPf != null ? ' (' + (dPf >= 0 ? '+' : '') + dPf.toFixed(2) + ')' : '').padStart(8));
}

const base = runBaseline();
const bs = stat(base.trades);
console.log('\n===== P1 波动率目标叠加层（修正引擎, kAtr=' + K + ' h=' + H + ' to=' + cfg.to + '）=====');
console.log('板块等权年化波动样本均值参照见各 VT 配置 stats。');
showRow('基线 VT=off（修正后）', bs, null);
console.log('--- abs 模式（年化波动阈值，>则暂停）---');
for (const v of [0.30, 0.35, 0.40, 0.45, 0.50]) {
  const r = runWithVolTarget({ mode: 'abs', volPause: v });
  const s = stat(r.trades);
  showRow('  abs volPause=' + v, s, bs);
  console.log('       pauseRate=' + r.stats.pauseRate + '  样本波动=' + r.stats.sampleVolAnnualized + '  skipVOLT=' + r.ps.skipVolTarget);
}
console.log('--- z 模式（滚动 z 分数，>则暂停）---');
for (const z of [1.0, 1.5, 2.0]) {
  const r = runWithVolTarget({ mode: 'z', zThresh: z, zLook: 250 });
  const s = stat(r.trades);
  showRow('  z zThresh=' + z, s, bs);
  console.log('       pauseRate=' + r.stats.pauseRate + '  skipVOLT=' + r.ps.skipVolTarget);
}
