// backtest_chuang.js — Phase 3(双创独立策略体系)
// 基于已拉长的 3 年日线(import_final.json, 680~700 根/支) + 上证指数(index_sh.json)，
// 仅取双创(创业板 cyb / 科创板 kcb,kc)，复盘"止损加宽 K_ATR"，单独做一套适合双创的策略体系：
//   - 网格搜索 K_ATR(1.5~4.0) × 持有期(5/8/10/12日) × 市况(none/not_bear)
//   - 找到期望值转正(≥+0.30%/笔、盈亏比 b≥1.6、f*>0、n≥30) 的最优双创配置
//   - 与主板(main_only)分开统计交易胜率(byBoard: cyb / kcb)
// 复用 phase12 的引擎(genSignals/applyPortfolio/summarize/置信区间/walk-forward)，仅改 board 过滤与网格。

const fs = require('fs');
// 4.3：数据源可经环境变量切换，同一份策略代码既能跑 9 支(import_final)也能跑全市场(universe_klines)
const SRC = process.env.BT_SRC || 'D:/WorkBuddy/选股结果/import_final.json';
const INDEX_FILE = 'D:/WorkBuddy/选股结果/index_sh.json';
const OUT = process.env.BT_OUT || 'D:/WorkBuddy/选股结果/backtest_chuang.json';

const ATR_WIN = 14;
const MA_WIN_TREND = 20, MA_WIN_SHORT = 5, VOL_MULT = 1.2;
const GAP_DOWN = 0.04, GAP_UP = 0.06;
const IDX_MA_WIN = 60;
const STOP_MAIN = 0.02, PROFIT_MAIN = 0.06;
const TRAIL_PCT = 0.03, TRAIL_CAP = 0.06;
const MAX_BUY_PER_DAY = 3, DD_PAUSE = 0.08;

// ===== 双创升级 4.1：G1–G5 选股门（仅 chuang_only 板块生效，主板 main 完全不动）=====
// 回滚开关：CHUANG_GATES=0 node backtest_chuang.js  → 一键关闭全部新门
const CHUANG_GATES = process.env.CHUANG_GATES !== '0';
const G2_ATR_MIN = 0.03, G2_ATR_MAX = 0.06;          // G2 波动率带：入场日 ATR14% ∈ [3%,6%]
const G3_MA20_EXT = 0.12, G3_RSI_LO = 40, G3_RSI_HI = 65; // G3 动量洁净度：距MA20∈[0,+12%] 且 RSI∈[40,65]
const G1_LIQ_FLOOR = 1.0e8;                          // G1 流动性：近20日日均成交额 ≥ 1亿元（量(手)×100×价 近似）
const FUND_FILE = process.env.BT_FUND || 'D:/WorkBuddy/选股结果/fundamental.json';
// G5 盈利质量（4.0 边车数据）：仅当 g5Quality 显式为 false 才剔除；无数据(undefined)放行，防陈旧数据误杀
const G5 = {};
try { const fj = JSON.parse(fs.readFileSync(FUND_FILE, 'utf8')); Object.entries(fj.items || {}).forEach(([c, f]) => G5[c] = f.g5Quality === true); } catch (e) { }

function rsi14(bars, idx) {
  if (idx < ATR_WIN) return null;
  let g = 0, l = 0;
  for (let k = idx - ATR_WIN + 1; k <= idx; k++) { const ch = bars[k][2] - bars[k - 1][2]; if (ch > 0) g += ch; else l -= ch; }
  if (l === 0) return 100; const rs = g / l; return 100 - 100 / (1 + rs);
}
// 近20日日均成交额(元) = mean(vol[手]×100×close)
function avgTurnover20(bars, idx) {
  if (idx < 19) return null;
  let s = 0; for (let k = idx - 19; k <= idx; k++) s += bars[k][5] * 100 * bars[k][2];
  return s / 20;
}

