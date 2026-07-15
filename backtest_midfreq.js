// 中频波段回测（验证用，独立于高频 backtest_winrate.js）
//
// 与高频(v1.0.9)的核心差异：
//   - 止损/止盈放宽：主板 −3.5%/+10%（高频 −2%/+6%）；双创 ATR×1.8 / 止盈×3（高频 ATR×1.05）
//   - 持仓窗口拉长：主板 ≤20天（高频≤10），双创 ≤12天（高频≤5）
//   - 跟踪止盈：主板也走 MA5 跟踪（高频仅双创有跟踪止损）
//   - 跟踪封顶放宽：10%（高频6%）
//   - 入场新增：MACD(12,26,9) 金叉确认（高频无此要求）
//   - 组合层⑤保留不变（大盘硬过滤/同日上限/回撤上限）
//
// 数据源与高频共用：import_final.json (320根kline) + index_sh.json
// 输出独立：backtest_midfreq.json（不覆盖任何高频产物）

const fs = require('fs');

const SRC = 'D:/WorkBuddy/选股结果/import_final.json';
const IDX_FILE = 'D:/WorkBuddy/选股结果/index_sh.json';
const OUT = 'D:/WorkBuddy/选股结果/backtest_midfreq.json';

const PERIOD = { from: '20250701', to: '20260630' };

// ========== 中频参数集（vs 高频对照） ==========
const MAX_HOLD_MAIN = 20;    // 高频=10 → 拉长到约4周
const MAX_HOLD_DYN  = 12;    // 高频=5  → 拉长到约2.5周
const K_ATR    = 1.80;       // 高频=1.05 → 给双创更多波动空间
const TRAIL_PCT = 0.04;       // 高频=0.03 → 跟踪回撤稍宽
const TRAIL_CAP = 0.10;       // 高频=0.06 → 跟踪封顶10%
const ATR_WIN  = 14;

// 主板固定止损/止盈（中频放宽）
const MAIN_STOP_PCT = 0.035; // 高频=0.02 → −3.5%
const MAIN_TP_PCT   = 0.10;  // 高频=0.06 → +10%

// MACD 参数（新增入场确认）
const MACD_FAST  = 12;
const MACD_SLOW = 26;
const MACD_SIG  = 9;

// 前置过滤参数（与高频一致）
const MA_WIN_TREND = 20;
const MA_WIN_SHORT = 5;
const VOL_MULT     = 1.2;
const GAP_DOWN     = 0.04;
const GAP_UP       = 0.06;

// 组合层⑤参数（与高频一致）
const MAX_BUY_PER_DAY = 3;
const DD_PAUSE       = 0.08;
const IDX_MA_WIN     = 20;


// ========== 工具函数 ==========

function atr14(bars, idx) {
  if (idx < ATR_WIN) return null;
  let s = 0;
  for (let k = idx - ATR_WIN + 1; k <= idx; k++) {
    const c0 = bars[k - 1][2];
    const h = bars[k][3], l = bars[k][4];
    s += Math.max(h - l, Math.abs(h - c0), Math.abs(l - c0));
  }
  return s / ATR_WIN;
}

function sma(bars, idx, win, field) {
  if (idx < win - 1 || idx >= bars.length) return null;
  let s = 0;
  for (let k = idx - win + 1; k <= idx; k++) s += bars[k][field];
  return s / win;
}

// EMA 用于 MACD 计算
function ema(bars, idx, win, field) {
  if (idx < 0 || idx >= bars.length) return null;
  if (idx === 0) return bars[0][field];
  const prev = ema(bars, idx - 1, win, field);
  if (prev == null) return null;
  const k = 2 / (win + 1);
  return bars[idx][field] * k + prev * (1 - k);
}

// MACD 趋势确认（放宽版）：DIF = EMA12(close) - EMA26(close) > 0
// 即短期均线上方长期均线，处于多头趋势中（不要求刚发生金叉）
function macdTrendUp(bars, i) {
  if (i < MACD_SLOW) return false; // 需要足够历史算慢线

  const ema12 = ema(bars, i, MACD_FAST, 2);
  const ema26 = ema(bars, i, MACD_SLOW, 2);
  if (ema12 == null || ema26 == null) return false;

  const dif = ema12 - ema26;
  return dif > 0; // DIF > 0 = 多头趋势
}

