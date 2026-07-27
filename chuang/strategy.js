'use strict';
// chuang/strategy.js — 信号生成（逐字移植 backtest_chuang.js 的 genSignals + 预过滤上下文）
// 设计目标：
//   ① 完全复刻旧 genSignals 的 board 门控 / G1–G5 / E1–E3 / 预过滤 / 退出循环 —— 保证回测数值 parity；
//   ② 用 indicators.precompute 的向量化序列替代内层 per-bar 重算（G2/G3/G1/ATR 边界已对齐旧 null 规则）；
//   ③ 主板任何路径都不改（STOP_MAIN/PROFIT_MAIN/3:1/trail 0.03 等沿用 config.main）；
//   ④ 新增 extraFilters（PE/PB/营收增长/MACD）默认全关，仅双创生效，不影响 parity。
// K线格式：bar = [日期, 开, 收, 高, 低, 量]  →  索引 1=开 2=收 3=高 4=低 5=量

const fs = require('fs');
const { precompute, screenPreFilter, ATR_WIN } = require('./indicators');

// ===== preStats（与旧 backtest_chuang.js 逐字段等价；回测前由 backtest.js 调 resetPreStats 清零）=====
function newPreStats() {
  return { total: 0, pass: 0, skipTrend: 0, skipVol: 0, skipGap: 0, skipAtr: 0,
           skipG1: 0, skipG2: 0, skipG3: 0, skipG4: 0, skipG5: 0, skipE2: 0 };
}
let preStats = newPreStats();
function resetPreStats() { preStats = newPreStats(); }
function getPreStats() { return preStats; }

// ===== G5 边车 reject 映射（与旧 G5[c]=g5Quality===true 完全等价）=====
// 旧逻辑：G5[c] = (g5Quality === true)；剔除条件是 G5[code] === false。
// 关键微妙点：仅当 code 出现在边车且 g5Quality 非 true 时才为 false 被剔；
//   code 不在边车 → G5[code]=undefined → undefined===false 为 false → 放行（防陈旧/缺数据误杀）。
function loadG5(fundFile) {
  const g5 = {};
  try {
    const fj = JSON.parse(fs.readFileSync(fundFile, 'utf8'));
    Object.entries(fj.items || {}).forEach(([c, f]) => { g5[c] = f.g5Quality === true; });
  } catch (e) { /* 边车缺失：全部放行 */ }
  return g5;
}
// 完整基本面边车（供 extraFilters 的 PE/PB/营收增长/净利增长；默认关闭，不影响 parity）
function loadFundStore(fundFile) {
  try { const fj = JSON.parse(fs.readFileSync(fundFile, 'utf8')); return fj.items || {}; } catch (e) { return {}; }
}

// ===== atr/rsi 边界守卫：旧 atr14/rsi14 在 idx<ATR_WIN(14) 返回 null，而 indicators 预计算在 i>=13 给值，需对齐 =====
function atrAt(ind, i) { return i < ATR_WIN ? null : ind.atr[i]; }
function rsiAt(ind, i) { return i < ATR_WIN ? null : ind.rsi[i]; }

// ===== regime 解析（与旧 genSignals 的 rKind/rMode 映射逐字等价）=====
function resolveRegime(cfg) {
  const regime = cfg.regime;
  if (regime === 'none') return { rKind: null, rMode: null };
  if (regime === 'bull_only') return { rKind: 'ma60', rMode: 'bull' };
  if (regime === 'ma20_up') return { rKind: 'ma20', rMode: 'bull' };
  if (regime === 'basket') return { rKind: 'basket', rMode: 'bull' };
  if (regime === 'not_bear') return { rKind: 'ma60', rMode: 'notbear' };
  if (regime === 'basket_not_bear') return { rKind: 'basket', rMode: 'notbear' };
  return { rKind: 'ma60', rMode: 'bull' }; // 默认
}

