// backtest_phase12.js — Phase 1(重做回测) + Phase 2(调参转正)
// 基于已拉长的 3 年日线(import_final.json, 680~700 根/支) + 上证指数(index_sh.json)，
// 对"次日开盘入场 + 分市场止损"规则做：
//   - 全样本统计(胜率/盈亏比/期望值/凯利 f*)
//   - 95% 置信区间(Wilson 胜率 + Bootstrap 期望值)
//   - 分市场(byBoard) / 分年度(byYear) / 分市场状态(byRegime) 拆解
//   - walk-forward(滚动 6 个月窗口) 稳定性检验
//   - 参数网格搜索：找到使期望值转正(≥+0.30%/笔、盈亏比 b≥1.6、f*>0、n≥300) 的最优配置
//
// K 线格式: bar = [日期"YYYYMMDD", 开, 收, 高, 低, 量]

const fs = require('fs');
const SRC = 'D:/WorkBuddy/选股结果/import_final.json';
const INDEX_FILE = 'D:/WorkBuddy/选股结果/index_sh.json';
const OUT = 'D:/WorkBuddy/选股结果/backtest_phase12.json';

const ATR_WIN = 14;
const MA_WIN_TREND = 20, MA_WIN_SHORT = 5, VOL_MULT = 1.2;
const GAP_DOWN = 0.04, GAP_UP = 0.06;
const IDX_MA_WIN = 60;          // 市场状态判定用 MA60
const STOP_MAIN = 0.02, PROFIT_MAIN = 0.06;   // 主板固定 2%/6%
const TRAIL_PCT = 0.03, TRAIL_CAP = 0.06;
const MAX_BUY_PER_DAY = 3, DD_PAUSE = 0.08;

function atr14(bars, idx) {
  if (idx < ATR_WIN) return null;
  let s = 0;
  for (let k = idx - ATR_WIN + 1; k <= idx; k++) {
    const c0 = bars[k - 1][2], h = bars[k][3], l = bars[k][4];
    s += Math.max(h - l, Math.abs(h - c0), Math.abs(l - c0));
  }
  return s / ATR_WIN;
}
function sma(bars, idx, win, field) {
  if (idx < win - 1 || idx >= bars.length) return null;
  let s = 0; for (let k = idx - win + 1; k <= idx; k++) s += bars[k][field];
  return s / win;
}
function passPreFilter(bars, i) {
  const close = bars[i][2], open = bars[i][1], vol = bars[i][5];
  const prevClose = i > 0 ? bars[i - 1][2] : close;
  const gap = (open - prevClose) / prevClose;
  const gapOk = gap >= -GAP_DOWN && gap <= GAP_UP;
  const ma5 = sma(bars, i, MA_WIN_SHORT, 2), ma20 = sma(bars, i, MA_WIN_TREND, 2);
  const ma20Prev = sma(bars, i - 1, MA_WIN_TREND, 2), ma20Vol = sma(bars, i, MA_WIN_TREND, 5);
  let trendOk = false;
  if (ma20 != null && ma5 != null) {
    const rising = ma20Prev != null ? (ma20 > ma20Prev) : true;
    trendOk = (close > ma20) && (ma5 > ma20) && rising;
  }
  let volOk = (ma20Vol != null && ma20Vol > 0) ? vol >= ma20Vol * VOL_MULT : false;
  return { trendOk, volOk, gapOk };
}