// 前置过滤（与高频一致）
function passPreFilter(bars, i) {
  const close = bars[i][2];
  const open = bars[i][1];
  const vol = bars[i][5];
  const prevClose = i > 0 ? bars[i - 1][2] : close;

  const gap = (open - prevClose) / prevClose;
  const gapOk = gap >= -GAP_DOWN && gap <= GAP_UP;

  const ma5 = sma(bars, i, MA_WIN_SHORT, 2);
  const ma20 = sma(bars, i, MA_WIN_TREND, 2);
  const ma20Prev = sma(bars, i - 1, MA_WIN_TREND, 2);
  const ma20Vol = sma(bars, i, MA_WIN_TREND, 5);

  let trendOk = false;
  if (ma20 != null && ma5 != null) {
    const rising = ma20Prev != null ? (ma20 > ma20Prev) : true;
    trendOk = (close > ma20) && (ma5 > ma20) && rising;
  }
  let volOk = false;
  if (ma20Vol != null && ma20Vol > 0) volOk = vol >= ma20Vol * VOL_MULT;

  return { trendOk, volOk, gapOk };
}


// ========== 主流程 ==========

const data = JSON.parse(fs.readFileSync(SRC, 'utf8'));
const items = data.items || [];

// 数据区间
let dataFrom = '99999999', dataTo = '00000000';
items.forEach(s => {
  const bars = (s.kline && s.kline.day) || [];
  bars.forEach(b => { if (b[0] < dataFrom) dataFrom = b[0]; if (b[0] > dataTo) dataTo = b[0]; });
});
const fmt = d => d.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3');

// 排序
const ranked = items.slice().sort((a, b) => (b.win || 0) - (a.win || 0));
const top3 = ranked.slice(0, 3);

const skippedNoData = [];
const skippedNoAtr = [];
const preStats = { total: 0, pass: 0, skipTrend: 0, skipVol: 0, skipGap: 0, skipMacd: 0 };
const candidates = [];

function tolFor(board) {
  if (board === 'cyb' || board === 'kcb' || board === 'kc') return 0.03;
  return 0.02;
}

function genSignals(stock) {
  const bars = (stock.kline && stock.kline.day) || [];
  if (bars.length < 2) { skippedNoData.push(stock.code); return; }
  const board = stock.board;
  const isDyn = (board === 'cyb' || board === 'kcb' || board === 'kc');
  const tol = tolFor(board);

  for (let i = 0; i < bars.length - 1; i++) {
    const d = bars[i], nd = bars[i + 1];
    const dateD = d[0];
    if (dateD < PERIOD.from || dateD > PERIOD.to) continue;

    const baseline = d[2];

    // 前置过滤（趋势 + 量能 + 缺口）
    preStats.total++;
    const f = passPreFilter(bars, i);
    if (!f.trendOk) { preStats.skipTrend++; continue; }
    if (!f.volOk)   { preStats.skipVol++;   continue; }
    if (!f.gapOk)   { preStats.skipGap++;   continue; }

    // ★ 新增：MACD 趋势确认（DIF > 0）
    if (!macdTrendUp(bars, i)) { preStats.skipMacd++; continue; }

    preStats.pass++;

    const nextOpen = nd[1];
    if (!baseline || !nextOpen) continue;
    const dev = (nextOpen - baseline) / baseline;
    if (Math.abs(dev) > tol) continue;
    const entry = nextOpen;

    // ★ 中频止损/止盈设定
    let sl, tp, maxHold, slDist;
    if (isDyn) {
      const a = atr14(bars, i);
      if (a == null) { skippedNoAtr.push(stock.code); continue; }
      slDist = K_ATR * a;
      sl = entry - slDist;
      tp = entry + 3 * slDist;          // 保持 3:1 盈亏比
      maxHold = MAX_HOLD_DYN;
    } else {
      // ★ 主板：放宽固定止损止盈
      slDist = entry * MAIN_STOP_PCT;
      sl = entry * (1 - MAIN_STOP_PCT);   // −3.5%
      tp = entry * (1 + MAIN_TP_PCT);      // +10%
      maxHold = MAX_HOLD_MAIN;
    }

    // 跟踪止损参数（中频：主板也跟踪 + 封顶更宽）
    const trailCap = entry * (1 + TRAIL_CAP);
    let curSL = sl;

    let outcome = null, exitPrice = entry, exitIdx = i + 1, holdDays = 0;

    for (let j = i + 1; j < bars.length && j <= i + maxHold; j++) {
      const h = bars[j][3], l = bars[j][4];
      holdDays++;

      // 止损/跟踪止损检查
      if (l <= curSL) { outcome = 'loss'; exitPrice = curSL; exitIdx = j; break; }
      if (h >= tp)    { outcome = 'win';  exitPrice = tp;    exitIdx = j; break; }

      // ★ 跟踪止损上移（中频：主板+双创都启用，封顶10%）
      const newSL = Math.min(trailCap, Math.max(curSL, h * (1 - TRAIL_PCT)));
      if (newSL > curSL) curSL = newSL;
    }

    if (!outcome) {
      const jlast = Math.min(bars.length - 1, i + maxHold);
      exitPrice = bars[jlast][2];
      outcome = exitPrice >= entry ? 'win' : 'loss';
      holdDays = jlast - i;
    }

    const ret = (exitPrice - entry) / entry;
    candidates.push({
      code: stock.code, name: stock.name, board, isDyn,
      signalDate: dateD, entryDate: nd[0],
      baseline: +baseline.toFixed(4), entry: +entry.toFixed(4),
      slDist: +slDist.toFixed(4), maxHold,
      exitDate: bars[exitIdx][0], exit: +exitPrice.toFixed(4),
      dev: +dev.toFixed(5), tol, outcome, ret: +ret.toFixed(5), holdDays,
      predicted: stock.win
    });
  }
}

