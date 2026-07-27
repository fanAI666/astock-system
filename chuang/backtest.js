'use strict';
// chuang/backtest.js — 回测引擎（移植旧 backtest_chuang.js 的 summarize/置信区间/walk-forward/backtest + 网格扫描）
// 产出 schema 与旧 backtest_chuang.json 完全等价（parity）：
//   backtest() -> { cfg, base, byBoard, byYear, byRegime, walkForward, portfolio, preStats, signalCodes }
// runSweep() 组装最终 out 并写盘（含 phase/best/sweepPassCount/sweepTotal/generatedAt）。

const fs = require('fs');
const { Logger } = require('./logger');
const { CHUANG_CONFIG, buildGrid } = require('./config');
const { generateSignals, resetPreStats, getPreStats } = require('./strategy');
const { applyPortfolio } = require('./risk');

// ===== 统计工具（与旧逐字等价）=====
function wilsonCI(k, n, z = 1.96) {
  if (n === 0) return [0, 0];
  const p = k / n, denom = 1 + z * z / n;
  const centre = (p + z * z / (2 * n)) / denom;
  const half = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom;
  return [Math.max(0, centre - half), Math.min(1, centre + half)];
}
function bootstrapExp(rets, iter = 2000, seed = 12345) {
  let s = seed; const rnd = () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; };
  const n = rets.length; if (n === 0) return [0, 0];
  const exps = [];
  for (let it = 0; it < iter; it++) {
    let s2 = 0; for (let k = 0; k < n; k++) s2 += rets[Math.floor(rnd() * n)];
    exps.push(s2 / n);
  }
  exps.sort((a, b) => a - b);
  return [exps[Math.floor(0.025 * iter)], exps[Math.floor(0.975 * iter)]];
}
function kelly(p, b) { return b > 0 ? p - (1 - p) / b : -Infinity; }

function summarize(trades) {
  const total = trades.length;
  const wins = trades.filter(t => t.outcome === 'win');
  const losses = trades.filter(t => t.outcome === 'loss');
  const winRate = total ? wins.length / total : 0;
  const avgWin = wins.length ? wins.reduce((s, t) => s + t.ret, 0) / wins.length : 0;
  const avgLoss = losses.length ? losses.reduce((s, t) => s + Math.abs(t.ret), 0) / losses.length : 0;
  const sumWin = wins.reduce((s, t) => s + t.ret, 0), sumLoss = losses.reduce((s, t) => s + Math.abs(t.ret), 0);
  const pf = sumLoss ? sumWin / sumLoss : (sumWin ? Infinity : 0);
  const expectancy = winRate * avgWin - (1 - winRate) * avgLoss;
  const rets = trades.map(t => t.ret);
  const [expLo, expHi] = bootstrapExp(rets);
  const [wrLo, wrHi] = wilsonCI(wins.length, total);
  const payoff = avgLoss > 0 ? avgWin / avgLoss : 0;
  const f = kelly(winRate, payoff);
  return { total, wins: wins.length, winRate, avgWin, avgLoss, profitFactor: isFinite(pf) ? pf : null,
    payoff, expectancy, expCI: [expLo, expHi], wrCI: [wrLo, wrHi], kelly: f,
    avgHold: total ? trades.reduce((s, t) => s + t.holdDays, 0) / total : 0 };
}

// ===== 单次回测（与旧 backtest(cfg) 等价，ctx 携带 items/index/g5/fund/config）=====
function backtest(cfg, ctx) {
  resetPreStats();
  let cands = [];
  ctx.items.forEach(s => { cands = cands.concat(generateSignals(s, cfg, ctx)); });
  const port = applyPortfolio(cands, ctx.config, ctx.index);
  const trades = port.trades;
  const base = summarize(trades);
  const byBoard = {};
  trades.forEach(t => { byBoard[t.board] = byBoard[t.board] || []; byBoard[t.board].push(t); });
  Object.keys(byBoard).forEach(b => byBoard[b] = summarize(byBoard[b]));
  const byYear = {};
  trades.forEach(t => { byYear[t.year] = byYear[t.year] || []; byYear[t.year].push(t); });
  Object.keys(byYear).forEach(y => byYear[y] = summarize(byYear[y]));
  const byRegime = {};
  trades.forEach(t => { byRegime[t.regime] = byRegime[t.regime] || []; byRegime[t.regime].push(t); });
  Object.keys(byRegime).forEach(r => byRegime[r] = summarize(byRegime[r]));
  const wf = [];
  const sorted = trades.slice().sort((a, b) => a.signalDate < b.signalDate ? -1 : 1);
  const months = [...new Set(sorted.map(t => t.signalDate.slice(0, 6)))].sort();
  for (let m = 0; m + 5 < months.length; m++) {
    const lo = months[m], hi = months[m + 5];
    const wt = sorted.filter(t => t.signalDate >= lo && t.signalDate <= hi);
    if (wt.length >= 10) { const sm = summarize(wt); wf.push({ window: lo + '~' + hi, n: wt.length, exp: sm.expectancy, winRate: sm.winRate, pf: sm.profitFactor }); }
  }
  // portfolio 仅保留三项诊断计数（与旧 backtest_chuang.json schema 严格一致；trades 不写入，避免 schema 漂移）
  return { cfg, base, byBoard, byYear, byRegime, walkForward: wf,
           portfolio: { idxFiltered: port.idxFiltered, perDayCapped: port.perDayCapped, ddPaused: port.ddPaused },
           preStats: getPreStats(), signalCodes: [...new Set(cands.map(c => c.code))] };
}

