'use strict';
// chuang_e3trig.js — P0 补充：E3 跟踪止损盈利触发门槛敏感度（修正引擎）
// 扫描 E3_trailTrigger ∈ {0,0.02,0.03,0.05}，价格先越过 entry*(1+trig) 才开始跟踪。
// 0 = 即日跟踪（复现审计 B 档）；>0 = 让盈利单多奔跑。
process.chdir('D:/WorkBuddy');
const { CHUANG_CONFIG } = require('./chuang/config');
const { loadUniverse, loadIndex, loadSwitchIndex } = require('./chuang/data');
const { loadG5, loadFundStore, generateSignals, resetPreStats } = require('./chuang/strategy');
const { applyPortfolio } = require('./chuang/risk');

config_portfolio_off();
function config_portfolio_off() {
  const c = CHUANG_CONFIG; c.portfolio.ddPause = 9.9; c.portfolio.maxBuyPerDay = 999;
}
const config = CHUANG_CONFIG;
const items = loadUniverse(config.src);
const index = loadIndex(config.indexFile);
const g5 = loadG5(config.fundFile);
const fund = loadFundStore(config.fundFile);
let switchIndex = null;
try { switchIndex = loadSwitchIndex(config.marketSwitch.indexFile, config.marketSwitch); } catch (e) {}
const baseCtx = { items, index, switchIndex, g5, fund, config, sectors: { byCode: {}, bySector: {} } };
const K = +(process.env.BT_K || config.execution.kAtr), H = +(process.env.BT_H || config.execution.maxHold);
const cfg = { kAtrDyn: K, maxHoldDyn: H, maxHoldMain: config.main.maxHold, boards: 'chuang_only',
              regime: process.env.BT_R || 'none', from: config.period.from, to: process.env.BT_TO || config.period.to };

function run(trig) {
  config.execution.E3_trailTrigger = trig;
  resetPreStats();
  let cands = [];
  items.forEach(s => { cands = cands.concat(generateSignals(s, cfg, baseCtx)); });
  return applyPortfolio(cands, config, index).trades;
}
function stat(trades) {
  const n = trades.length; if (!n) return null;
  const pos = trades.filter(t => t.ret > 0), neg = trades.filter(t => t.ret <= 0);
  const sp = pos.reduce((s, t) => s + t.ret, 0), sn = neg.reduce((s, t) => s + Math.abs(t.ret), 0);
  return { n, win: pos.length / n, exp: trades.reduce((s, t) => s + t.ret, 0) / n, pf: sn ? sp / sn : null };
}
const p = x => (x * 100).toFixed(2) + '%';
console.log('\n===== E3_trailTrigger 敏感度（修正引擎, kAtr=' + K + ' h=' + H + ' to=' + cfg.to + '）=====');
let base = null;
for (const trig of [0, 0.02, 0.03, 0.05]) {
  const s = stat(run(trig));
  if (!s) { console.log('trig=' + trig + ': 无样本'); continue; }
  const d = base ? (s.exp - base.exp) * 100 : 0;
  console.log('trig=' + String(trig).padEnd(5) + ': n=' + String(s.n).padStart(4) + '  胜率 ' + p(s.win).padStart(7)
    + '  期望 ' + p(s.exp).padStart(7) + (base ? ' (' + (d >= 0 ? '+' : '') + d.toFixed(2) + 'pp)' : '').padStart(9)
    + '  PF ' + (s.pf == null ? 'n/a' : s.pf.toFixed(3)));
  if (!base) base = s;
}