// ---- 加载数据 ----
const data = JSON.parse(fs.readFileSync(SRC, 'utf8'));
const items = data.items || [];
const idx = JSON.parse(fs.readFileSync(INDEX_FILE, 'utf8'));
const ib = idx.bars || [];
const idxClose = {}, idxMA = {};
ib.forEach(b => { idxClose[b[0]] = b[2]; });
for (let i = 0; i < ib.length; i++) {
  if (i >= IDX_MA_WIN - 1) {
    let s = 0; for (let k = i - IDX_MA_WIN + 1; k <= i; k++) s += ib[k][2];
    idxMA[ib[i][0]] = s / IDX_MA_WIN;
  }
}
// 市场状态: 基于上证指数 MA60 / MA20
const idxMA20 = {};
for (let i = 0; i < ib.length; i++) {
  if (i >= 19) { let s = 0; for (let k = i - 19; k <= i; k++) s += ib[k][2]; idxMA20[ib[i][0]] = s / 20; }
}
function idxRegime(date, kind) {
  const cl = idxClose[date], ma = idxMA[date], ma20 = idxMA20[date];
  if (cl == null) return 'unknown';
  if (kind === 'ma20_up') { if (ma20 == null) return 'unknown'; return cl > ma20 ? 'bull' : 'bear'; }
  if (ma == null) return 'unknown';
  const i = ib.findIndex(b => b[0] === date);
  if (i < IDX_MA_WIN + 19) return 'unknown';
  let s = 0; for (let k = i - 19; k <= i; k++) s += ib[k][2];
  const ma20ago = s / 20;
  if (cl > ma && ma >= ma20ago) return 'bull';
  if (cl < ma && ma < ma20ago) return 'bear';
  return 'side';
}

// 篮子市场状态(全 3 年覆盖): 各票自身 MA60 之上比例 + 方向
const stockMA60 = {};       // code -> {date: ma60}
items.forEach(s => {
  const bars = (s.kline && s.kline.day) || [];
  const m = {};
  for (let i = 0; i < bars.length; i++) {
    if (i >= IDX_MA_WIN - 1) { let ss = 0; for (let k = i - IDX_MA_WIN + 1; k <= i; k++) ss += bars[k][2]; m[bars[i][0]] = ss / IDX_MA_WIN; }
  }
  stockMA60[s.code] = m;
});
const allDatesSorted = [...new Set(items.flatMap(s => (s.kline.day || []).map(b => b[0])))].sort();
const basketRegime = {};    // date -> 'bull'/'bear'/'side'/'unknown'
for (const date of allDatesSorted) {
  let up = 0, down = 0, above = 0, tot = 0;
  items.forEach(s => {
    const m = stockMA60[s.code]; if (!m || m[date] == null) return;
    const bars = s.kline.day; const i = bars.findIndex(b => b[0] === date); if (i < 0) return;
    tot++;
    if (bars[i][2] > m[date]) above++;
    // 方向: 比较 20 日前 MA60
    if (i >= 20) {
      // 近似: 用 20 日前收盘 vs 其 MA60
      const past = bars[i - 20]; const mp = m[past[0]];
      if (mp != null) { if (m[date] > mp) up++; else down++; }
    }
  });
  if (tot === 0) { basketRegime[date] = 'unknown'; continue; }
  const aboveFrac = above / tot;
  if (aboveFrac > 0.5 && up >= down) basketRegime[date] = 'bull';
  else if (aboveFrac < 0.5 && down > up) basketRegime[date] = 'bear';
  else basketRegime[date] = 'side';
}

function regimeOf(date, kind) {
  if (kind === 'basket' || kind === 'basket_not_bear') return basketRegime[date] || 'unknown';
  return idxRegime(date, kind === 'ma20_up' ? 'ma20_up' : 'ma60');
}