// ===== 网格扫描 + 写盘（复刻旧 backtest_chuang.js 顶层逻辑）=====
function runSweep(userConfig, ctx) {
  const config = userConfig || CHUANG_CONFIG;
  const grid = buildGrid(config);
  const pc = config.passCriteria;
  Logger.info('BT', `双创网格搜索 (${grid.length} 配置)`);
  const results = [];
  for (const cfg of grid) {
    const r = backtest(cfg, ctx);
    const b = r.base;
    const pass = b.expectancy * 100 >= pc.expMin && (b.profitFactor == null || b.profitFactor >= pc.pfMin) && b.kelly > 0 && b.total >= pc.nMin;
    results.push({ cfg, b, pass });
    Logger.progress('BT', `kAtr=${cfg.kAtrDyn} holdD=${cfg.maxHoldDyn} regime=${cfg.regime.padEnd(9)} | n=${String(b.total).padStart(4)} win=${(b.winRate*100).toFixed(1)}% PF=${b.profitFactor==null?'inf':b.profitFactor.toFixed(2)} exp=${(b.expectancy*100).toFixed(2)}% f*=${b.kelly.toFixed(2)} ${pass?'PASS':''}`);
  }
  const passed = results.filter(r => r.pass).sort((a, b) => b.b.expectancy - a.b.expectancy);
  Logger.info('BT', `双创达标配置 (exp≥${pc.expMin}%, b≥${pc.pfMin}, f*>0, n≥${pc.nMin}) ${passed.length} 个`);
  passed.slice(0, 10).forEach(r => {
    Logger.info('BT', `kAtr=${r.cfg.kAtrDyn} holdD=${r.cfg.maxHoldDyn} regime=${r.cfg.regime} | exp=${(r.b.expectancy*100).toFixed(2)}% PF=${r.b.profitFactor.toFixed(2)} win=${(r.b.winRate*100).toFixed(1)}% f*=${r.b.kelly.toFixed(2)} n=${r.b.total}`);
  });
  const best = (passed.length ? passed[0] : results.slice().sort((a, b) => b.b.expectancy - a.b.expectancy)[0]);
  const detail = backtest(best.cfg, ctx);
  const out = {
    phase: 'Phase3-chuang',
    best: { kAtrDyn: best.cfg.kAtrDyn, boards: best.cfg.boards, regime: best.cfg.regime, maxHoldDyn: best.cfg.maxHoldDyn, maxHoldMain: best.cfg.maxHoldMain, period: config.period },
    base: detail.base,
    byBoard: detail.byBoard,
    byYear: detail.byYear,
    byRegime: detail.byRegime,
    walkForward: detail.walkForward,
    portfolio: detail.portfolio,
    preStats: detail.preStats,
    signalCodes: detail.signalCodes,
    sweepPassCount: passed.length,
    sweepTotal: grid.length,
    generatedAt: new Date().toISOString().slice(0, 10),
  };
  fs.writeFileSync(config.out, JSON.stringify(out, null, 2), 'utf8');
  Logger.info('BT', `双创最优配置: ${JSON.stringify(best.cfg)} → exp=${(detail.base.expectancy*100).toFixed(2)}%/笔, 文件: ${config.out}`);
  const ps = detail.preStats;
  Logger.info('BT', `G 门过滤: 候选=${ps.total} 通过预过滤=${ps.pass} | G1=${ps.skipG1} G2=${ps.skipG2} G3=${ps.skipG3} G4=${ps.skipG4} G5整只=${ps.skipG5} E2=${ps.skipE2}`);
  Logger.info('BT', `byBoard: ${JSON.stringify(Object.fromEntries(Object.entries(detail.byBoard).map(([b, s]) => [b, { n: s.total, win: +(s.winRate*100).toFixed(1), exp: +(s.expectancy*100).toFixed(2) }])))}`);
  return out;
}

module.exports = { wilsonCI, bootstrapExp, kelly, summarize, backtest, runSweep };
