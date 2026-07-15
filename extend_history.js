// extend_history.js — 用通达信(TDX) MCP 拉取的 320 根真实日线，
// 替换 import_final.json 中各候选股的 kline.day（原仅 70 根，2026-03 起）。
// 同时把上证指数 000001 单独存出，供 ⑤ 大盘硬过滤使用。
//
// 列映射（TDX Rows 对象 → backtest bar）：
//   bar = [ date, open, close, high, low, volume ]
//   Data→日期, Open→开, Close→收, High→高, Low→低, Volume→量
// 与 import_final.json 既有 kline.day 格式完全一致（date 为 "YYYYMMDD" 字符串）。

const fs = require('fs');
const path = require('path');

const TOOL_DIR = 'C:/Users/fanfan/.workbuddy/projects/d-WorkBuddy/e0b70369-9b1d-4187-a9f3-62e9dcb5fced/tool-results/';
const SRC = 'D:/WorkBuddy/选股结果/import_final.json';
const BAK = 'D:/WorkBuddy/选股结果/import_final.bak';
const INDEX_OUT = 'D:/WorkBuddy/选股结果/index_sh.json';

const INDEX_CODES = new Set(['000001', '1A0001', '999999']); // 上证指数常见代码

// 1) 扫描所有 tdx 文件，按 Code 聚合（保留最长序列）
const files = fs.readdirSync(TOOL_DIR).filter(f => f.includes('tdx_kline'));
const byCode = {}; // code -> { name, bars:[[...]] }

for (const f of files) {
  const txt = fs.readFileSync(path.join(TOOL_DIR, f), 'utf8');
  const j = txt.indexOf('{');
  if (j < 0) continue;
  let obj; try { obj = JSON.parse(txt.slice(j)); } catch (e) { continue; }
  const code = obj.Code;
  if (!code) continue;
  const rows = obj.Rows || [];
  if (!rows.length) continue;

  const bars = [];
  const seen = new Set();
  for (const r of rows) {
    const d = String(r.Data);
    if (!d || seen.has(d)) continue;
    const open = parseFloat(r.Open), close = parseFloat(r.Close),
          high = parseFloat(r.High), low = parseFloat(r.Low);
    let vol = parseFloat(r.Volume);
    if (!isFinite(vol)) vol = (parseFloat(r.RawVolume) || 0) / 100;
    if (![open, close, high, low].every(isFinite)) continue;
    seen.add(d);
    bars.push([d, +open.toFixed(4), +close.toFixed(4), +high.toFixed(4), +low.toFixed(4), +vol.toFixed(2)]);
  }
  bars.sort((a, b) => (a[0] < b[0] ? -1 : 1));

  if (!byCode[code] || byCode[code].bars.length < bars.length) {
    byCode[code] = { name: obj.AttachInfo && obj.AttachInfo.Name, bars };
  }
}
console.log('解析到代码:', Object.keys(byCode).join(', '));

// 2) 上证指数单独存出
let indexSaved = null;
for (const ic of INDEX_CODES) {
  if (byCode[ic]) {
    const idx = byCode[ic];
    const out = {
      code: ic, name: idx.name || '上证指数',
      board: 'index',
      bars: idx.bars,
      updated: new Date().toISOString().slice(0, 10)
    };
    fs.writeFileSync(INDEX_OUT, JSON.stringify(out, null, 2), 'utf8');
    indexSaved = { code: ic, name: out.name, bars: idx.bars.length };
    console.log(`上证指数已存: ${out.name} (${idx.bars.length} 根, ${idx.bars[0][0]}~${idx.bars[idx.bars.length-1][0]})`);
    break;
  }
}
if (!indexSaved) console.log('⚠ 未找到上证指数(000001)数据');

// 3) 替换 import_final.json 各票 kline.day
const data = JSON.parse(fs.readFileSync(SRC, 'utf8'));
fs.copyFileSync(SRC, BAK); // 备份原 70 根版本
const items = data.items || [];
let matched = 0, totalBars = 0, minBars = 1e9, maxBars = 0;
for (const s of items) {
  const hit = byCode[s.code];
  if (!hit) { console.log(`⚠ 未匹配到 TDX 数据: ${s.code} ${s.name}`); continue; }
  s.kline = s.kline || {};
  s.kline.day = hit.bars;
  matched++;
  totalBars += hit.bars.length;
  minBars = Math.min(minBars, hit.bars.length);
  maxBars = Math.max(maxBars, hit.bars.length);
}
data.updated = new Date().toISOString();
fs.writeFileSync(SRC, JSON.stringify(data), 'utf8'); // 紧凑写回（面板读取无影响）

console.log(`\n替换完成: ${matched}/${items.length} 支匹配`);
console.log(`每票根数: min=${minBars}, max=${maxBars}, 均值=${(totalBars/matched).toFixed(0)}`);
console.log(`备份原文件 → ${BAK}`);
console.log(`新文件大小: ${(fs.statSync(SRC).size/1024).toFixed(1)} KB (原 ${(fs.statSync(BAK).size/1024).toFixed(1)} KB)`);