// 全候选池回测
items.forEach(genSignals);


// ==================== ⑤ 组合层约束（与高频一致） ====================

let idxClose = {}, idxMA20 = {};
try {
  const idx = JSON.parse(fs.readFileSync(IDX_FILE, 'utf8'));
  const ib = idx.bars || [];
  ib.forEach(b => { idxClose[b[0]] = b[2]; });
  for (let i = 0; i < ib.length; i++) {
    if (i >= IDX_MA_WIN - 1) {
      let s = 0; for (let k = i - IDX_MA_WIN + 1; k <= i; k++) s += ib[k][2];
      idxMA20[ib[i][0]] = s / IDX_MA_WIN;
    }
  }
} catch (e) { console.log('⚠ 未加载上证指数:', e.message); }

// (1) 大盘硬过滤
const idxFiltered = [], afterIndex = [];
const idxBearishDays = new Set();
candidates.forEach(c => {
  const ma = idxMA20[c.signalDate], cl = idxClose[c.signalDate];
  if (ma != null && cl != null && cl < ma) { idxFiltered.push(c); idxBearishDays.add(c.signalDate); }
  else afterIndex.push(c);
});

// (2) 同日上限
const byDay = {};
afterIndex.forEach(c => { (byDay[c.signalDate] = byDay[c.signalDate] || []).push(c); });
const afterCap = [];
let perDayCapped = 0;
Object.keys(byDay).sort().forEach(d => {
  const arr = byDay[d].slice().sort((a, b) => (b.predicted || 0) - (a.predicted || 0));
  perDayCapped += Math.max(0, arr.length - MAX_BUY_PER_DAY);
  arr.slice(0, MAX_BUY_PER_DAY).forEach(c => afterCap.push(c));
});

// (3) 回撤上限
const allDates = [...new Set(afterCap.map(c => c.signalDate))].sort();
const dateIdx = {}; allDates.forEach((d, i) => dateIdx[d] = i);
const ddSorted = afterCap.slice().sort((a, b) =>
  a.signalDate < b.signalDate ? -1 : a.signalDate > b.signalDate ? 1 : (b.predicted || 0) - (a.predicted || 0));
