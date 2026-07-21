// phase0b_merge.js — Phase 0b-3
// 把已落盘的 3 年日线(tool-results/*.txt) 合并进 import_final.json：
//   1) 7 支原候选：用落盘文件刷新 kline.day(取更长序列)
//   2) 17 支新候选(均线多头排列 screener)：按 build_final.py 口径计算元数据(ma20/ma60/rsi/atr/vol/struct/sector/score/win/stop/target)后追加
// 输出宇宙 = 7 + 17 = 24 支，主板数显著扩大 → 供 backtest_phase12.js 跑 main_only 看 n 是否≥300

const fs = require('fs');
const path = require('path');

const TOOL_DIR = 'C:/Users/fanfan/.workbuddy/projects/d-WorkBuddy/e0b70369-9b1d-4187-a9f3-62e9dcb5fced/tool-results/';
const SRC = 'D:/WorkBuddy/选股结果/import_final.json';
const BAK = 'D:/WorkBuddy/选股结果/import_final.phase0b_bak';

const INDEX_CODES = new Set(['000001', '1A0001', '999999']);

// ---------- 1) 解析落盘文件 -> byCode ----------
function parseCode(code) { return String(code).replace(/\D/g, ''); }
function boardOf(code) {
  if (/^(600|601|603|000|002|001)/.test(code)) return 'main';
  if (/^(300|301)/.test(code)) return 'cyb';
  if (/^688/.test(code)) return 'kcb';
  return 'main';
}
function setcodeOf(code) { return code[0] === '6' ? '1' : '0'; }

const files = fs.readdirSync(TOOL_DIR).filter(f => f.includes('tdx_kline') && f.endsWith('.txt'));
const byCode = {};
for (const f of files) {
  const st = fs.statSync(path.join(TOOL_DIR, f));
  if (st.size < 200000) continue; // 仅 3 年拉取
  const txt = fs.readFileSync(path.join(TOOL_DIR, f), 'utf8');
  const j = txt.indexOf('{'); if (j < 0) continue;
  let obj; try { obj = JSON.parse(txt.slice(j)); } catch (e) { continue; }
  const code = parseCode(obj.Code); if (!code) continue;
  if (INDEX_CODES.has(code)) continue; // 指数单独处理，不进个股池
  const rows = obj.Rows || []; if (!rows.length) continue;
  const bars = []; const seen = new Set();
  for (const r of rows) {
    const d = String(r.Data); if (!d || seen.has(d)) continue;
    const open = parseFloat(r.Open), close = parseFloat(r.Close), high = parseFloat(r.High), low = parseFloat(r.Low);
    let vol = parseFloat(r.Volume);
    if (!isFinite(vol)) vol = (parseFloat(r.RawVolume) || 0) / 100;
    if (![open, close, high, low].every(isFinite)) continue;
    seen.add(d);
    bars.push([d, +open.toFixed(4), +close.toFixed(4), +high.toFixed(4), +low.toFixed(4), +vol.toFixed(2)]);
  }
  bars.sort((a, b) => (a[0] < b[0] ? -1 : 1));
  if (!byCode[code] || byCode[code].bars.length < bars.length) {
    byCode[code] = { name: (obj.AttachInfo && obj.AttachInfo.Name) || '', bars, setcode: obj.Setcode != null ? String(obj.Setcode) : setcodeOf(code) };
  }
}
console.log('落盘解析到代码:', Object.keys(byCode).sort().join(', '));

