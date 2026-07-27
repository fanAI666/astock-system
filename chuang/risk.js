'use strict';
// chuang/risk.js — 组合层风控 + 持仓比例建议
// ① applyPortfolio：逐字移植旧 backtest_chuang.js 的 applyPortfolio（指数硬过滤 / 每日买入上限 / 回撤暂停）。
//   保证重构后组合层 equity 曲线与旧版一致（parity）。
// ② recommendPosition：新增持仓比例建议（kelly_atr / fixed / vol_parity），封顶 maxPosition；
//   这是原系统缺失的能力（原 app 只有 BUY/no-trigger，无明确仓位建议），属增量。

// ===== ① 组合层风控（与旧 applyPortfolio 逐字段等价）=====
// cands: generateSignals 产出的候选信号数组
// config: CHUANG_CONFIG（取 portfolio.maxBuyPerDay / ddPause）
// index: data.loadIndex 结果（取 idxMA / idxClose）
function applyPortfolio(cands, config, index) {
  const idxMA = index.idxMA, idxClose = index.idxClose;
  const MAX_BUY_PER_DAY = config.portfolio.maxBuyPerDay;
  const DD_PAUSE = config.portfolio.ddPause;

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

// ===== ② 持仓比例建议（增量能力）=====
// 入参 trade: { entry, sl, board, atrPct?, ... }（signals.js 生成的信号，携带 entry/sl）
//      ctx: { summary? }  summary 为回测 base 统计（含 kelly/winRate/payoff），供 kelly_atr 方法参考
// 返回 0~1 的仓位比例（单标的占总资金比例），已封顶 maxPosition、下限 1%。
function clampPos(p, config) {
  const max = config.position.maxPosition;
  if (!isFinite(p) || p <= 0) return 0;
  return Math.min(max, Math.max(0.01, p));
}

function recommendPosition(trade, config, ctx) {
  const pos = config.position;
  const method = pos.method;
  const entry = trade.entry, sl = trade.sl;
  const stopPct = (entry != null && sl != null && entry > 0) ? (entry - sl) / entry : null;

  if (method === 'fixed') {
    return clampPos(pos.base, config);
  }

  if (method === 'vol_parity') {
    // 波动率平价：波动越高仓位越低；参考波动 refVol=4%
    const refVol = 0.04;
    const vol = (trade.atrPct != null && trade.atrPct > 0) ? trade.atrPct : stopPct;
    if (vol == null) return clampPos(pos.base, config);
    return clampPos(pos.base * (refVol / vol), config);
  }

  // 默认 kelly_atr：风险预算(ATR 止损) 与 Kelly 上限 取小，再封顶 maxPosition
  const riskPos = (stopPct != null && stopPct > 0) ? pos.atrRiskPct / stopPct : pos.base;
  const summary = ctx && ctx.summary;
  const kellyFull = (summary && isFinite(summary.kelly)) ? summary.kelly : 0;
  const kellyPos = kellyFull > 0 ? pos.kellyFraction * kellyFull : 0;
  const finalPos = kellyPos > 0 ? Math.min(riskPos, kellyPos) : riskPos;
  return clampPos(finalPos, config);
}

// 仓位档位标签（便于 app 展示）
function positionLabel(pct) {
  if (pct >= 0.15) return '重仓';
  if (pct >= 0.10) return '标准';
  if (pct >= 0.05) return '轻仓';
  if (pct > 0) return '试探';
  return '不建仓';
}

module.exports = { applyPortfolio, recommendPosition, positionLabel, clampPos };