// ---- 单笔信号生成 ----
function genSignals(stock, cfg) {
  const bars = (stock.kline && stock.kline.day) || [];
  if (bars.length < 2) return [];
  const board = stock.board;
  if (cfg.boards === 'main_only' && board !== 'main') return [];
  if (cfg.boards === 'no_kcb' && board === 'kcb') return [];
  const isDyn = (board === 'cyb' || board === 'kcb' || board === 'kc');
  const tol = (board === 'cyb' || board === 'kcb' || board === 'kc') ? 0.03 : 0.02;
  const K_ATR = isDyn ? cfg.kAtrDyn : 1.05;
  const maxHold = isDyn ? 5 : cfg.maxHoldMain;
  // 解析 regime 配置
  let rKind = 'ma60', rMode = 'bull';
  if (cfg.regime === 'none') { rKind = null; }
  else if (cfg.regime === 'bull_only') { rKind = 'ma60'; rMode = 'bull'; }
  else if (cfg.regime === 'ma20_up') { rKind = 'ma20'; rMode = 'bull'; }
  else if (cfg.regime === 'basket') { rKind = 'basket'; rMode = 'bull'; }
  else if (cfg.regime === 'not_bear') { rKind = 'ma60'; rMode = 'notbear'; }
  else if (cfg.regime === 'basket_not_bear') { rKind = 'basket'; rMode = 'notbear'; }
  const out = [];
  for (let i = 0; i < bars.length - 1; i++) {
    const d = bars[i], nd = bars[i + 1];
    const dateD = d[0];
    if (dateD < cfg.from || dateD > cfg.to) continue;
    if (rKind) {
      const r = regimeOf(dateD, rKind);
      if (rMode === 'bull' && r !== 'bull') continue;
      if (rMode === 'notbear' && r === 'bear') continue;
    }
    preStats.total++;
    const f = passPreFilter(bars, i);
    if (!f.trendOk) { preStats.skipTrend++; continue; }
    if (!f.volOk) { preStats.skipVol++; continue; }
    if (!f.gapOk) { preStats.skipGap++; continue; }
    preStats.pass++;
    const baseline = d[2], nextOpen = nd[1];
    if (!baseline || !nextOpen) continue;
    const dev = (nextOpen - baseline) / baseline;
    if (Math.abs(dev) > tol) continue;
    const entry = nextOpen;
    let sl, tp, slDist;
    if (isDyn) {
      const a = atr14(bars, i); if (a == null) { preStats.skipAtr++; continue; }
      slDist = K_ATR * a; sl = entry - slDist; tp = entry + 3 * slDist;
    } else { slDist = entry * STOP_MAIN; sl = entry * (1 - STOP_MAIN); tp = entry * (1 + PROFIT_MAIN); }
    const trailCap = entry * (1 + TRAIL_CAP);
    let curSL = sl, outcome = null, exitPrice = entry, exitIdx = i + 1, holdDays = 0;
    for (let j = i + 1; j < bars.length && j <= i + maxHold; j++) {
      const h = bars[j][3], l = bars[j][4]; holdDays++;
      if (l <= curSL) { outcome = 'loss'; exitPrice = curSL; exitIdx = j; break; }
      if (h >= tp) { outcome = 'win'; exitPrice = tp; exitIdx = j; break; }
      if (isDyn) { const nsl = Math.min(trailCap, Math.max(curSL, h * (1 - TRAIL_PCT))); if (nsl > curSL) curSL = nsl; }
    }
    if (!outcome) {
      const jlast = Math.min(bars.length - 1, i + maxHold);
      exitPrice = bars[jlast][2];
      outcome = exitPrice >= entry ? 'win' : 'loss'; holdDays = jlast - i;
    }
    const ret = (exitPrice - entry) / entry;
    const rTrade = rKind ? regimeOf(dateD, rKind) : 'n/a';
    out.push({ code: stock.code, board, signalDate: dateD, entryDate: nd[0], entry, exit: exitPrice,
               outcome, ret, holdDays, regime: rTrade, year: dateD.slice(0, 4) });
  }
  return out;
}