// ---------- 2) 指标计算(与 build_final.py 一致) ----------
function sma(vals, n) { if (vals.length < n) return vals.reduce((a, b) => a + b, 0) / Math.max(1, vals.length); return vals.slice(-n).reduce((a, b) => a + b, 0) / n; }
function rsi(closes, n = 14) {
  if (closes.length < n + 1) return 50.0;
  const gains = [], losses = [];
  for (let i = 1; i < closes.length; i++) { const ch = closes[i] - closes[i - 1]; gains.push(Math.max(ch, 0)); losses.push(Math.max(-ch, 0)); }
  let g = gains.slice(0, n).reduce((a, b) => a + b, 0) / n, l = losses.slice(0, n).reduce((a, b) => a + b, 0) / n;
  for (let i = n; i < gains.length; i++) { g = (g * (n - 1) + gains[i]) / n; l = (l * (n - 1) + losses[i]) / n; }
  if (l === 0) return 100.0; const rs = g / l; return 100 - 100 / (1 + rs);
}
function atrPct(bars, n = 14) {
  if (bars.length < n + 1) return 0.0;
  const trs = [];
  for (let i = 1; i < bars.length; i++) { const h = bars[i][3], l = bars[i][4], c0 = bars[i - 1][2]; trs.push(Math.max(h - l, Math.abs(h - c0), Math.abs(l - c0))); }
  return sma(trs, n) / bars[bars.length - 1][2] * 100;
}
function metrics(day) {
  const closes = day.map(b => b[2]), vols = day.map(b => b[5]);
  const ma20 = sma(closes, 20), ma20_5 = closes.length > 25 ? sma(closes.slice(0, -5), 20) : ma20;
  const ma60 = sma(closes, 60), ma60_5 = closes.length > 65 ? sma(closes.slice(0, -5), 60) : ma60;
  const last = closes[closes.length - 1];
  const ma20_up = ma20 >= ma20_5, price_above = last >= ma20, ma60_up = ma60 >= ma60_5;
  const r = rsi(closes, 14), a = atrPct(day, 14);
  const ma20v = sma(vols, 20); const vratio = ma20v > 0 ? vols[vols.length - 1] / ma20v : 1.0;
  const vol = vratio >= 1.5 ? 'high' : vratio >= 0.8 ? 'normal' : 'low';
  const highs = day.map(b => b[3]); const prev19 = highs.length >= 20 ? Math.max(...highs.slice(-20, -1)) : Math.max(...highs);
  let struct; if (highs[highs.length - 1] > prev19 * 1.0001) struct = 'breakout';
  else if (Math.abs(last - ma20) / ma20 < 0.03 && closes[closes.length - 1] < closes[closes.length - 2]) struct = 'pullback';
  else struct = 'neutral';
  return { ma20: ma20_up ? 'up' : 'down', priceMa: price_above ? 'above' : 'below', ma60: ma60_up ? 'up' : 'down', rsi: +r.toFixed(1), atr: +a.toFixed(2), vol, struct, sector: 'mid' };
}
function boardParams(board) { return (board === 'main' || board === 'cyb') ? { loss: 2.0, profit: 6.0, k_atr: 1.5 } : { loss: 5.0, profit: 15.0, k_atr: 2.5 }; }
function scoreCandidate(c) {
  let s = 0; const reasons = [];
  if (c.rsi > 72) { return { total: 0, strength: 0, reject: `RSI=${c.rsi}>72 超买` }; }
  if (c.ma60 !== 'up') { return { total: 0, strength: 0, reject: `MA60=${c.ma60} 未向上` }; }
  let t = 0; if (c.ma20 === 'up') t += 10; if (c.priceMa === 'above') t += 8; if (c.ma60 === 'up') t += 7; s += t; reasons.push(`趋势${t}`);
  const st = { breakout: 20, pullback: 16 }[c.struct] || 4; s += st; reasons.push(`结构${st}`);
  const v = { high: 15, normal: 8, low: 2 }[c.vol]; s += v; reasons.push(`量能${v}`);
  const sec = { strong: 15, mid: 9, weak: 3 }[c.sector]; s += sec; reasons.push(`板块${sec}`);
  let rr; if (c.rsi >= 40 && c.rsi <= 60) rr = 15; else if ((c.rsi >= 30 && c.rsi < 40) || (c.rsi > 60 && c.rsi <= 70)) rr = 8; else rr = 3; s += rr; reasons.push(`RSI${rr}`);
  const bp = boardParams(c.board); const fit = Math.max(0, Math.round(10 * Math.max(0, 1 - c.atr / (bp.loss * bp.k_atr)))); s += fit; reasons.push(`ATR适配${fit}`);
  const strength = Math.min(88, +(50 + s * 0.35).toFixed(1));
  return { total: s, strength, reject: null, reasons };
}

// ---------- 3) 读 import_final.json ----------
const data = JSON.parse(fs.readFileSync(SRC, 'utf8'));
fs.copyFileSync(SRC, BAK); // 备份
const existing = data.items || [];
const existingCodes = new Set(existing.map(s => String(s.code)));

// 3a) 刷新 7 原候选 kline.day
let refreshed = 0;
for (const s of existing) {
  const hit = byCode[String(s.code)];
  if (hit && hit.bars.length > (s.kline && s.kline.day ? s.kline.day.length : 0)) {
    s.kline = s.kline || {}; s.kline.day = hit.bars; refreshed++;
  }
}
console.log(`原候选刷新 kline.day: ${refreshed}/${existing.length}`);

// 3b) 构建 17 新候选
const newItems = [];
for (const code of Object.keys(byCode).sort()) {
  if (existingCodes.has(code)) continue;
  const { name, bars, setcode } = byCode[code];
  const board = boardOf(code);
  const m = metrics(bars);
  const sc = scoreCandidate({ board, ...m });
  const entry = bars[bars.length - 1][2];
  const bp = boardParams(board);
  const stopPrice = +((entry * (1 - bp.loss / 100)).toFixed(2));
  const targetPrice = +((entry * (1 + bp.profit / 100)).toFixed(2));
  const item = {
    name: (name ? `${name} ${code}` : code),
    code, setcode: setcode || setcodeOf(code), board,
    ma20: m.ma20, priceMa: m.priceMa, ma60: m.ma60, rsi: m.rsi, vol: m.vol, struct: m.struct, sector: m.sector, atr: m.atr,
    score: sc.total, win: sc.strength,
    category: 'final', date: bars[bars.length - 1][0],
    stopPrice, targetPrice,
    kline: { day: bars }
  };
  newItems.push(item);
  console.log(`+新增 ${code} ${name} board=${board} ma20=${m.ma20} ma60=${m.ma60} rsi=${m.rsi} atr=${m.atr}% struct=${m.struct} score=${sc.total} str=${sc.strength} bars=${bars.length}`);
}

// ---------- 4) 合并写回 ----------
const merged = existing.concat(newItems);
const out = { updated: new Date().toISOString(), items: merged, watch: data.watch || [] };
fs.writeFileSync(SRC, JSON.stringify(out), 'utf8');
const boardCount = {}; merged.forEach(s => boardCount[s.board] = (boardCount[s.board] || 0) + 1);
console.log(`\n合并完成: 宇宙=${merged.length} 支 | 主板=${boardCount.main || 0} 双创=${boardCount.cyb || 0} 科创=${boardCount.kcb || 0}`);
console.log(`原候选=${existing.length} + 新增=${newItems.length} = ${merged.length}`);
console.log(`文件大小: ${(fs.statSync(SRC).size / 1024).toFixed(1)} KB | 备份: ${BAK}`);
