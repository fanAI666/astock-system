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
           skipG1: 0, skipG2: 0, skipG3: 0, skipG4: 0, skipG5: 0, skipE2: 0, skipSwitch: 0,
           skipTls: 0, skipTsq: 0, skipPbes: 0 };
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

// ===== 共享退出/持有模拟（供 tracks.js 的 5.1–5.6 观察轨道复用；与 generateSignals 内联退出逻辑数学一致）=====
// 入参：entry=次日开盘入场价；i=信号bar索引；bars=K线；maxHold；K_ATR；exec；main；isDyn；ind
// 返回 { outcome, exitPrice, holdDays, sl, tp, entry, ret }（ret 为收益率）；ATR 缺失返回 null
function simulateTrade(entry, i, bars, maxHold, K_ATR, exec, main, isDyn, ind) {
  const a = isDyn ? atrAt(ind, i) : null;
  if (isDyn && a == null) return null;
  const slDist = isDyn ? K_ATR * a : entry * main.stop;
  const sl = isDyn ? entry - slDist : entry * (1 - main.stop);
  const tp = isDyn ? entry + Math.max(exec.E1_tpR * slDist, exec.E1_tpAtr * a) : entry * (1 + main.profit);
  const trailPct = (isDyn && exec.enabled) ? exec.E3_trailPct : main.trailPct;
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
  return { outcome, exitPrice, holdDays, sl, tp, entry, ret: (exitPrice - entry) / entry };
}

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