// ===== 新增可配置指标层（默认全关；仅双创；返回 true=通过）=====
function screenExtra(stock, ind, i, ctx, config) {
  const ef = config.extraFilters;
  const anyOn = ef.pe.enabled || ef.pb.enabled || ef.revGrowth.enabled || ef.npGrowth.enabled || ef.macd.enabled;
  if (!anyOn) return true;
  const fund = ctx.fund && ctx.fund[stock.code];
  if (ef.pe.enabled) {
    const v = fund && fund.pe; if (v == null || v < ef.pe.min || v > ef.pe.max) return false;
  }
  if (ef.pb.enabled) {
    const v = fund && fund.pb; if (v == null || v < ef.pb.min || v > ef.pb.max) return false;
  }
  if (ef.revGrowth.enabled) {
    const v = fund && fund.revGrowth; if (v == null || v < ef.revGrowth.min) return false;
  }
  if (ef.npGrowth.enabled) {
    const v = fund && fund.npGrowth; if (v == null || v < ef.npGrowth.min) return false;
  }
  if (ef.macd.enabled) {
    const hist = ind.macdHist, m = hist[i], mp = i > 0 ? hist[i - 1] : null;
    if (ef.macd.goldenCross) {
      // 金叉：MACD 柱由负（或零）转正的当根
      if (!(mp != null && mp <= 0 && m != null && m > 0)) return false;
    } else {
      // 零轴上方
      if (m == null || m <= 0) return false;
    }
  }
  return true;
}

