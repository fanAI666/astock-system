'use strict';
// chuang/indicators.js — 技术指标（纯函数 + 向量化预计算）
// 关键约束：所有公式与旧 backtest_chuang.js 的 per-bar 调用（rsi14/atr14/sma/passPreFilter）
// 数学等价，确保重构后回测数值 parity。新增 MACD/EMA 供 extraFilters 与 signals 使用。
// K线格式：bar = [日期, 开, 收, 高, 低, 量]  →  索引 1=开 2=收 3=高 4=低 5=量

const ATR_WIN = 14;

// 注意：以下序列函数刻意采用与旧 backtest_chuang.js 逐 bar 公式【完全一致的朴素求和】，
// 牺牲约 20x 微优化，换取 bit-exact 数值 parity（浮点求和顺序差异会在大样本下累积成可见偏差）。
function smaSeries(bars, win, field) {
  const n = bars.length, out = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    if (i < win - 1) continue;
    let s = 0;
    for (let k = i - win + 1; k <= i; k++) s += bars[k][field];
    out[i] = s / win;
  }
  return out;
}

function atrSeries(bars) {
  const n = bars.length, out = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    if (i < ATR_WIN) continue;
    let s = 0;
    for (let k = i - ATR_WIN + 1; k <= i; k++) {
      const c0 = bars[k - 1][2], h = bars[k][3], l = bars[k][4];
      s += Math.max(h - l, Math.abs(h - c0), Math.abs(l - c0));
    }
    out[i] = s / ATR_WIN;
  }
  return out;
}

function rsiSeries(bars) {
  const n = bars.length, out = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    if (i < ATR_WIN) continue; // 旧 rsi14：idx < ATR_WIN(14) 返回 null
    let g = 0, l = 0;
    for (let k = i - ATR_WIN + 1; k <= i; k++) {
      const ch = bars[k][2] - bars[k - 1][2];
      if (ch > 0) g += ch; else l -= ch;
    }
    if (l === 0) { out[i] = 100; continue; }
    const rs = g / l; out[i] = 100 - 100 / (1 + rs);
  }
  return out;
}

function emaSeries(bars, win, field) {
  const n = bars.length, out = new Array(n).fill(null);
  if (n === 0) return out;
  const k = 2 / (win + 1);
  let prev = bars[0][field];
  out[0] = prev;
  for (let i = 1; i < n; i++) {
    prev = bars[i][field] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

// MACD(12,26,9)：macd=ema12-ema26；signal=ema9(macd)；hist=macd-signal
function macdSeries(bars) {
  const close = bars.map(b => b[2]);
  const ema12 = emaSeries(bars, 12, 2);
  const ema26 = emaSeries(bars, 26, 2);
  const n = bars.length;
  const macd = new Array(n).fill(null);
  for (let i = 0; i < n; i++) macd[i] = (ema12[i] != null && ema26[i] != null) ? ema12[i] - ema26[i] : null;
  // signal = EMA9 of macd（用 macd 数组构造伪 bars）
  const sigBars = macd.map((m, i) => [bars[i][0], m == null ? 0 : m, m == null ? 0 : m, m == null ? 0 : m, m == null ? 0 : m, 0]);
  const sig = emaSeries(sigBars, 9, 2);
  const hist = new Array(n).fill(null);
  for (let i = 0; i < n; i++) hist[i] = (macd[i] != null && sig[i] != null) ? macd[i] - sig[i] : null;
  return { macd, signal: sig, hist };
}

function volMaSeries(bars, win) { return smaSeries(bars, win, 5); }

// 近20日日均成交额(元) = mean(vol[手]×100×close)
function turnover20Series(bars) {
  const n = bars.length, out = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    if (i < 19) continue;
    let s = 0;
    for (let k = i - 19; k <= i; k++) s += bars[k][5] * 100 * bars[k][2];
    out[i] = s / 20;
  }
  return out;
}

// TSQ 因子序列：成交量比 = vol[i] / median(vol[i-19..i])（代理换手突增；kline 无换手率字段）
function volRatioSeries(bars) {
  const n = bars.length, out = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    if (i < 19) continue;
    const arr = new Array(21);
    for (let k = i - 19; k <= i; k++) arr[k - (i - 19)] = bars[k][5];
    arr.sort((a, b) => a - b);
    const med = arr[10];
    out[i] = med > 0 ? bars[i][5] / med : null;
  }
  return out;
}