let equity = 1, peak = 1, paused = false, pauseUntil = null, ddPaused = 0;
const trades = [];
for (const c of ddSorted) {
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

const portfolio = {
  enabled: true,
  mode: 'midFreq',
  indexFilter:   { rule: '上证指数收盘<MA20(20日) -> 当日全市场不交易', dropped: idxFiltered.length, bearishDays: idxBearishDays.size },
  perDayCap:     { max: MAX_BUY_PER_DAY, rule: '每个信号日最多开仓 ' + MAX_BUY_PER_DAY + ' 笔', dropped: perDayCapped },
  drawdownPause: { threshold: DD_PAUSE, rule: '权益曲线自峰值回撤>' + (DD_PAUSE * 100).toFixed(0) + '% -> 暂停下一交易日', dropped: ddPaused },
  finalTrades: trades.length,
  stageCounts: { raw: candidates.length, afterIndex: afterIndex.length, afterCap: afterCap.length, final: trades.length }
};


// ========== 统计（与高频结构一致） ==========

const total = trades.length;
const wins = trades.filter(t => t.outcome === 'win');
const losses = trades.filter(t => t.outcome === 'loss');
const winRate = total ? wins.length / total : 0;
const avgWin = wins.length ? wins.reduce((s, t) => s + t.ret, 0) / wins.length : 0;
const avgLoss = losses.length ? losses.reduce((s, t) => s + Math.abs(t.ret), 0) / losses.length : 0;
const sumWin = wins.reduce((s, t) => s + t.ret, 0);
const sumLoss = losses.reduce((s, t) => s + Math.abs(t.ret), 0);
const profitFactor = sumLoss ? sumWin / sumLoss : (sumWin ? Infinity : 0);
const avgHold = total ? trades.reduce((s, t) => s + t.holdDays, 0) / total : 0;

const byBoard = {};
trades.forEach(t => {
  const b = t.board;
  byBoard[b] = byBoard[b] || { trades: 0, wins: 0 };
  byBoard[b].trades++;
  if (t.outcome === 'win') byBoard[b].wins++;
});
Object.keys(byBoard).forEach(b => {
  const o = byBoard[b];
  o.winRate = o.trades ? +(o.wins / o.trades).toFixed(4) : 0;
});

const byWinTier = {
  high: { predMin: 70, trades: 0, wins: 0 },
  low:  { predMin: 0, trades: 0, wins: 0 }
};
trades.forEach(t => {
  const tier = (t.predicted >= 70) ? byWinTier.high : byWinTier.low;
  tier.trades++;
  if (t.outcome === 'win') tier.wins++;
});
Object.keys(byWinTier).forEach(k => {
  const o = byWinTier[k];
  o.winRate = o.trades ? +(o.wins / o.trades).toFixed(4) : 0;
});

const perStock = {};
trades.forEach(t => {
  perStock[t.code] = perStock[t.code] || { code: t.code, name: t.name, board: t.board, predicted: t.predicted, trades: 0, wins: 0 };
  perStock[t.code].trades++;
  if (t.outcome === 'win') perStock[t.code].wins++;
});
const perStockArr = Object.values(perStock).map(o => {
  o.realized = o.trades ? +(o.wins / o.trades).toFixed(4) : 0;
  return o;
});
const predList = perStockArr.map(o => o.predicted).filter(v => v != null);
const predMean = predList.length ? predList.reduce((s, v) => s + v, 0) / predList.length : 0;
const calibBias = +(predMean / 100 - winRate).toFixed(4);

const expectancy = winRate * avgWin - (1 - winRate) * avgLoss;

const result = {
  mode: 'midFreq',
  label: '中频波段回测（验证用）',
  metric: 'winRate',
  period: { from: '2025-07-01', to: '2026-06-30' },
  dataRange: { from: fmt(dataFrom), to: fmt(dataTo) },
  winRate: +winRate.toFixed(4),
  trades: total,
  wins: wins.length,
  losses: losses.length,
  avgWin: +avgWin.toFixed(4),
  avgLoss: +avgLoss.toFixed(4),
  profitFactor: isFinite(profitFactor) ? +profitFactor.toFixed(2) : null,
  expectancy: +expectancy.toFixed(4),
  avgHoldDays: +avgHold.toFixed(2),
  universe: items.length,
  pool: 'full',

  // ★ 中频规则描述
  ruleMain: '主板：止损−3.5%/止盈+10%（固定~2.86:1），持有≤20日，MA5跟踪止损(回撤4%,封顶10%)',
  ruleDyn: '创业板/科创板：先过趋势(站上MA20+MA5>MA20+MA20上行)+量能(≥1.2×20日均量)+缺口(±4%~6%)+MACD趋势确认(DIF>0)；通过后走动态止损=入场价−1.8×ATR(14)，止盈×3(保持3:1)，持有封顶12日+跟踪止损(回撤4%,封顶10%)',
  ruleFilterAll: '全市场(主板+双创)：趋势+量能+缺口 过滤 + MACD趋势确认(DIF>0)（中频新增）',
  rulePortfolio: '⑤ 组合层：大盘硬过滤(上证<MA20当日不交易) + 同日上限(≤' + MAX_BUY_PER_DAY + '笔) + 回撤上限(>' + (DD_PAUSE * 100).toFixed(0) + '%暂停次日)',

  top3: top3.map(s => ({ code: s.code, name: s.name, board: s.board, win: s.win })),
  byBoard,
  byWinTier,
  calibration: {
    predMean: +(predMean / 100).toFixed(4),
    realized: +winRate.toFixed(4),
    bias: calibBias,
    perStock: perStockArr
  },
  preFilter: {
    total: preStats.total, pass: preStats.pass,
    skipTrend: preStats.skipTrend, skipVol: preStats.skipVol,
    skipGap: preStats.skipGap, skipMacd: preStats.skipMacd  // ★ 新增 MACD 统计
  },

  portfolio,
  generatedAt: new Date().toISOString().slice(0, 10),
  trades_detail: trades
};

fs.writeFileSync(OUT, JSON.stringify(result, null, 2), 'utf8');


// ========== 输出报告 ==========

console.log('');
console.log('╔══════════════════════════════════════════════════════╗');
console.log('║         中频波段回测（midFreq）— 验证用            ║');
console.log('╠══════════════════════════════════════════════════════╣');
console.log('║  与高频(v1.0.9)差异:                                ║');
console.log('║    主板止损  -2%   →  -3.5%                         ║');
console.log('║    主板止盈  +6%   →  +10%                          ║');
console.log('║    双创K_ATR  1.05  →  1.8                          ║');
console.log('║    主板持仓  ≤10天  →  ≤20天                        ║');
console.log('║    双创持仓  ≤5天   →  ≤12天                        ║');
console.log('║    跟踪封顶   6%    →  10%                          ║');
console.log('║    新增入场   无     →  MACD(12,26)趋势确认(DIF>0)       ║');
console.log('║    跟踪止损   仅双创  →  主板+双创均启用             ║');
console.log('╚══════════════════════════════════════════════════════╝');
console.log('');

console.log('回测周期   :', PERIOD.from, '~', PERIOD.to);
console.log('数据覆盖   :', fmt(dataFrom), '~', fmt(dataTo));
console.log('候选宇宙   :', items.length, '支 | Top3 =', top3.map(s => s.name + '(' + s.win + ')').join(', '));
console.log('候选池     : 全', items.length, '支（全候选池）');
console.log('');

console.log('─── Phase A: 原始信号（前置过滤后） ───');
console.log('原始候选   :', candidates.length, '笔');
console.log('前置过滤漏斗:');
console.log('  总候选     :', preStats.total);
console.log('  趋势未过   :', preStats.skipTrend);
console.log('  量能未过   :', preStats.skipVol);
console.log('  缺口未过   :', preStats.skipGap);
console.log('  MACD非趋势 :', preStats.skipMacd, '  ← ★ 中频新增(DIF<=0)');
console.log('  通过       :', preStats.pass);
console.log('');

console.log('─── ⑤ 组合层风控 ───');
console.log('大盘硬过滤  : 剔除', portfolio.indexFilter.dropped, '笔 | 空头交易日', portfolio.indexFilter.bearishDays, '天');
console.log('同日上限    : ≤', portfolio.perDayCap.max, '笔/日 | 剔除', portfolio.perDayCap.dropped, '笔');
console.log('回撤上限    : 阈值', (portfolio.drawdownPause.threshold * 100).toFixed(0) + '% | 暂停剔除', portfolio.drawdownPause.dropped, '笔');
console.log('阶段流水    : raw', portfolio.stageCounts.raw,
            '→ 过滤', portfolio.stageCounts.afterIndex,
            '→ 限', portfolio.stageCounts.afterCap,
            '→ 最终', portfolio.stageCounts.final);
console.log('');

console.log('─── 核心指标 ───');
console.log('成交交易   :', total, '笔');
console.log('盈利/亏损  :', wins.length, '/', losses.length);
console.log('交易胜率   :', (winRate * 100).toFixed(1) + '%');
console.log('平均盈利   :', (avgWin * 100).toFixed(2) + '%');
console.log('平均亏损   :', (avgLoss * 100).toFixed(2) + '%');
console.log('盈亏比     :', isFinite(profitFactor) ? profitFactor.toFixed(2) : '∞');
console.log('期望值     :', (expectancy * 100).toFixed(3) + '% / 笔');
console.log('平均持有   :', avgHold.toFixed(1), '交易日');
console.log('');

console.log('─── 分市场胜率 ───');
Object.entries(byBoard).forEach(([b, o]) => {
  console.log('  ' + b.padEnd(4), ':', (o.winRate * 100).toFixed(1) + '%', '(' + o.wins + '/' + o.trades + ')');
});

console.log('');
console.log('─── 标定偏差 ───');
console.log('  预测均值   :', predMean.toFixed(1) + '%');
console.log('  实现胜率   :', (winRate * 100).toFixed(1) + '%');
console.log('  偏差       :', (calibBias * 100).toFixed(1) + 'pp', calibBias > 0 ? '(过度乐观)' : '(诚实/偏保守)');
console.log('');

console.log('输出文件    :', OUT, '(', fs.statSync(OUT).size, 'bytes )');
if (skippedNoData.length) console.log('跳过(无K线) :', skippedNoData.join(','));
if (skippedNoAtr.length) console.log('跳过(ATR不足):', skippedNoAtr.join(','));