// ===== 否决层（TSQ / PBES，圆桌新增；仅双创；默认关，CHUANG_VETO=1 开启）=====
// 定位：挂在 G1–G5 + 大盘开关 + E 层之后做尾部剔除（不替代动量，只砍最烂样本）。
// 返回 true=通过；'tsq'/'pbes'=对应否决（主循环据此区分计数并 continue）。
function screenVeto(stock, ind, i, ctx, config) {
  const v = config.veto;
  if (!v || !v.enabled) return true;
  const code = stock.code, board = stock.board;
  if (!['cyb', 'kcb', 'kc'].includes(board)) return true;  // 仅双创

  // --- TSQ：换手突增 / 连板高潮 排除 ---
  if (v.tsq && v.tsq.enabled) {
    const vr = ind.volRatio[i];
    let H = 0;
    for (let k = i; k >= 1; k--) { if (ind.isLimitUp[k]) H++; else break; }  // 连板计数（含当日）
    if ((vr != null && vr > v.tsq.volRatioMax) || H >= v.tsq.limitUpStreakMax) return 'tsq';
  }

  // --- PBES：贵且无增长 一票否决（价格分位代理 PE 分位）---
  if (v.pbes && v.pbes.enabled) {
    const pp = ind.pricePct[i];
    const fund = ctx.fund && ctx.fund[code];
    const npTtm = fund && fund.npTtm;
    const epsSlope = fund && fund.npGrowth;
    // 科创板 npTtm≤0（亏损）：EPS 斜率无法定义 → 不否决（保守放行）
    if (npTtm != null && npTtm > 0 && epsSlope != null && pp != null &&
        pp > v.pbes.pePctMax && epsSlope <= v.pbes.epsSlopeMax) return 'pbes';
  }

  return true;
}
// 入参：
//   stock  = {code,name,board,kline:{day:[...]}}
//   cfg    = 网格单配置 {kAtrDyn,maxHoldDyn,maxHoldMain,boards,regime,from,to}
//   ctx    = { index: data.loadIndex 结果, g5: loadG5 结果, fund: loadFundStore 结果, config: CHUANG_CONFIG }
function generateSignals(stock, cfg, ctx) {
  const config = ctx.config;
  const ind = precompute(stock, { pbesLookback: (config.veto && config.veto.pbes && config.veto.pbes.pePctLookback) || 250 });
  const bars = ind.bars;
  if (bars.length < 2) return [];
  const board = stock.board;
  if (cfg.boards === 'main_only' && board !== 'main') return [];
  if (cfg.boards === 'no_kcb' && board === 'kcb') return [];
  if (cfg.boards === 'chuang_only' && !['cyb', 'kcb', 'kc'].includes(board)) return [];
  const isDyn = (board === 'cyb' || board === 'kcb' || board === 'kc');

  const gates = config.gates, exec = config.execution, main = config.main;
  const index = ctx.index;

  // G5 盈利质量（股票级，4.0 边车）：仅当显式不达标(g5Quality===false，含在边车内但非 true)才剔除整只；无数据放行
  if (isDyn && gates.enabled && gates.G5_earningsQuality && ctx.g5[stock.code] === false) { preStats.skipG5++; return []; }

  const tol = isDyn ? exec.tol : main.tol;
  const K_ATR = isDyn ? cfg.kAtrDyn : main.kAtr;
  const maxHold = isDyn ? cfg.maxHoldDyn : cfg.maxHoldMain;

  const { rKind, rMode } = resolveRegime(cfg);
  const out = [];

  // 区间边界归一化：bars 日期为 'YYYY-MM-DD'，而 cfg.from/to 历史上为紧凑 'YYYYMMDD'。
  // 直接字符串比较会因第 5 位 '-'(45) < '0'(48) 恒判 dateD < 紧凑串 →
  //   to 永不生效（区间右端形同虚设），from 误砍掉同年数据。此处统一去横线后比较。
  const fromKey = String(cfg.from || '').replace(/-/g, '');
  const toKey = String(cfg.to || '').replace(/-/g, '');

  for (let i = 0; i < bars.length - 1; i++) {
    const d = bars[i], nd = bars[i + 1];
    const dateD = d[0];
    const dKey = dateD.replace(/-/g, '');
    if ((fromKey && dKey < fromKey) || (toKey && dKey > toKey)) continue;
    if (rKind) {
      const r = index.regimeOf(dateD, rKind);
      if (rMode === 'bull' && r !== 'bull') continue;
      if (rMode === 'notbear' && r === 'bear') continue;
    }
    // ===== TLS 板块内龙头主筛（圆桌路线 B；仅双创；默认关，CHUANG_TLS=1 开启）=====
    // 主筛（最外层过滤）：先把候选池压到「当周主线板块内龙头前N」，再走后续 gates/veto；
    // 解决 G3 与 PBES 互斥导致的否决层冗余——让 TSQ/PBES 在龙头样本上真正生效。
    if (isDyn && config.tls && config.tls.enabled) {
      const set = ctx.tlsPass && ctx.tlsPass.get(dateD);
      if (!set || !set.has(stock.code)) { preStats.skipTls++; continue; }
    }
    // ===== 大盘开关（DRFR，圆桌新增；仅双创）=====
    // 始终打标 open/closed（验证态 bySwitch 用）；enabled 时过滤 closed（部署态）。
    let swState = 'na';
    if (isDyn && ctx.switchIndex) {
      swState = ctx.switchIndex.switchOf(dateD);
      if (config.marketSwitch.enabled && swState !== 'open') { preStats.skipSwitch++; continue; }
    }
    preStats.total++;
    const f = screenPreFilter(ind, i, config);
    // 5.0 反手：深跌坑票在 MA20 下方，正常 trendOk（close>ma20&ma5>ma20）会误剔 → 反手态放松 trendOk
    const trendOk = config.invert ? true : f.trendOk;
    if (!trendOk) { preStats.skipTrend++; continue; }
    if (!f.volOk) { preStats.skipVol++; continue; }
    if (!f.gapOk) { preStats.skipGap++; continue; }
    preStats.pass++;

    // ===== 双创 G1–G4 逐日选股门（仅双创；主板在上方 board 过滤已 return，不经过此处）=====
    if (isDyn && gates.enabled) {
      // G2 波动率带：ATR14% ∈ [3%,6%]
      const a0 = atrAt(ind, i); const atrPct = a0 != null ? a0 / d[2] : null;
      if (atrPct == null || atrPct < gates.G2_atrMin || atrPct > gates.G2_atrMax) { preStats.skipG2++; continue; }
      // G3 动量洁净度：站上 MA20 且 距MA20 ∈ [0,+12%]，且 RSI(14) ∈ [40,65]
      //   5.0 反手：镜像为 距MA20 ∈ [-35%,0]（深跌坑），RSI 放宽至 [20,70]
      const ma20g = ind.ma20[i]; const rrsi = rsiAt(ind, i);
      if (ma20g == null || rrsi == null) { preStats.skipG3++; continue; }
      const ext = (d[2] - ma20g) / ma20g;
      if (config.invert) {
        if (ext > 0 || ext < gates.G3_ma20ExtMinInvert || rrsi < 20 || rrsi > 70) { preStats.skipG3++; continue; }
      } else {
        if (ext < 0 || ext > gates.G3_ma20ExtMax || rrsi < gates.G3_rsiLo || rrsi > gates.G3_rsiHi) { preStats.skipG3++; continue; }
      }
      // G1 流动性：近20日日均成交额 ≥ 1亿元
      const t20 = ind.turnover20[i];
      if (t20 == null || t20 < gates.G1_liquidityFloor) { preStats.skipG1++; continue; }
      // G4 相对强度：个股近20日收益 > 上证同期收益
      //   5.0 反手：镜像为 个股20日收益 < 上证同期（深跌/跑输 → 反向介入）
      const sr = i >= 20 ? d[2] / bars[i - 20][2] - 1 : null;
      const ip = index.idxPos[dateD];
      const ir = (ip != null && ip >= 20) ? index.idxClose[index.idxDates[ip]] / index.idxClose[index.idxDates[ip - 20]] - 1 : null;
      if (config.invert) {
        if (sr == null || ir == null || sr >= ir) { preStats.skipG4++; continue; }
      } else {
        if (sr == null || ir == null || sr <= ir) { preStats.skipG4++; continue; }
      }
    }

    // 新增可配置指标层（默认全关；仅双创；不影响 parity）
    if (isDyn && !screenExtra(stock, ind, i, ctx, config)) continue;

    // ===== 否决层（TSQ / PBES，圆桌新增；仅双创；默认关，CHUANG_VETO=1 开启）=====
    // 尾部剔除：先通过所有 G 门 + E 门，再用 TSQ/PBES 砍最烂样本
    if (isDyn) {
      const vres = screenVeto(stock, ind, i, ctx, config);
      if (vres === 'tsq') { preStats.skipTsq++; continue; }
      if (vres === 'pbes') { preStats.skipPbes++; continue; }
    }

    const baseline = d[2], nextOpen = nd[1];
    if (!baseline || !nextOpen) continue;
    const dev = (nextOpen - baseline) / baseline;
    if (Math.abs(dev) > tol) continue;

    // E2 回踩 MA20 不破才入场（仅双创，4.2）：信号bar低点回踩至 MA20±3% 内且收在 MA20 上，过滤追高
    //   5.0 反手：深跌坑票在 MA20 下方，E2 回踩门会误剔 → 反手态跳过 E2
    if (isDyn && exec.enabled && !config.invert) {
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
               sl, tp, outcome, ret, holdDays, regime: rTrade, switch: swState, year: dateD.slice(0, 4) });
  }
  return out;
}

module.exports = {
  generateSignals, resetPreStats, getPreStats, loadG5, loadFundStore,
  resolveRegime, screenExtra, newPreStats, atrAt, rsiAt, simulateTrade,
};
