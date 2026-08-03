'use strict';
// chuang/config.js — 双创选股策略 · 全参数配置中心
// 目标：把原先散落在 backtest_chuang.js 顶部的硬编码常量 + env 开关，集中为单一可配置对象。
// 兼容旧 env：BT_SRC / BT_OUT / BT_FUND / BT_GRID / BT_BASKET / BT_K / BT_H / BT_R /
//             CHUANG_GATES / CHUANG_EXEC / FUND_SRC / FUND_OUT / FUND_CODES / FUND_SKIP_G6。
// 新增指标层（PE/PB/营收增长/MACD）默认全部关闭 —— 保证重构后回测行为与旧版严格一致（parity）。

const env = process.env;

function boolEnv(name, def) {
  const v = env[name];
  if (v === undefined || v === '') return def;
  return v !== '0' && v !== 'false' && v !== 'no';
}
function numEnv(name, def) {
  const v = env[name];
  if (v === undefined || v === '') return def;
  const n = +v;
  return isFinite(n) ? n : def;
}

const CHUANG_CONFIG = {
  // ===== 数据源（与旧 BT_* env 兼容）=====
  src: env.BT_SRC || 'D:/WorkBuddy/选股结果/import_final.json',
  out: env.BT_OUT || 'D:/WorkBuddy/选股结果/backtest_chuang.json',
  fundFile: env.BT_FUND || 'D:/WorkBuddy/选股结果/fundamental.json',
  indexFile: 'D:/WorkBuddy/选股结果/index_sh.json',

  // ===== 回测区间 =====
  period: { from: '20230828', to: '20260630' },

  // ===== 板块门控：主板完全不动；仅 chuang_only 走 G/E 体系 =====
  boards: 'chuang_only',
  chuangBoards: ['cyb', 'kcb', 'kc'],

  // ===== 主板固定参数（重构后保持原样，任何路径都不改主板）=====
  main: { stop: 0.02, profit: 0.06, kAtr: 1.05, maxHold: 20, tol: 0.02, trailPct: 0.03, trailCap: 0.06 },

  // ===== 双创 G1–G5 选股门（默认开启，保留核心逻辑）=====
  gates: {
    enabled: boolEnv('CHUANG_GATES', true),
    G1_liquidityFloor: 1.0e8,                 // G1 流动性：近20日日均成交额 ≥ 1亿元
    G2_atrMin: 0.03, G2_atrMax: 0.06,         // G2 波动率带：入场日 ATR14% ∈ [3%,6%]
    G3_ma20ExtMax: 0.12, G3_rsiLo: 40, G3_rsiHi: 65, // G3 动量洁净度：距MA20∈[0,+12%] 且 RSI∈[40,65]
    G4_relativeStrength: true,                // G4 相对强度：个股20日收益 > 上证同期
    G5_earningsQuality: true,                 // G5 盈利质量：读边车 g5Quality===false 才剔除整只
  },

  // ===== 双创 E1–E3 执行层（默认开启，保留核心逻辑）=====
  execution: {
    enabled: boolEnv('CHUANG_EXEC', true),
    E1_tpR: 2.0, E1_tpAtr: 1.8,               // E1 弹性止盈：TP = max(2.0×SL, 1.8×ATR14)
    E2_pullbackTol: 0.03,                     // E2 回踩入场：信号bar低点回踩至 MA20±3% 内且收在 MA20 上
    E3_trailPct: 0.02,                        // E3 跟踪止损：3% → 2%
    kAtr: 2.5,                                // 双创动态止损倍数（网格可覆盖）
    maxHold: 8,                               // 双创持有期（网格可覆盖）
    tol: 0.03,                                // 开盘偏离容差（双创）
  },

  // ===== 预过滤（trend/vol/gap，主板与双创共用，保留）=====
  preFilter: { maShort: 5, maTrend: 20, volMult: 1.2, gapDown: 0.04, gapUp: 0.06 },

  // ===== 指数 / 市况 =====
  index: { maWin: 60, ma20Win: 20, ma20agoWin: 20 },

  // ===== 组合层风控（保留）=====
  portfolio: { maxBuyPerDay: 3, ddPause: 0.08 },

  // ===== 网格搜索 =====
  grid: {
    mode: env.BT_GRID || 'full',             // full(48) / quick(16) / single
    kList: [1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
    hList: [5, 8, 10, 12],
    rList: ['none', 'not_bear'],
    kSingle: numEnv('BT_K', 3),
    hSingle: numEnv('BT_H', 5),
    rSingle: env.BT_R || 'none',
  },

  // ===== 达标线（用于筛 PASS 配置）=====
  passCriteria: { expMin: 0.30, pfMin: 1.6, kellyPos: true, nMin: 30 },

  // ===== 4.3 全市场优化 =====
  basket: { enabled: env.BT_BASKET === '1' },

  // ===== 新增可配置指标层（C1 质量增长筛选：开 revGrowth/npGrowth，关 pe/pb 待补数据）=====
  // 开启后作为额外筛选门槛，不改变默认回测行为；用于后续新 edge 研究。
  // 注意：fundamental.json 边车当前仅 9 支、无 PE/PB 字段，故 pe/pb 保持关闭（开启会因 null 全剔）。
  extraFilters: {
    pe:         { enabled: false, min: 0,    max: 60 },   // 市盈率（边车暂无字段，保持关）
    pb:         { enabled: false, min: 0,    max: 10 },   // 市净率（边车暂无字段，保持关）
    revGrowth:  { enabled: true, min: 0 },                 // C1: 营收同比增长(%) ≥ 0（剔除下滑）
    npGrowth:   { enabled: true, min: 0 },                 // C1: 净利润同比增长(%) ≥ 0（剔除下滑/亏损）
    macd:       { enabled: false, goldenCross: true },     // MACD 金叉 / 零轴上方
  },

  // ===== 持仓比例建议（signals 输出用）=====
  position: {
    method: 'kelly_atr',    // kelly_atr | fixed | vol_parity
    base: 0.10,             // 单笔基础仓位（fixed 用）
    kellyFraction: 0.5,     // Kelly 安全系数（半仓）
    atrRiskPct: 0.02,       // 单笔最大回撤预算（用于 ATR 仓位）
    maxPosition: 0.20,      // 单标的仓位上限
  },
};

// 网格展开：返回配置数组（与旧 grid 构造一致）
function buildGrid(cfg) {
  const g = cfg.grid;
  let kList = g.kList, hList = g.hList, rList = g.rList;
  if (g.mode === 'quick') { kList = [2.5, 3.0, 3.5, 4.0]; hList = [5, 8]; }
  if (g.mode === 'single') { kList = [g.kSingle]; hList = [g.hSingle]; rList = [g.rSingle]; }
  const grid = [];
  kList.forEach(kAtrDyn =>
    ['chuang_only'].forEach(boards =>
      rList.forEach(regime =>
        hList.forEach(maxHoldDyn => {
          grid.push({
            kAtrDyn, boards, regime, maxHoldDyn,
            maxHoldMain: cfg.main.maxHold,
            from: cfg.period.from, to: cfg.period.to,
          });
        }))));
  return grid;
}

module.exports = { CHUANG_CONFIG, boolEnv, numEnv, buildGrid };
