'use strict';
// chuang/index.js — 双创策略包 CLI 编排
// 子命令：
//   backtest   网格扫描 + 写回测结果（默认；保留原 `node backtest_chuang.js` 契约）
//   fund       采集/刷新基本面边车（保留原 `node extend_fundamental.js` 契约）
//   signals    生成结构化 BUY/SELL 信号 + 仓位建议（chuang_signals.json）
// 所有 BT_* / CHUANG_GATES / CHUANG_EXEC / FUND_* env 由 config.js 读取，契约不变。

const { CHUANG_CONFIG } = require('./config');
const { loadUniverse, loadIndex } = require('./data');
const { loadG5, loadFundStore } = require('./strategy');
const { runSweep } = require('./backtest');
const { buildFundamentals } = require('./fundamentals');
const { generateSignalsFile } = require('./signals');
const { Logger } = require('./logger');

const cmd = process.argv[2] || 'backtest';

async function main() {
  const config = CHUANG_CONFIG;
  if (cmd === 'backtest') {
    Logger.info('CLI', `加载宇宙: ${config.src}`);
    const items = loadUniverse(config.src);
    const index = loadIndex(config.indexFile);
    const g5 = loadG5(config.fundFile);
    const fund = loadFundStore(config.fundFile);
    Logger.info('CLI', `宇宙 ${items.length} 支，开始网格扫描…`);
    runSweep(config, { items, index, g5, fund, config });
  } else if (cmd === 'fund') {
    Logger.info('CLI', '采集基本面边车…');
    await buildFundamentals({ src: config.src, out: config.fundFile });
    Logger.info('CLI', `基本面边车完成: ${config.fundFile}`);
  } else if (cmd === 'signals') {
    const outFile = process.argv[3] || 'D:/WorkBuddy/选股结果/chuang_signals.json';
    Logger.info('CLI', `加载宇宙: ${config.src}`);
    const items = loadUniverse(config.src);
    const index = loadIndex(config.indexFile);
    const g5 = loadG5(config.fundFile);
    const fund = loadFundStore(config.fundFile);
    generateSignalsFile(items, config, { items, index, g5, fund, config }, { outFile });
  } else {
    Logger.error('CLI', `未知命令: ${cmd}（可用: backtest | fund | signals）`);
    process.exit(1);
  }
}

main().catch(e => { Logger.error('CLI', '异常: ' + (e && e.stack ? e.stack : e)); process.exit(1); });