// ===== 双创升级 4.2：E1–E3 执行层适配（仅 chuang_only，主板 3:1 完全不动）=====
// 回滚开关：CHUANG_EXEC=0 node backtest_chuang.js  → 关闭全部执行层改动
const CHUANG_EXEC = process.env.CHUANG_EXEC !== '0';
const E1_TP_R = 2.0, E1_TP_ATR = 1.8;   // E1 弹性止盈：TP = max(2.0×SL, 1.8×ATR14)（替代固定 3:1）
const E2_PULLBACK_TOL = 0.03;           // E2 回踩入场：信号bar低点须回踩至 MA20±3% 内且收在 MA20 上
const E3_TRAIL = 0.02;                  // E3 跟踪止损：3% → 2%（高波动下更快锁利）

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

const data = JSON.parse(fs.readFileSync(SRC, 'utf8'));
const items = data.items || [];
const idx = JSON.parse(fs.readFileSync(INDEX_FILE, 'utf8'));
const ib = idx.bars || [];
const idxClose = {}, idxMA = {};
ib.forEach(b => { idxClose[b[0]] = b[2]; });
const idxDates = ib.map(b => b[0]).sort();          // G4 相对强度用：指数交易日序列与位置
const idxPos = {}; idxDates.forEach((d, i) => idxPos[d] = i);
for (let i = 0; i < ib.length; i++) {
  if (i >= IDX_MA_WIN - 1) {
    let s = 0; for (let k = i - IDX_MA_WIN + 1; k <= i; k++) s += ib[k][2];
    idxMA[ib[i][0]] = s / IDX_MA_WIN;
  }
}
const idxMA20 = {}, idxMA20ago = {};
for (let i = 0; i < ib.length; i++) {
  if (i >= 19) { let s = 0; for (let k = i - 19; k <= i; k++) s += ib[k][2]; idxMA20[ib[i][0]] = s / 20; }
  if (i >= 19 + 20) { let s2 = 0; for (let k = i - 19 - 20; k <= i - 20; k++) s2 += ib[k][2]; idxMA20ago[ib[i][0]] = s2 / 20; }
}
function idxRegime(date, kind) {
  const cl = idxClose[date], ma = idxMA[date], ma20 = idxMA20[date];
  if (cl == null) return 'unknown';
  if (kind === 'ma20_up') { if (ma20 == null) return 'unknown'; return cl > ma20 ? 'bull' : 'bear'; }
  if (ma == null) return 'unknown';
  const ma20ago = idxMA20ago[date]; if (ma20ago == null) return 'unknown';   // 预计算，O(1)（原 findIndex O(n)）
  if (cl > ma && ma >= ma20ago) return 'bull';
  if (cl < ma && ma < ma20ago) return 'bear';
  return 'side';
}
// basket 市况仅在 regime 含 basket 时才需要；网格现只用 none/not_bear（走 idxRegime），
// 全市场(1949支)下 basketRegime 预计算 O(dates×items×findIndex) 过慢，默认跳过（BT_BASKET=1 才启用）。
const USE_BASKET = process.env.BT_BASKET === '1';
const stockMA60 = {}; const basketRegime = {};
if (USE_BASKET) {
  items.forEach(s => {
    const bars = (s.kline && s.kline.day) || [];
    const m = {};
    for (let i = 0; i < bars.length; i++) {
      if (i >= IDX_MA_WIN - 1) { let ss = 0; for (let k = i - IDX_MA_WIN + 1; k <= i; k++) ss += bars[k][2]; m[bars[i][0]] = ss / IDX_MA_WIN; }
    }
    stockMA60[s.code] = m;
  });
  const allDatesSorted = [...new Set(items.flatMap(s => (s.kline.day || []).map(b => b[0])))].sort();
  for (const date of allDatesSorted) {
    let up = 0, down = 0, above = 0, tot = 0;
    items.forEach(s => {
      const m = stockMA60[s.code]; if (!m || m[date] == null) return;
      const bars = s.kline.day; const i = bars.findIndex(b => b[0] === date); if (i < 0) return;
      tot++;
      if (bars[i][2] > m[date]) above++;
      if (i >= 20) {
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
}
function regimeOf(date, kind) {
  if (kind === 'basket' || kind === 'basket_not_bear') return basketRegime[date] || 'unknown';
  return idxRegime(date, kind === 'ma20_up' ? 'ma20_up' : 'ma60');
}

function genSignals(stock, cfg) {
  const bars = (stock.kline && stock.kline.day) || [];
  if (bars.length < 2) return [];
  const board = stock.board;
  if (cfg.boards === 'main_only' && board !== 'main') return [];
  if (cfg.boards === 'no_kcb' && board === 'kcb') return [];
  if (cfg.boards === 'chuang_only' && !['cyb', 'kcb', 'kc'].includes(board)) return [];
  const isDyn = (board === 'cyb' || board === 'kcb' || board === 'kc');
  // G5 盈利质量（股票级，4.0 边车）：仅当显式不达标(g5Quality===false)才剔除整只；无数据放行
  if (isDyn && CHUANG_GATES && G5[stock.code] === false) { preStats.skipG5++; return []; }
  const tol = (board === 'cyb' || board === 'kcb' || board === 'kc') ? 0.03 : 0.02;
  const K_ATR = isDyn ? cfg.kAtrDyn : 1.05;
  const maxHold = isDyn ? cfg.maxHoldDyn : cfg.maxHoldMain;
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
    // ===== 双创 G1–G4 逐日选股门（仅双创；主板在上方 board 过滤已 return，不经过此处）=====
    if (isDyn && CHUANG_GATES) {
      // G2 波动率带：ATR14% ∈ [3%,6%]
      const a0 = atr14(bars, i); const atrPct = a0 != null ? a0 / d[2] : null;
      if (atrPct == null || atrPct < G2_ATR_MIN || atrPct > G2_ATR_MAX) { preStats.skipG2++; continue; }
      // G3 动量洁净度：站上 MA20 且 距MA20 ∈ [0,+12%]，且 RSI(14) ∈ [40,65]
      const ma20g = sma(bars, i, MA_WIN_TREND, 2); const rrsi = rsi14(bars, i);
      if (ma20g == null || rrsi == null) { preStats.skipG3++; continue; }
      const ext = (d[2] - ma20g) / ma20g;
      if (ext < 0 || ext > G3_MA20_EXT || rrsi < G3_RSI_LO || rrsi > G3_RSI_HI) { preStats.skipG3++; continue; }
      // G1 流动性：近20日日均成交额 ≥ 1亿元
      const t20 = avgTurnover20(bars, i);
      if (t20 == null || t20 < G1_LIQ_FLOOR) { preStats.skipG1++; continue; }
      // G4 相对强度：个股近20日收益 > 上证同期收益（行业/个股有 beta 才做）
      const sr = i >= 20 ? d[2] / bars[i - 20][2] - 1 : null;
      const ip = idxPos[dateD]; const ir = (ip != null && ip >= 20) ? idxClose[idxDates[ip]] / idxClose[idxDates[ip - 20]] - 1 : null;
      if (sr == null || ir == null || sr <= ir) { preStats.skipG4++; continue; }
    }
    const baseline = d[2], nextOpen = nd[1];
    if (!baseline || !nextOpen) continue;
    const dev = (nextOpen - baseline) / baseline;
    if (Math.abs(dev) > tol) continue;
    // E2 回踩 MA20 不破才入场（仅双创，4.2）：信号bar低点回踩至 MA20±3% 内且收在 MA20 上，过滤追高
    if (isDyn && CHUANG_EXEC) {
      const ma20e = sma(bars, i, MA_WIN_TREND, 2); const lowI = bars[i][4];
      if (ma20e == null || lowI > ma20e * (1 + E2_PULLBACK_TOL) || d[2] < ma20e) { preStats.skipE2++; continue; }
    }
    const entry = nextOpen;
    let sl, tp, slDist;
    if (isDyn) {
      const a = atr14(bars, i); if (a == null) { preStats.skipAtr++; continue; }
      slDist = K_ATR * a; sl = entry - slDist;
      // E1 弹性止盈（4.2）：TP = max(2.0×SL, 1.8×ATR14)，替代固定 3:1；主板仍走下方固定 2%/6%
      tp = CHUANG_EXEC ? entry + Math.max(E1_TP_R * slDist, E1_TP_ATR * a) : entry + 3 * slDist;
    } else { slDist = entry * STOP_MAIN; sl = entry * (1 - STOP_MAIN); tp = entry * (1 + PROFIT_MAIN); }
    const trailPct = (isDyn && CHUANG_EXEC) ? E3_TRAIL : TRAIL_PCT;   // E3 跟踪止损 3%→2%（仅双创）
    const trailCap = entry * (1 + TRAIL_CAP);
    let curSL = sl, outcome = null, exitPrice = entry, exitIdx = i + 1, holdDays = 0;
    for (let j = i + 1; j < bars.length && j <= i + maxHold; j++) {
      const h = bars[j][3], l = bars[j][4]; holdDays++;
      if (l <= curSL) { outcome = 'loss'; exitPrice = curSL; exitIdx = j; break; }
      if (h >= tp) { outcome = 'win'; exitPrice = tp; exitIdx = j; break; }
      if (isDyn) { const nsl = Math.min(trailCap, Math.max(curSL, h * (1 - trailPct))); if (nsl > curSL) curSL = nsl; }
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

let preStats = { total: 0, pass: 0, skipTrend: 0, skipVol: 0, skipGap: 0, skipAtr: 0, skipG1: 0, skipG2: 0, skipG3: 0, skipG4: 0, skipG5: 0, skipE2: 0 };
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

function backtest(cfg) {
  preStats = { total: 0, pass: 0, skipTrend: 0, skipVol: 0, skipGap: 0, skipAtr: 0, skipG1: 0, skipG2: 0, skipG3: 0, skipG4: 0, skipG5: 0, skipE2: 0 };
  let cands = [];
  items.forEach(s => { cands = cands.concat(genSignals(s, cfg)); });
  const port = applyPortfolio(cands);
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
  return { cfg, base, byBoard, byYear, byRegime, walkForward: wf, portfolio: { idxFiltered: port.idxFiltered, perDayCapped: port.perDayCapped, ddPaused: port.ddPaused }, preStats, signalCodes: [...new Set(cands.map(c => c.code))] };
}

const PERIOD = { from: '20230828', to: '20260630' };
// 网格规模：BT_GRID=full(48) / quick(16，全市场加速) / single(单一配置快验，BT_K/BT_H/BT_R 可指定)
const GRID_MODE = process.env.BT_GRID || 'full';
let kList = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0], hList = [5, 8, 10, 12], rList = ['none', 'not_bear'];
if (GRID_MODE === 'quick') { kList = [2.5, 3.0, 3.5, 4.0]; hList = [5, 8]; }
if (GRID_MODE === 'single') { kList = [+(process.env.BT_K || 3)]; hList = [+(process.env.BT_H || 5)]; rList = [process.env.BT_R || 'none']; }
const grid = [];
kList.forEach(kAtrDyn =>
  ['chuang_only'].forEach(boards =>
    rList.forEach(regime =>
      hList.forEach(maxHoldDyn => {
        grid.push({ kAtrDyn, boards, regime, maxHoldDyn, maxHoldMain: 20, from: PERIOD.from, to: PERIOD.to });
      }))));

console.log('=== 双创网格搜索 (', grid.length, '配置 ) ===');
const results = [];
for (const cfg of grid) {
  const r = backtest(cfg);
  const b = r.base;
  const pass = b.expectancy * 100 >= 0.30 && (b.profitFactor == null || b.profitFactor >= 1.6) && b.kelly > 0 && b.total >= 30;
  results.push({ cfg, b, pass });
  console.log(`kAtr=${cfg.kAtrDyn} holdD=${cfg.maxHoldDyn} regime=${cfg.regime.padEnd(9)} | n=${String(b.total).padStart(4)} win=${(b.winRate*100).toFixed(1)}% PF=${b.profitFactor==null?'inf':b.profitFactor.toFixed(2)} exp=${(b.expectancy*100).toFixed(2)}% f*=${b.kelly.toFixed(2)} ${pass?'✅PASS':''}`);
}

const passed = results.filter(r => r.pass).sort((a, b) => b.b.expectancy - a.b.expectancy);
console.log('\n=== 双创达标配置 (exp≥0.30%, b≥1.6, f*>0, n≥30) ===', passed.length, '个');
passed.slice(0, 10).forEach(r => {
  console.log(`kAtr=${r.cfg.kAtrDyn} holdD=${r.cfg.maxHoldDyn} regime=${r.cfg.regime} | exp=${(r.b.expectancy*100).toFixed(2)}% PF=${r.b.profitFactor.toFixed(2)} win=${(r.b.winRate*100).toFixed(1)}% f*=${r.b.kelly.toFixed(2)} n=${r.b.total}`);
});

const best = (passed.length ? passed[0] : results.slice().sort((a, b) => b.b.expectancy - a.b.expectancy)[0]);
const detail = backtest(best.cfg);
const out = {
  phase: 'Phase3-chuang',
  best: { kAtrDyn: best.cfg.kAtrDyn, boards: best.cfg.boards, regime: best.cfg.regime, maxHoldDyn: best.cfg.maxHoldDyn, maxHoldMain: best.cfg.maxHoldMain, period: PERIOD },
  base: detail.base,
  byBoard: detail.byBoard,
  byYear: detail.byYear,
  byRegime: detail.byRegime,
  walkForward: detail.walkForward,
  portfolio: detail.portfolio,
  preStats: detail.preStats,
  signalCodes: detail.signalCodes,          // 产生信号的股票代码（供 4.3 两遍法抓 G5 基本面）
  sweepPassCount: passed.length,
  sweepTotal: grid.length,
  generatedAt: new Date().toISOString().slice(0, 10)
};
fs.writeFileSync(OUT, JSON.stringify(out, null, 2), 'utf8');
console.log('\n双创最优配置:', JSON.stringify(best.cfg), '→ exp=', (detail.base.expectancy*100).toFixed(2)+'%/笔, 文件:', OUT);
const ps = detail.preStats;
console.log(`\n=== 双创 G 门过滤效果（CHUANG_GATES=${CHUANG_GATES ? '开' : '关'}）===`);
console.log(`候选信号=${ps.total} 通过预过滤=${ps.pass} | G1流动性剔除=${ps.skipG1} G2波动带剔除=${ps.skipG2} G3动量洁净剔除=${ps.skipG3} G4相对强度剔除=${ps.skipG4} G5盈利质量剔除(整只)=${ps.skipG5} E2回踩入场剔除=${ps.skipE2}`);
console.log(`执行层: CHUANG_EXEC=${CHUANG_EXEC ? '开(E1弹性止盈/E2回踩/E3跟踪2%)' : '关(固定3:1)'} | byBoard盈亏比:`, JSON.stringify(Object.fromEntries(Object.entries(detail.byBoard).map(([b, s]) => [b, +(s.payoff).toFixed(2)]))));
console.log(`最优配置 byBoard:`, JSON.stringify(Object.fromEntries(Object.entries(detail.byBoard).map(([b, s]) => [b, { n: s.total, win: +(s.winRate * 100).toFixed(1), exp: +(s.expectancy * 100).toFixed(2) }]))));