// PBES 因子序列（代理）：价格在区间 [i-lookback+1, i] 的归一化位置 = (close[i]-low)/(high-low)
//   近似"自身 PE 分位"（EPS 短期稳定假设下 PE 位置≈价格位置；成长股有偏差，作否决层语义足够）
function pricePctSeries(bars, lookback) {
  const n = bars.length, out = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    if (i < lookback - 1) continue;
    let lo = Infinity, hi = -Infinity;
    for (let k = i - lookback + 1; k <= i; k++) { const c = bars[k][2]; if (c < lo) lo = c; if (c > hi) hi = c; }
    out[i] = hi > lo ? (bars[i][2] - lo) / (hi - lo) : 0.5;
  }
  return out;
}

// TSQ 涨停标记：双创 20cm，r=(close-prevClose)/prevClose ≥ 0.195 视为涨停（留 0.5% 容差）
//   用于连板计数 H（从当前 i 往前数连续涨停天数）
function isLimitUpSeries(bars) {
  const n = bars.length, out = new Array(n).fill(false);
  for (let i = 1; i < n; i++) {
    const prevClose = bars[i - 1][2];
    if (prevClose > 0) { const r = (bars[i][2] - prevClose) / prevClose; out[i] = r >= 0.195; }
  }
  return out;
}

// 一次性预计算某股票全部指标序列（O(bars)，替代 genSignals 内层重复计算 → 效率提升）
// opts.pbesLookback：PBES 价格分位滚动窗口（日）
function precompute(stock, opts) {
  const bars = (stock.kline && stock.kline.day) || [];
  const ma5 = smaSeries(bars, 5, 2);
  const ma20 = smaSeries(bars, 20, 2);
  const atr = atrSeries(bars);
  const rsi = rsiSeries(bars);
  const volMa20 = volMaSeries(bars, 20);
  const turnover20 = turnover20Series(bars);
  const volRatio = volRatioSeries(bars);
  const pricePct = pricePctSeries(bars, (opts && opts.pbesLookback) || 250);
  const isLimitUp = isLimitUpSeries(bars);
  const { macd, signal: macdSig, hist: macdHist } = macdSeries(bars);
  return { bars, ma5, ma20, atr, rsi, volMa20, turnover20, volRatio, pricePct, isLimitUp, macd, macdSig, macdHist };
}

// 预过滤（trend/vol/gap），与旧 passPreFilter 逐字等价
// 返回 {trendOk, volOk, gapOk}
function screenPreFilter(ind, i, config) {
  const bars = ind.bars;
  const pf = config.preFilter;
  const close = bars[i][2], open = bars[i][1], vol = bars[i][5];
  const prevClose = i > 0 ? bars[i - 1][2] : close;
  const gap = (open - prevClose) / prevClose;
  const gapOk = gap >= -pf.gapDown && gap <= pf.gapUp;
  const ma5 = ind.ma5[i], ma20 = ind.ma20[i];
  const ma20Prev = i > 0 ? ind.ma20[i - 1] : null;
  const ma20Vol = ind.volMa20[i];
  let trendOk = false;
  if (ma20 != null && ma5 != null) {
    const rising = ma20Prev != null ? (ma20 > ma20Prev) : true;
    trendOk = (close > ma20) && (ma5 > ma20) && rising;
  }
  let volOk = (ma20Vol != null && ma20Vol > 0) ? vol >= ma20Vol * pf.volMult : false;
  return { trendOk, volOk, gapOk };
}

module.exports = {
  ATR_WIN,
  smaSeries, atrSeries, rsiSeries, emaSeries, macdSeries, volMaSeries, turnover20Series,
  volRatioSeries, pricePctSeries, isLimitUpSeries,
  precompute, screenPreFilter,
};
