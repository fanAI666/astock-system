'use strict';
// chuang/signals.js — 新增：明确的买入/卖出信号 + 持仓比例建议
// 解决原系统缺口：app 仅有 BUY/no-trigger 决策，无 SELL 信号与仓位建议。
// 本模块消费 strategy.generateSignals 的候选 + risk.applyPortfolio 组合过滤，
// 输出结构化 chuang_signals.json：buys（含 entry/sl/tp/positionPct）+ sellRules（显式卖出条件）。
// 与回测共用同一套 G1–G5/E1–E3 逻辑，信号与线上策略一致。

const fs = require('fs');
const { Logger } = require('./logger');
const { CHUANG_CONFIG } = require('./config');
const { generateSignals, loadG5, loadFundStore } = require('./strategy');
const { applyPortfolio, recommendPosition, positionLabel } = require('./risk');
const { summarize } = require('./backtest');

const BOARD_NAME = { cyb: '创业板', kcb: '科创板', kc: '科创板', main: '主板' };
const isDynBoard = (b) => b === 'cyb' || b === 'kcb' || b === 'kc';

// 优先复用已部署的 backtest_chuang.json 最优配置，保证信号与线上策略参数一致；否则用双创典型兜底
function loadBestCfg(config) {
  try {
    const fj = JSON.parse(fs.readFileSync(config.out, 'utf8'));
    if (fj.best) {
      return { kAtrDyn: fj.best.kAtrDyn, boards: fj.best.boards, regime: fj.best.regime,
               maxHoldDyn: fj.best.maxHoldDyn, maxHoldMain: fj.best.maxHoldMain,
               from: config.period.from, to: config.period.to };
    }
  } catch (e) { /* 用兜底 */ }
  return { kAtrDyn: 2.5, boards: 'chuang_only', regime: 'none', maxHoldDyn: 8, maxHoldMain: 20,
           from: config.period.from, to: config.period.to };
}

function buildReasons(trade, cfg, config) {
  const stopPct = (trade.entry - trade.sl) / trade.entry * 100;
  const tgtPct = (trade.tp / trade.entry - 1) * 100;
  const bn = BOARD_NAME[trade.board] || trade.board;
  return [
    `信号日 ${trade.signalDate}（${trade.regime === 'n/a' ? '无市况约束' : trade.regime + ' 市况'}）`,
    `买入板块：${bn}；已通过 G1 流动性 / G2 波动率带 / G3 动量洁净 / G4 相对强度 / G5 盈利质量 + E2 回踩入场 + E1 弹性止盈`,
    `计划止损价 ${trade.sl.toFixed(2)}（-${stopPct.toFixed(1)}%）`,
    `计划目标价 ${trade.tp.toFixed(2)}（+${tgtPct.toFixed(1)}%）`,
    `最长持有 ${cfg.maxHoldDyn} 日，跟踪止损 ${(config.execution.E3_trailPct * 100).toFixed(0)}%`,
  ];
}

// 生成信号文件
// items: 宇宙数组；config: CHUANG_CONFIG；ctx: {index,g5,fund,config}；opts: {cfg, outFile, windowDays}
function generateSignalsFile(items, config, ctx, opts) {
  opts = opts || {};
  const cfg = opts.cfg || loadBestCfg(config);
  const windowDays = opts.windowDays || 60;

  let cands = [];
  items.forEach(s => { cands = cands.concat(generateSignals(s, cfg, ctx)); });
  const port = applyPortfolio(cands, config, ctx.index);
  const trades = port.trades;

  // 近窗口：取最后 windowDays 个交易日的信号
  const dates = [...new Set(trades.map(t => t.signalDate))].sort();
  const windowStart = dates.length > windowDays ? dates[dates.length - windowDays] : (dates[0] || cfg.from);
  const inWindow = trades.filter(t => t.signalDate >= windowStart);

  // 快速 base 统计，供 kelly 仓位参考
  const summary = summarize(trades);

  const buys = inWindow.map(t => {
    const stock = items.find(s => s.code === t.code);
    const name = (stock && stock.name) || t.code;
    const pos = recommendPosition({ entry: t.entry, sl: t.sl }, config, { summary });
    return {
      code: t.code, name, board: t.board, boardName: BOARD_NAME[t.board] || t.board,
      signalDate: t.signalDate, entryDate: t.entryDate, entry: t.entry,
      stopLoss: t.sl, takeProfit: t.tp,
      trailingStopPct: isDynBoard(t.board) ? config.execution.E3_trailPct : config.main.trailPct,
      maxHoldDays: cfg.maxHoldDyn,
      positionPct: +pos.toFixed(4), positionLabel: positionLabel(pos),
      regime: t.regime,
      resolved: { outcome: t.outcome, exit: t.exit, holdDays: t.holdDays },
      reasons: buildReasons(t, cfg, config),
    };
  }).sort((a, b) => a.signalDate < b.signalDate ? 1 : -1);

  const last5 = dates.length ? dates[dates.length - 5] : cfg.from;
  const newAlerts = buys.filter(b => b.signalDate >= last5).length;

  const out = {
    generatedAt: new Date().toISOString().slice(0, 10),
    config: { kAtrDyn: cfg.kAtrDyn, maxHoldDyn: cfg.maxHoldDyn, regime: cfg.regime, boards: cfg.boards, period: config.period },
    method: 'chuang-strategy-refactor',
    summary: { total: summary.total, winRate: +summary.winRate.toFixed(4),
               expectancy: +(summary.expectancy * 100).toFixed(3), profitFactor: summary.profitFactor, kelly: +summary.kelly.toFixed(3) },
    sellRules: {
      stopLoss: '跌破入场价下方 K_ATR×ATR14 止损位即卖出（双创动态止损）',
      takeProfit: '触及 E1 弹性止盈 max(2.0×SL, 1.8×ATR14) 即卖出',
      trailingStop: '持仓创新高后，从高点回撤 2%（双创）/ 3%（主板）触发跟踪止损卖出',
      maxHold: `持有满 ${cfg.maxHoldDyn} 日强制平仓（周期结束）`,
    },
    buys,
    stats: { total: trades.length, inWindow: buys.length, newAlerts },
  };
  if (opts.outFile) {
    fs.writeFileSync(opts.outFile, JSON.stringify(out, null, 2), 'utf8');
    Logger.info('SIG', `写入信号文件 ${opts.outFile}（窗口内 ${buys.length} 条，新警报 ${newAlerts}）`);
  }
  return out;
}

module.exports = { generateSignalsFile, loadBestCfg, buildReasons, BOARD_NAME };
