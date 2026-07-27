'use strict';
// backtest_chuang.js — 薄入口（重构后）
// 保留 `node backtest_chuang.js` 调用契约：逻辑已迁入 chuang/ 模块化包。
// 所有 BT_SRC / BT_OUT / BT_FUND / BT_GRID / BT_K / BT_H / BT_R / BT_BASKET /
// CHUANG_GATES / CHUANG_EXEC env 由 chuang/config.js 读取，契约不变。
const { CHUANG_CONFIG } = require('./chuang/config');
const { loadUniverse, loadIndex } = require('./chuang/data');
const { loadG5, loadFundStore } = require('./chuang/strategy');
const { runSweep } = require('./chuang/backtest');

const cfg = CHUANG_CONFIG;
const items = loadUniverse(cfg.src);
const index = loadIndex(cfg.indexFile);
const g5 = loadG5(cfg.fundFile);
const fund = loadFundStore(cfg.fundFile);
runSweep(cfg, { items, index, g5, fund, config: cfg });