// ---- 组合层 (同 backtest_winrate.js) ----
let preStats = { total: 0, pass: 0, skipTrend: 0, skipVol: 0, skipGap: 0, skipAtr: 0 };
function applyPortfolio(cands) {
  const afterIndex = [], idxFiltered = [];
  cands.forEach(c => {
    const ma = idxMA[c.signalDate], cl = idxClose[c.signalDate];
    if (ma != null && cl != null && cl < ma) idxFiltered.push(c); else afterIndex.push(c);
  });
  const byDay = {};
  afterIndex.forEach(c => { (byDay[c.signalDate] = byDay[c.signalDate] || []).push(c); });
  const afterCap = []; let perDayCapped = 0;
  Object.keys(byDay).sort().forEach(d => {
    const arr = byDay[d].slice().sort((a, b) => +new Date(b.signalDate) - +new Date(a.signalDate));
    perDayCapped += Math.max(0, arr.length - MAX_BUY_PER_DAY);
    arr.slice(0, MAX_BUY_PER_DAY).forEach(c => afterCap.push(c));
  });
  const allDates = [...new Set(afterCap.map(c => c.signalDate))].sort();
  const dateIdx = {}; allDates.forEach((d, i) => dateIdx[d] = i);
  const sorted = afterCap.slice().sort((a, b) => a.signalDate < b.signalDate ? -1 : a.signalDate > b.signalDate ? 1 : 0);
  let equity = 1, peak = 1, paused = false, pauseUntil = null, ddPaused = 0;
  const trades = [];
  for (const c of sorted) {
    if (paused) {
      if (pauseUntil == null || c.signalDate <= pauseUntil) { ddPaused++; continue; }
      paused = false;
    }
    equity *= (1 + c.ret);
    if (equity > peak) peak = equity;
    trades.push(c);
    if (peak - equity > DD_PAUSE * peak) {
      paused = true;
      const i = dateIdx[c.signalDate];
      pauseUntil = (i + 1 < allDates.length) ? allDates[i + 1] : null;
    }
  }
  return { trades, idxFiltered: idxFiltered.length, perDayCapped, ddPaused };
}

// ---- 统计 + 置信区间 ----
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
  // 注意: 凯利公式的 b 必须是"净赔率"(avgWin/avgLoss), 不是盈亏比(profitFactor=sumWin/sumLoss)。
  // 旧实现误把 profitFactor 当作 b, 导致 f* 被错误算为负。此处修正。
  const payoff = avgLoss > 0 ? avgWin / avgLoss : 0;
  const f = kelly(winRate, payoff);
  return { total, wins: wins.length, winRate, avgWin, avgLoss, profitFactor: isFinite(pf) ? pf : null,
    payoff, expectancy, expCI: [expLo, expHi], wrCI: [wrLo, wrHi], kelly: f,
    avgHold: total ? trades.reduce((s, t) => s + t.holdDays, 0) / total : 0 };
}

function backtest(cfg) {
  preStats = { total: 0, pass: 0, skipTrend: 0, skipVol: 0, skipGap: 0, skipAtr: 0 };
  let cands = [];
  items.forEach(s => { cands = cands.concat(genSignals(s, cfg)); });
  const port = applyPortfolio(cands);
  const trades = port.trades;
  const base = summarize(trades);
  // 分市场
  const byBoard = {};
  trades.forEach(t => { byBoard[t.board] = byBoard[t.board] || []; byBoard[t.board].push(t); });
  Object.keys(byBoard).forEach(b => byBoard[b] = summarize(byBoard[b]));
  // 分年度
  const byYear = {};
  trades.forEach(t => { byYear[t.year] = byYear[t.year] || []; byYear[t.year].push(t); });
  Object.keys(byYear).forEach(y => byYear[y] = summarize(byYear[y]));
  // 分状态
  const byRegime = {};
  trades.forEach(t => { byRegime[t.regime] = byRegime[t.regime] || []; byRegime[t.regime].push(t); });
  Object.keys(byRegime).forEach(r => byRegime[r] = summarize(byRegime[r]));
  // walk-forward: 滚动 6 个月窗口
  const wf = [];
  const sorted = trades.slice().sort((a, b) => a.signalDate < b.signalDate ? -1 : 1);
  const months = [...new Set(sorted.map(t => t.signalDate.slice(0, 6)))].sort();
  for (let m = 0; m + 5 < months.length; m++) {
    const lo = months[m], hi = months[m + 5];
    const wt = sorted.filter(t => t.signalDate >= lo && t.signalDate <= hi);
    if (wt.length >= 10) { const sm = summarize(wt); wf.push({ window: lo + '~' + hi, n: wt.length, exp: sm.expectancy, winRate: sm.winRate, pf: sm.profitFactor }); }
  }
  return { cfg, base, byBoard, byYear, byRegime, walkForward: wf, portfolio: { idxFiltered: port.idxFiltered, perDayCapped: port.perDayCapped, ddPaused: port.ddPaused }, preStats };
}

