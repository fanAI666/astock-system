'use strict';
// chuang_pairing.js — Step2 原型：双创多 / 指数空 配对对冲（多基准对比）
// 方法：同一批修正引擎信号，对每笔交易用「指数持有期收益」做对冲腿，
//       hedgedRet = 个股ret − 指数同期收益；隔离选股 alpha 与方向 beta。
// 基准：中证500(sh000905) / 创业板指(sz399006) / 科创50(sh000688)。
// 仅输出独立报告，不污染生产 backtest_chuang.json。
const fs = require('fs');
const { CHUANG_CONFIG } = require('./chuang/config');
const { loadUniverse, loadIndex, loadSwitchIndex } = require('./chuang/data');
const { generateSignals, resetPreStats, loadG5, loadFundStore } = require('./chuang/strategy');
const { applyPortfolio } = require('./chuang/risk');
const { summarize } = require('./chuang/backtest');

function buildCtx(config) {
  const items = loadUniverse(config.src);
  const index = loadIndex(config.indexFile);
  const g5 = loadG5(config.fundFile);
  const fund = loadFundStore(config.fundFile);
  let switchIndex = null;
  const swFile = config.marketSwitch.indexFile;
  if (fs.existsSync(swFile)) { try { switchIndex = loadSwitchIndex(swFile, config.marketSwitch); } catch (e) {} }
  return { items, index, switchIndex, g5, fund, config };
}

// 指数日收益（紧凑 YYYYMMDD 键，对齐宇宙K线）
function buildBench(file) {
  const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
  const dates = raw.map(r => String(r[0]).replace(/-/g, ''));
  const close = raw.map(r => +r[2]);
  const ret = {};
  for (let i = 1; i < dates.length; i++) ret[dates[i]] = close[i] / close[i - 1] - 1;
  return { dates, ret };
}
function hedgeRet(b, entryDate, holdDays) {
  const s = b.dates.indexOf(entryDate);
  if (s < 0) return null;
  let eq = 1;
  for (let k = 1; k <= holdDays && s + k < b.dates.length; k++) eq *= (1 + (b.ret[b.dates[s + k]] || 0));
  return eq - 1;
}

const config = JSON.parse(JSON.stringify(CHUANG_CONFIG));
config.period.to = process.env.BT_TO || '20260731';
const ctx = buildCtx(config);
const gridCfg = {
  kAtrDyn: config.execution.kAtr, boards: 'chuang_only', regime: 'none',
  maxHoldDyn: config.execution.maxHold, maxHoldMain: config.main.maxHold,
  from: config.period.from, to: config.period.to,
};
resetPreStats();
let cands = [];
ctx.items.forEach(s => { cands = cands.concat(generateSignals(s, gridCfg, ctx)); });
const trades = applyPortfolio(cands, config, ctx.index).trades;

const benches = {
  zz500: { label: '中证500', file: 'D:/WorkBuddy/选股结果/index_zz500_raw.json' },
  cyb:   { label: '创业板指', file: 'D:/WorkBuddy/选股结果/index_cyb_raw.json' },
  kc50:  { label: '科创50',  file: 'D:/WorkBuddy/选股结果/index_kc50_raw.json' },
};
for (const k of Object.keys(benches)) benches[k].data = buildBench(benches[k].file);

function fmt(s) {
  return { n: s.total, win: +(s.winRate * 100).toFixed(1) + '%', exp: +(s.expectancy * 100).toFixed(3) + '%',
    pf: s.profitFactor == null ? 'inf' : +s.profitFactor.toFixed(2), maxDD: +(s.maxDD * 100).toFixed(1) + '%',
    kelly: +s.kelly.toFixed(2), avgHold: +s.avgHold.toFixed(1) };
}

const uBase = summarize(trades);
console.log('=== 样本 ===  未对冲交易数=', trades.length);
console.log('\n=== 基准（未对冲, 修正引擎）===');
console.log(JSON.stringify(fmt(uBase)));
console.log('未对冲分年度:', Object.fromEntries(['2024', '2025', '2026'].map(y => {
  const t = trades.filter(x => x.year === y); return [y, fmt(summarize(t))];
})));

const out = { generatedAt: new Date().toISOString().slice(0, 10), sample: trades.length, unhedged: fmt(uBase),
  unhedgedByYear: Object.fromEntries(['2024', '2025', '2026'].map(y => [y, fmt(summarize(trades.filter(x => x.year === y)))])),
  hedged: {} };

console.log('\n=== 对冲后（多双创 + 空指数）===');
for (const k of Object.keys(benches)) {
  const b = benches[k].data;
  const hedged = [];
  let cnt = 0;
  trades.forEach(t => {
    const h = hedgeRet(b, t.entryDate, t.holdDays);
    if (h === null) return;
    cnt++;
    const hr = t.ret - h;
    hedged.push({ ...t, ret: hr, outcome: hr >= 0 ? 'win' : 'loss' });
  });
  const hb = summarize(hedged);
  const f = fmt(hb);
  out.hedged[k] = { label: benches[k].label, ...f, hedgedN: cnt };
  console.log(`[${benches[k].label}] 可对冲=${cnt}  n=${f.n} 胜率=${f.win} 期望=${f.exp} PF=${f.pf} 回撤=${f.maxDD}`);
  console.log(`   delta期望=${(hb.expectancy - uBase.expectancy) * 100 >= 0 ? '+' : ''}${((hb.expectancy - uBase.expectancy) * 100).toFixed(3)}pp  deltaPF=${(f.pf === 'inf' ? 99 : f.pf) - (uBase.profitFactor == null ? 99 : uBase.profitFactor)}`);
  console.log('   分年度:', Object.fromEntries(['2024', '2025', '2026'].map(y => {
    const t = hedged.filter(x => x.year === y); return [y, fmt(summarize(t))];
  })));
}

fs.writeFileSync('D:/WorkBuddy/选股结果/pairing_zz500_result.json', JSON.stringify(out, null, 2), 'utf8');
console.log('\n已写出 选股结果/pairing_zz500_result.json');
