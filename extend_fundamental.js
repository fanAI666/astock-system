'use strict';
// extend_fundamental.js — 薄入口（重构后）
// 保留 `node extend_fundamental.js` 调用契约：逻辑已迁入 chuang/fundamentals.js。
// 所有 FUND_* / BT_FUND / BT_SRC env 由 chuang/config.js 读取，契约不变。
const { CHUANG_CONFIG } = require('./chuang/config');
const { buildFundamentals } = require('./chuang/fundamentals');

buildFundamentals({
  src: CHUANG_CONFIG.src,
  out: CHUANG_CONFIG.fundFile,
  codesFile: process.env.CODES_FILE || '',
  skipG6: process.env.SKIP_G6 === '1',
  skipVal: process.env.SKIP_VAL === '1',
})
  .then(() => { console.log('fundamentals done →', CHUANG_CONFIG.fundFile); })
  .catch(e => { console.error(e); process.exit(1); });