// ===== 核心：信号生成（=旧 genSignals）=====
// 入参：
//   stock  = {code,name,board,kline:{day:[...]}}
//   cfg    = 网格单配置 {kAtrDyn,maxHoldDyn,maxHoldMain,boards,regime,from,to}
//   ctx    = { index: data.loadIndex 结果, g5: loadG5 结果, fund: loadFundStore 结果, config: CHUANG_CONFIG }
function generateSignals(stock, cfg, ctx) {
  const ind = precompute(stock);
  const bars = ind.bars;
  if (bars.length < 2) return [];
  const board = stock.board;
  if (cfg.boards === 'main_only' && board !== 'main') return [];
  if (cfg.boards === 'no_kcb' && board === 'kcb') return [];
  if (cfg.boards === 'chuang_only' && !['cyb', 'kcb', 'kc'].includes(board)) return [];
  const isDyn = (board === 'cyb' || board === 'kcb' || board === 'kc');

  const config = ctx.config;
  const gates = config.gates, exec = config.execution, main = config.main;
  const index = ctx.index;

  // G5 盈利质量（股票级，4.0 边车）：仅当显式不达标(g5Quality===false，含在边车内但非 true)才剔除整只；无数据放行
  if (isDyn && gates.enabled && gates.G5_earningsQuality && ctx.g5[stock.code] === false) { preStats.skipG5++; return []; }

  const tol = isDyn ? exec.tol : main.tol;
  const K_ATR = isDyn ? cfg.kAtrDyn : main.kAtr;
  const maxHold = isDyn ? cfg.maxHoldDyn : cfg.maxHoldMain;

  const { rKind, rMode } = resolveRegime(cfg);
  const out = [];

  for (let i = 0; i < bars.length - 1; i++) {
    const d = bars[i], nd = bars[i + 1];
    const dateD = d[0];
    if (dateD < cfg.from || dateD > cfg.to) continue;
    if (rKind) {
      const r = index.regimeOf(dateD, rKind);
      if (rMode === 'bull' && r !== 'bull') continue;
      if (rMode === 'notbear' && r === 'bear') continue;
    }
    preStats.total++;
    const f = screenPreFilter(ind, i, config);
    if (!f.trendOk) { preStats.skipTrend++; continue; }
    if (!f.volOk) { preStats.skipVol++; continue; }
    if (!f.gapOk) { preStats.skipGap++; continue; }
    preStats.pass++;

    // ===== 双创 G1–G4 逐日选股门（仅双创；主板在上方 board 过滤已 return，不经过此处）=====
    if (isDyn && gates.enabled) {
      // G2 波动率带：ATR14% ∈ [3%,6%]
      const a0 = atrAt(ind, i); const atrPct = a0 != null ? a0 / d[2] : null;
      if (atrPct == null || atrPct < gates.G2_atrMin || atrPct > gates.G2_atrMax) { preStats.skipG2++; continue; }
      // G3 动量洁净度：站上 MA20 且 距MA20 ∈ [0,+12%]，且 RSI(14) ∈ [40,65]
      const ma20g = ind.ma20[i]; const rrsi = rsiAt(ind, i);
      if (ma20g == null || rrsi == null) { preStats.skipG3++; continue; }
      const ext = (d[2] - ma20g) / ma20g;
      if (ext < 0 || ext > gates.G3_ma20ExtMax || rrsi < gates.G3_rsiLo || rrsi > gates.G3_rsiHi) { preStats.skipG3++; continue; }
      // G1 流动性：近20日日均成交额 ≥ 1亿元
      const t20 = ind.turnover20[i];
      if (t20 == null || t20 < gates.G1_liquidityFloor) { preStats.skipG1++; continue; }
      // G4 相对强度：个股近20日收益 > 上证同期收益
      const sr = i >= 20 ? d[2] / bars[i - 20][2] - 1 : null;
      const ip = index.idxPos[dateD];
      const ir = (ip != null && ip >= 20) ? index.idxClose[index.idxDates[ip]] / index.idxClose[index.idxDates[ip - 20]] - 1 : null;
      if (sr == null || ir == null || sr <= ir) { preStats.skipG4++; continue; }
    }

    // 新增可配置指标层（默认全关；仅双创；不影响 parity）
    if (isDyn && !screenExtra(stock, ind, i, ctx, config)) continue;

    const baseline = d[2], nextOpen = nd[1];
    if (!baseline || !nextOpen) continue;
    const dev = (nextOpen - baseline) / baseline;
    if (Math.abs(dev) > tol) continue;

    // E2 回踩 MA20 不破才入场（仅双创，4.2）：信号bar低点回踩至 MA20±3% 内且收在 MA20 上，过滤追高
    if (isDyn && exec.enabled) {
      const ma20e = ind.ma20[i]; const lowI = bars[i][4];
      if (ma20e == null || lowI > ma20e * (1 + exec.E2_pullbackTol) || d[2] < ma20e) { preStats.skipE2++; continue; }
    }

    const entry = nextOpen;
    let sl, tp, slDist;
    if (isDyn) {
      const a = atrAt(ind, i); if (a == null) { preStats.skipAtr++; continue; }
      slDist = K_ATR * a; sl = entry - slDist;
      // E1 弹性止盈（4.2）：TP = max(2.0×SL, 1.8×ATR14)，替代固定 3:1；主板仍走下方固定 2%/6%
      tp = exec.enabled ? entry + Math.max(exec.E1_tpR * slDist, exec.E1_tpAtr * a) : entry + 3 * slDist;
    } else {
      slDist = entry * main.stop; sl = entry * (1 - main.stop); tp = entry * (1 + main.profit);
    }
    const trailPct = (isDyn && exec.enabled) ? exec.E3_trailPct : main.trailPct;   // E3 跟踪止损 3%→2%（仅双创）
    const trailCap = entry * (1 + main.trailCap);
    let curSL = sl, outcome = null, exitPrice = entry, holdDays = 0;
    for (let j = i + 1; j < bars.length && j <= i + maxHold; j++) {
      const h = bars[j][3], l = bars[j][4]; holdDays++;
      if (l <= curSL) { outcome = 'loss'; exitPrice = curSL; break; }
      if (h >= tp) { outcome = 'win'; exitPrice = tp; break; }
      if (isDyn) { const nsl = Math.min(trailCap, Math.max(curSL, h * (1 - trailPct))); if (nsl > curSL) curSL = nsl; }
    }
    if (!outcome) {
      const jlast = Math.min(bars.length - 1, i + maxHold);
      exitPrice = bars[jlast][2];
      outcome = exitPrice >= entry ? 'win' : 'loss'; holdDays = jlast - i;
    }
    const ret = (exitPrice - entry) / entry;
    const rTrade = rKind ? index.regimeOf(dateD, rKind) : 'n/a';
    out.push({ code: stock.code, board, signalDate: dateD, entryDate: nd[0], entry, exit: exitPrice,
               sl, tp, outcome, ret, holdDays, regime: rTrade, year: dateD.slice(0, 4) });
  }
  return out;
}

module.exports = {
  generateSignals, resetPreStats, getPreStats, loadG5, loadFundStore,
  resolveRegime, screenExtra, newPreStats, atrAt, rsiAt,
};