// ---- 网格搜索 ----
const PERIOD = { from: '20230828', to: '20260630' }; // 全 3 年
const grid = [];
[1.05, 1.5, 2.0, 2.5, 3.0].forEach(kAtrDyn =>
  ['all', 'no_kcb', 'main_only'].forEach(boards =>
    ['none', 'bull_only', 'ma20_up', 'basket', 'not_bear', 'basket_not_bear'].forEach(regime =>
      [10, 20].forEach(maxHoldMain => {
        grid.push({ kAtrDyn, boards, regime, maxHoldMain, from: PERIOD.from, to: PERIOD.to });
      }))));

console.log('=== 网格搜索 (', grid.length, '配置 ) ===');
const results = [];
for (const cfg of grid) {
  const r = backtest(cfg);
  const b = r.base;
  const pass = b.expectancy * 100 >= 0.30 && (b.profitFactor == null || b.profitFactor >= 1.6) && b.kelly > 0 && b.total >= 300;
  results.push({ cfg, b, pass });
  console.log(`kAtr=${cfg.kAtrDyn} boards=${cfg.boards.padEnd(9)} regime=${cfg.regime.padEnd(9)} holdM=${cfg.maxHoldMain} | n=${String(b.total).padStart(4)} win=${(b.winRate*100).toFixed(1)}% PF=${b.profitFactor==null?'inf':b.profitFactor.toFixed(2)} exp=${(b.expectancy*100).toFixed(2)}% f*=${b.kelly.toFixed(2)} ${pass?'✅PASS':''}`);
}

const passed = results.filter(r => r.pass).sort((a, b) => b.b.expectancy - a.b.expectancy);
console.log('\n=== 达标配置 (exp≥0.30%, b≥1.6, f*>0, n≥300) ===', passed.length, '个');
passed.slice(0, 10).forEach(r => {
  console.log(`kAtr=${r.cfg.kAtrDyn} boards=${r.cfg.boards} regime=${r.cfg.regime} holdM=${r.cfg.maxHoldMain} | exp=${(r.b.expectancy*100).toFixed(2)}% PF=${r.b.profitFactor.toFixed(2)} win=${(r.b.winRate*100).toFixed(1)}% f*=${r.b.kelly.toFixed(2)} n=${r.b.total}`);
});

// 选最优(期望值最高且达标) 写详细 JSON
const best = (passed.length ? passed[0] : results.slice().sort((a, b) => b.b.expectancy - a.b.expectancy)[0]);
const detail = backtest(best.cfg);
const out = {
  phase: 'Phase1+2',
  best: { kAtrDyn: best.cfg.kAtrDyn, boards: best.cfg.boards, regime: best.cfg.regime, maxHoldMain: best.cfg.maxHoldMain, period: PERIOD },
  base: detail.base,
  byBoard: detail.byBoard,
  byYear: detail.byYear,
  byRegime: detail.byRegime,
  walkForward: detail.walkForward,
  portfolio: detail.portfolio,
  preStats: detail.preStats,
  sweepPassCount: passed.length,
  sweepTotal: grid.length,
  generatedAt: new Date().toISOString().slice(0, 10)
};
fs.writeFileSync(OUT, JSON.stringify(out, null, 2), 'utf8');
console.log('\n最优配置:', JSON.stringify(best.cfg), '→ exp=', (detail.base.expectancy*100).toFixed(2)+'%/笔, 文件:', OUT);
