'use strict';
// chuang_p0_verify.js — P0 修复前后严格对照（同候选、同数据）
// 用当前（已修复）generateSignals 生成候选，再对每笔候选分别重放：
//   OLD = 修复前 bug 出场（触及 curSL 记 loss + 无条件按 curSL 成交）
//   NEW = 修复后（跳空感知成交 min(curSL,open) + 胜负按 ret 符号）
// 两者候选完全相同 → 干净的 before/after，不受区间/宇宙漂移影响。
process.chdir('D:/WorkBuddy');
const { CHUANG_CONFIG } = require('./chuang/config');
const { loadUniverse, loadIndex, loadSwitchIndex } = require('./chuang/data');
const { loadG5, loadFundStore, generateSignals, resetPreStats } = require('./chuang/strategy');
const { applyPortfolio } = require('./chuang/risk');

const config = CHUANG_CONFIG;
const items = loadUniverse(config.src);
const index = loadIndex(config.indexFile);
const g5 = loadG5(config.fundFile);
const fund = loadFundStore(config.fundFile);
let switchIndex = null;
try { switchIndex = loadSwitchIndex(config.marketSwitch.indexFile, config.marketSwitch); } catch (e) {}
const ctx = { items, index, switchIndex, g5, fund, config, sectors: { byCode: {}, bySector: {} } };

const K = +(process.env.BT_K || config.execution.kAtr);
const H = +(process.env.BT_H || config.execution.maxHold);
const cfg = { kAtrDyn: K, maxHoldDyn: H, maxHoldMain: config.main.maxHold, boards: 'chuang_only',
              regime: process.env.BT_R || 'none', from: config.period.from, to: process.env.BT_TO || config.period.to };

resetPreStats();
let cands = [];
items.forEach(s => { cands = cands.concat(generateSignals(s, cfg, ctx)); });
const trades = applyPortfolio(cands, config, index).trades;

const barsBy = new Map();
items.forEach(s => {
  const day = (s.kline && s.kline.day) || [];
  const pos = new Map(); day.forEach((b, i) => pos.set(b[0], i));
  barsBy.set(s.code, { day, pos });
});

const TRAIL = config.execution.E3_trailPct, TRAILCAP = config.main.trailCap;

function replayOld(t) {
  const rec = barsBy.get(t.code); if (!rec) return null;
  const i = rec.pos.get(t.signalDate); if (i == null) return null;
  const bars = rec.day, entry = t.entry, sl = t.sl, tp = t.tp, cap = entry * (1 + TRAILCAP);
  let curSL = sl, exitPrice = entry, hit = null;
  for (let j = i + 1; j < bars.length && j <= i + H; j++) {
    const h = bars[j][3], l = bars[j][4];
    if (l <= curSL) { exitPrice = curSL; hit = 'sl'; break; }
    if (h >= tp) { exitPrice = tp; hit = 'tp'; break; }
    const nsl = Math.min(cap, Math.max(curSL, h * (1 - TRAIL))); if (nsl > curSL) curSL = nsl;
  }
  if (hit == null) exitPrice = bars[Math.min(bars.length - 1, i + H)][2];
  const outcome = hit == null ? (exitPrice >= entry ? 'win' : 'loss') : (hit === 'tp' ? 'win' : 'loss');
  return { ret: (exitPrice - entry) / entry, outcome };
}
function replayNew(t) {
  const rec = barsBy.get(t.code); if (!rec) return null;
  const i = rec.pos.get(t.signalDate); if (i == null) return null;
  const bars = rec.day, entry = t.entry, sl = t.sl, tp = t.tp, cap = entry * (1 + TRAILCAP);
  let curSL = sl, exitPrice = null;
  for (let j = i + 1; j < bars.length && j <= i + H; j++) {
    const o = bars[j][1], h = bars[j][3], l = bars[j][4];
    if (l <= curSL) { exitPrice = Math.min(curSL, o); break; }
    if (h >= tp) { exitPrice = tp; break; }
    const nsl = Math.min(cap, Math.max(curSL, h * (1 - TRAIL))); if (nsl > curSL) curSL = nsl;
  }
  if (exitPrice == null) exitPrice = bars[Math.min(bars.length - 1, i + H)][2];
  return { ret: (exitPrice - entry) / entry, outcome: exitPrice >= entry ? 'win' : 'loss' };
}

function stat(rows) {
  const n = rows.length; if (!n) return null;
  const pos = rows.filter(r => r.ret > 0), neg = rows.filter(r => r.ret <= 0);
  const sp = pos.reduce((s, r) => s + r.ret, 0), sn = neg.reduce((s, r) => s + Math.abs(r.ret), 0);
  return { n, win: pos.length / n, exp: rows.reduce((s, r) => s + r.ret, 0) / n,
           pf: sn ? sp / sn : null, avgWin: pos.length ? sp / pos.length : 0, avgLoss: neg.length ? sn / neg.length : 0 };
}
function show(label, s) {
  const p = x => (x * 100).toFixed(2) + '%';
  if (!s) { console.log(label + ': 无样本'); return; }
  console.log(label.padEnd(34) + ': n=' + String(s.n).padStart(4) + '  胜率 ' + p(s.win).padStart(7)
    + '  期望 ' + p(s.exp).padStart(7) + '  PF ' + (s.pf == null ? 'n/a' : s.pf.toFixed(3)).padStart(6));
}

const old = trades.map(replayOld).filter(Boolean);
const neu = trades.map(replayNew).filter(Boolean);
console.log('\n===== P0 修复前后对照（同候选 n=' + trades.length + ', kAtr=' + K + ' h=' + H + ' to=' + cfg.to + '）=====');
show('OLD 修复前(bug: 触发位定胜负+curSL成交)', stat(old));
show('NEW 修复后(跳空感知+ret符号定胜负)', stat(neu));
// 错标笔：OLD 记 loss 但 ret>0
const mis = old.filter((r, k) => r.outcome === 'loss' && neu[k] && neu[k].ret > 0).length;
console.log('OLD 误标亏损实为盈利的笔数: ' + mis + ' / ' + old.length + ' (' + ((mis / old.length) * 100).toFixed(2) + '%)');
