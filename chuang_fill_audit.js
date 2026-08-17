'use strict';
// chuang_fill_audit.js — 出场成交价假设审计（只读诊断，不写生产文件）
//
// 背景：chuang_outcome_audit.js 已证实 summarize() 的 win/loss 标签有 bug
//       （跟踪止损出场一律记 loss，394/744 笔实为盈利），真实口径胜率 55.51% / 期望 +1.47%/笔。
// 本脚本回答第二个问题：这个 +1.47% 是否建立在乐观成交假设上？
//   引擎逻辑（strategy.js line 285-290）：若 low[j] <= curSL 则 exitPrice = curSL —— 无条件按止损价成交。
//   现实：若当日 open[j] 已低于 curSL（跳空穿越），实际只能按 open 成交，拿不到 curSL。
// 三个变体对照：
//   A 引擎原样        exit = curSL
//   B 跳空感知        exit = min(curSL, open[j])          ← 现实可成交价
//   C 跳空感知+滑点   B 的基础上双边各 0.3%（买入抬价/卖出压价）
// 同时输出「同日先冲高后回落」的口径差异：引擎当日不抬 curSL（次日才生效），比真实跟踪止损更宽松。

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
if (config.factors && config.factors.enabled) {
  const { buildFactorPass } = require('./chuang/factors');
  const b = buildFactorPass(config); ctx.factorPass = b.passByDate;
  console.log('因子层已构建:', JSON.stringify(b.stats));
}

const K = +(process.env.BT_K || 2.5), H = +(process.env.BT_H || 8);
const cfg = { kAtrDyn: K, maxHoldDyn: H, maxHoldMain: config.main.maxHold, boards: 'chuang_only',
              regime: process.env.BT_R || 'none', from: config.period.from, to: process.env.BT_TO || config.period.to };

resetPreStats();
let cands = [];
items.forEach(s => { cands = cands.concat(generateSignals(s, cfg, ctx)); });
const trades = applyPortfolio(cands, config, index).trades;

// 建 code → {bars, pos} 索引，用于重放出场路径
const barsBy = new Map();
items.forEach(s => {
  const day = (s.kline && s.kline.day) || [];
  const pos = new Map(); day.forEach((b, i) => pos.set(b[0], i));
  barsBy.set(s.code, { day, pos });
});

const TRAIL = config.execution.E3_trailPct;         // 0.02
const TRAILCAP = config.main.trailCap;              // 0.06
const SLIP = 0.003;

function replay(t, mode) {
  const rec = barsBy.get(t.code); if (!rec) return null;
  const i = rec.pos.get(t.signalDate); if (i == null) return null;
  const bars = rec.day;
  const entry = t.entry, sl = t.sl, tp = t.tp;
  const cap = entry * (1 + TRAILCAP);
  let curSL = sl, exitPrice = null, reason = null, gapped = false;
  for (let j = i + 1; j < bars.length && j <= i + H; j++) {
    const o = bars[j][1], h = bars[j][3], l = bars[j][4];
    if (l <= curSL) {
      if (mode === 'A') exitPrice = curSL;
      else { exitPrice = Math.min(curSL, o); if (o < curSL) gapped = true; }
      reason = (Math.abs(curSL - sl) < 1e-9) ? 'sl' : 'trail';
      break;
    }
    if (h >= tp) { exitPrice = tp; reason = 'tp'; break; }
    const nsl = Math.min(cap, Math.max(curSL, h * (1 - TRAIL)));
    if (nsl > curSL) curSL = nsl;
  }
  if (exitPrice == null) {
    const jl = Math.min(bars.length - 1, i + H); exitPrice = bars[jl][2]; reason = 'time';
  }
  let ret = (exitPrice - entry) / entry;
  if (mode === 'C') ret = (exitPrice * (1 - SLIP)) / (entry * (1 + SLIP)) - 1;
  return { ret, reason, gapped };
}

function stat(rows) {
  const n = rows.length; if (!n) return null;
  const pos = rows.filter(r => r.ret > 0), neg = rows.filter(r => r.ret <= 0);
  const sp = pos.reduce((s, r) => s + r.ret, 0), sn = neg.reduce((s, r) => s + Math.abs(r.ret), 0);
  return { n, win: pos.length / n, exp: rows.reduce((s, r) => s + r.ret, 0) / n,
           pf: sn ? sp / sn : null, avgWin: pos.length ? sp / pos.length : 0, avgLoss: neg.length ? sn / neg.length : 0 };
}
const p = (x) => (x * 100).toFixed(2) + '%';
function show(label, s) {
  if (!s) { console.log(label + ': 无样本'); return; }
  console.log(label.padEnd(26) + ': n=' + String(s.n).padStart(4) + '  胜率 ' + p(s.win).padStart(7)
    + '  期望 ' + p(s.exp).padStart(7) + '  PF ' + (s.pf == null ? 'n/a' : s.pf.toFixed(3)).padStart(6)
    + '  avgWin ' + p(s.avgWin).padStart(6) + '  avgLoss ' + p(s.avgLoss).padStart(6));
}

console.log('\n===== 出场成交价假设审计 (kAtr=' + K + ' h=' + H + ' to=' + cfg.to + ', 因子层=' + (config.factors.enabled ? 'ON' : 'OFF') + ') =====');
const A = trades.map(t => replay(t, 'A')).filter(Boolean);
const B = trades.map(t => replay(t, 'B')).filter(Boolean);
const C = trades.map(t => replay(t, 'C')).filter(Boolean);
show('A 引擎原样(exit=curSL)', stat(A));
show('B 跳空感知(min(curSL,open))', stat(B));
show('C B+双边0.3%滑点', stat(C));
const gap = B.filter(r => r.gapped).length;
console.log('跳空穿越止损笔数: ' + gap + ' / ' + B.length + ' (' + p(B.length ? gap / B.length : 0) + ')');
const byReason = {};
B.forEach(r => { (byReason[r.reason] = byReason[r.reason] || []).push(r); });
Object.keys(byReason).sort().forEach(k => show('  [B] 出场=' + k, stat(byReason[k])));

// 分年度（用真实口径 B 与 C）
const yr = {};
trades.forEach((t, idx) => {
  const y = t.year; (yr[y] = yr[y] || { b: [], c: [] });
  if (B[idx]) yr[y].b.push(B[idx]); if (C[idx]) yr[y].c.push(C[idx]);
});
console.log('分年度：');
Object.keys(yr).sort().forEach(y => { show('  ' + y + ' [B]', stat(yr[y].b)); show('  ' + y + ' [C]', stat(yr[y].c)); });
