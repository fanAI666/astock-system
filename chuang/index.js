'use strict';
// chuang/index.js — 双创策略包 CLI 编排
// 子命令：
//   backtest   网格扫描 + 写回测结果（默认；保留原 `node backtest_chuang.js` 契约）
//   fund       采集/刷新基本面边车（保留原 `node extend_fundamental.js` 契约）
//   signals    生成结构化 BUY/SELL 信号 + 仓位建议（chuang_signals.json）
// 所有 BT_* / CHUANG_GATES / CHUANG_EXEC / FUND_* env 由 config.js 读取，契约不变。

const { CHUANG_CONFIG } = require('./config');
const { loadUniverse, loadIndex, loadSwitchIndex } = require('./data');
const { loadG5, loadFundStore } = require('./strategy');
const { runSweep } = require('./backtest');
const { buildFundamentals } = require('./fundamentals');
const { generateSignalsFile } = require('./signals');
const { getTrackSignalFn } = require('./tracks');
const data0 = require('./data0');
const { Logger } = require('./logger');
const fsX = require('fs');

const cmd = process.argv[2] || 'backtest';

// 板块映射归一化：bySector 由 sectorCode 索引 → 翻成 sectorName 索引，供 tracks 的 sectorMom/topSectors 直接消费
function loadSectors(sectorFile) {
  try {
    const raw = JSON.parse(fsX.readFileSync(sectorFile, 'utf8'));
    const bySectorName = {};
    Object.entries(raw.byCode || {}).forEach(([code, v]) => {
      const nm = v.sector; if (!nm) return;
      (bySectorName[nm] = bySectorName[nm] || []).push(code);
    });
    return { byCode: raw.byCode || {}, bySector: bySectorName };
  } catch (e) { Logger.warn('CLI', `板块映射加载失败: ${e.message}`); return { byCode: {}, bySector: {} }; }
}

// 加载方案0数据基建边车（仅当观察轨道激活时）
function loadData0Stores(config) {
  const d = config.data0;
  return {
    consensus: data0.loadConsensus(d.consensusFile),
    fundFlow: data0.loadFundFlow(d.fundFlowFile),
    pePct: data0.loadPePct(d.pePctFile),
    quarterly: data0.loadQuarterly(d.quarterlyFile),
    valuation: data0.loadValuation(d.valuationFile),
  };
}

// 构建回测 ctx（统一入口：backtest / invert / track 共用）
function buildBaseCtx(config, switchIndex) {
  const items = loadUniverse(config.src);
  const index = loadIndex(config.indexFile);
  const g5 = loadG5(config.fundFile);
  const fund = loadFundStore(config.fundFile);
  const sectors = loadSectors(config.tls.sectorFile);
  const ctx = { items, index, switchIndex, g5, fund, config, sectors };
  // TLS 主筛（路线 B，默认关 → parity 不变）
  if (config.tls && config.tls.enabled) {
    try {
      const { buildTlsPass } = require('./tls');
      const built = buildTlsPass(config);
      ctx.tlsPass = built.passByDate;
      Logger.info('CLI', `TLS 主筛已构建: ${JSON.stringify(built.stats)}`);
    } catch (e) { Logger.warn('CLI', `TLS 主筛构建失败: ${e.message}`); }
  }
  return ctx;
}

async function main() {
  const config = CHUANG_CONFIG;
  let switchIndex = null;
  const swFile = config.marketSwitch.indexFile;
  if (fsX.existsSync(swFile)) {
    try { switchIndex = loadSwitchIndex(swFile, config.marketSwitch); Logger.info('CLI', `大盘开关指数已加载: ${swFile}`); }
    catch (e) { Logger.warn('CLI', `大盘开关指数加载失败: ${e.message}`); }
  } else {
    Logger.warn('CLI', `大盘开关指数缺失(${swFile})，运行 fetch_switch_index 生成；本轮 bySwitch 全 na`);
  }

  if (cmd === 'backtest') {
    Logger.info('CLI', `加载宇宙: ${config.src}`);
    const ctx = buildBaseCtx(config, switchIndex);
    // 若显式开启观察轨道（CHUANG_TRACK），注入 signalFn + 方案0 边车
    if (config.track.active !== 'none') {
      const sigFn = getTrackSignalFn(config.track.active);
      if (sigFn) { ctx.signalFn = sigFn; Object.assign(ctx, loadData0Stores(config)); Logger.info('CLI', `观察轨道激活: ${config.track.active}`); }
    }
    Logger.info('CLI', `宇宙 ${ctx.items.length} 支，开始网格扫描…`);
    runSweep(config, ctx);
  } else if (cmd === 'invert') {
    // 5.0 反手证伪：翻转动量入场极性，其余全不变 → 纯净 A/B
    config.invert = true;
    Logger.info('CLI', `5.0 反手证伪模式：invert=true（翻转 G3/G4/preFilter/E2）`);
    Logger.info('CLI', `加载宇宙: ${config.src}`);
    const ctx = buildBaseCtx(config, switchIndex);
    Logger.info('CLI', `宇宙 ${ctx.items.length} 支，开始反手网格扫描…`);
    runSweep(config, ctx);
  } else if (cmd === 'track') {
    // 观察轨道独立命令：node index.js track <5.1|5.2|...|5.6> [--quick]
    const active = process.argv[3];
    const sigFn = getTrackSignalFn(active);
    if (!sigFn) { Logger.error('CLI', `未知轨道: ${active}（可用 5.1–5.6）`); process.exit(1); }
    config.track.active = active;
    config.tracks[active].enabled = true;
    // 安全护栏 + 观察宇宙：观察轨道默认写入独立产物、扫描全候选池(1270)，绝不污染生产回测文件
    if (!process.env.BT_OUT) config.out = `D:/WorkBuddy/选股结果/bt_track${active}.json`;
    if (!process.env.BT_SRC) config.src = 'D:/WorkBuddy/选股结果/universe_klines.json';
    // 网格收敛到单点（regime=none，持有区间由轨道 clamp），便于快速评估
    config.grid.mode = 'single';
    config.grid.rSingle = 'none';
    config.grid.hSingle = config.tracks[active].holdDays || config.tracks[active].holdMax || 20;
    config.grid.kSingle = 3.0;
    Logger.info('CLI', `观察轨道 ${active}：加载方案0边车…`);
    const ctx = buildBaseCtx(config, switchIndex);
    Object.assign(ctx, loadData0Stores(config));
    ctx.signalFn = sigFn;
    const cov = k => Object.keys(ctx[k] || {}).length;
    Logger.info('CLI', `方案0 边车覆盖: 估值=${cov('valuation')} 资金流=${cov('fundFlow')} 季报=${cov('quarterly')} 一致预期=${cov('consensus')} PE代理=${cov('pePct')}`);
    Logger.info('CLI', `宇宙 ${ctx.items.length} 支，开始 ${active} 轨道扫描…`);
    runSweep(config, ctx);
  } else if (cmd === 'fund') {
    Logger.info('CLI', '采集基本面边车…');
    await buildFundamentals({ src: config.src, out: config.fundFile });
    Logger.info('CLI', `基本面边车完成: ${config.fundFile}`);
  } else if (cmd === 'signals') {
    const outFile = process.argv[3] || 'D:/WorkBuddy/选股结果/chuang_signals.json';
    Logger.info('CLI', `加载宇宙: ${config.src}`);
    const ctx = buildBaseCtx(config, switchIndex);
    generateSignalsFile(ctx.items, config, ctx, { outFile });
  } else {
    Logger.error('CLI', `未知命令: ${cmd}（可用: backtest | invert | track | fund | signals）`);
    process.exit(1);
  }
}

// 仅当作为独立脚本运行才启动主流程；被 require 时不执行，避免意外触发回测覆盖生产文件
if (require.main === module) {
  main().catch(e => { Logger.error('CLI', '异常: ' + (e && e.stack ? e.stack : e)); process.exit(1); });
}
