'use strict';
// chuang/data.js — 数据获取与归一化（独立模块）
// 职责：① 加载 K线源文件（import_final.json / universe_klines.json 等，兼容 {items} 或扁平 dict）
//       ② 加载上证指数并预构建市况判定（idxClose/idxPos/idxMA/idxMA20/idxMA20ago，O(1)）
//       ③ 全市场双创枚举 + 日K 抓取（从 expand_universe.js 迁入，保留东财枚举 + 腾讯 ifzq 抓取 + 断点续跑）
// 所有函数纯数据层，不含任何策略逻辑；策略层（strategy.js）只消费这里产出的结构。

const fs = require('fs');
const { Logger } = require('./logger');

// ===== ① K线加载 / 归一化 =====
// 返回 items 数组：[{code,name,board,kline:{day:[[date,open,close,high,low,vol],...]}}]
function loadUniverse(src) {
  const raw = JSON.parse(fs.readFileSync(src, 'utf8'));
  if (Array.isArray(raw)) return raw;
  if (raw && Array.isArray(raw.items)) return raw.items;
  if (raw && typeof raw === 'object') {
    // 扁平 dict：{ code: {name,board,kline} } → 补 code 字段
    return Object.entries(raw).map(([code, v]) => ({ code, ...v }));
  }
  return [];
}

// ===== ② 指数加载 + 市况判定（与旧 backtest_chuang.js 逐字等价，保证 parity）=====
function loadIndex(indexFile) {
  const idx = JSON.parse(fs.readFileSync(indexFile, 'utf8'));
  const ib = idx.bars || [];
  const idxClose = {}, idxMA = {};
  ib.forEach(b => { idxClose[b[0]] = b[2]; });
  const idxDates = ib.map(b => b[0]).sort();
  const idxPos = {}; idxDates.forEach((d, i) => idxPos[d] = i);
  const IDX_MA_WIN = 60, MA20 = 20;
  for (let i = 0; i < ib.length; i++) {
    if (i >= IDX_MA_WIN - 1) {
      let s = 0; for (let k = i - IDX_MA_WIN + 1; k <= i; k++) s += ib[k][2];
      idxMA[ib[i][0]] = s / IDX_MA_WIN;
    }
  }
  const idxMA20 = {}, idxMA20ago = {};
  for (let i = 0; i < ib.length; i++) {
    if (i >= MA20 - 1) { let s = 0; for (let k = i - MA20 + 1; k <= i; k++) s += ib[k][2]; idxMA20[ib[i][0]] = s / MA20; }
    if (i >= MA20 - 1 + MA20) { let s2 = 0; for (let k = i - MA20 - MA20 + 1; k <= i - MA20; k++) s2 += ib[k][2]; idxMA20ago[ib[i][0]] = s2 / MA20; }
  }
  function idxRegime(date, kind) {
    const cl = idxClose[date], ma = idxMA[date], ma20 = idxMA20[date];
    if (cl == null) return 'unknown';
    if (kind === 'ma20_up') { if (ma20 == null) return 'unknown'; return cl > ma20 ? 'bull' : 'bear'; }
    if (ma == null) return 'unknown';
    const ma20ago = idxMA20ago[date]; if (ma20ago == null) return 'unknown';
    if (cl > ma && ma >= ma20ago) return 'bull';
    if (cl < ma && ma < ma20ago) return 'bear';
    return 'side';
  }
  function regimeOf(date, kind) {
    if (kind === 'basket' || kind === 'basket_not_bear') return 'unknown'; // basket 由市况模块另算
    return idxRegime(date, kind === 'ma20_up' ? 'ma20_up' : 'ma60');
  }
  return { idxClose, idxPos, idxDates, idxMA, idxMA20, idxMA20ago, regimeOf, bars: ib };
}

// ===== 大盘开关指数（创业板指 sz399006 + 沪深300 sh000300）=====
// switch_index.json = { cyb:[bars], hs300:[bars] }，bars=[date,o,c,h,l,v]
// 评估器 switchOf(date) → 'open' | 'closed' | 'na'（na=数据缺失，部署态视为关门）
function buildSwitchIdx(bars) {
  const close = {}, vol = {}, dates = bars.map(b => b[0]).sort(), pos = {};
  dates.forEach(d => { pos[d] = bars.findIndex(b => b[0] === d); });
  dates.forEach(d => { close[d] = bars[pos[d]][2]; vol[d] = bars[pos[d]][5]; });
  const ma20 = {}, vol20 = {};
  for (let i = 0; i < bars.length; i++) {
    if (i >= 19) {
      let s = 0, v = 0;
      for (let k = i - 19; k <= i; k++) { s += bars[k][2]; v += bars[k][5]; }
      ma20[bars[i][0]] = s / 20; vol20[bars[i][0]] = v / 20;
    }
  }
  return { close, vol, dates, pos, ma20, vol20 };
}
function loadSwitchIndex(file, ms) {
  const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
  const cyb = buildSwitchIdx(raw.cyb || []), hz = buildSwitchIdx(raw.hs300 || []);
  const L = ms.rsLookback, M = ms.maWin, V = ms.volMult;
  function switchOf(date) {
    const ci = cyb.pos[date], hi = hz.pos[date];
    if (ci == null || hi == null || ci < L || hi < L) return 'na';
    const c = cyb.close[date], ma = cyb.ma20[date], v = cyb.vol[date], v20 = cyb.vol20[date];
    if (c == null || ma == null || v == null || v20 == null) return 'na';
    let ok = true;
    if (ms.rsRequired) {
      const c5 = cyb.close[cyb.dates[ci - L]], h5 = hz.close[hz.dates[hi - L]];
      if (c5 == null || h5 == null) return 'na';
      const rs = (c / c5 - 1) - (hz.close[date] / h5 - 1);
      if (!(rs > 0)) ok = false;
    }
    if (ms.ma20Required && !(c > ma)) ok = false;
    if (ms.volRequired && !(v > v20 * V)) ok = false;
    return ok ? 'open' : 'closed';
  }
  return { switchOf };
}

// ===== ③ 全市场双创枚举 + 日K 抓取（接管 expand_universe.js）=====
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function fetchJson(url, referer, retries = 4) {
  for (let a = 0; a <= retries; a++) {
    try {
      const r = await fetch(url, { headers: { 'Referer': referer, 'User-Agent': 'Mozilla/5.0' } });
      if (r.ok) return await r.json();
    } catch (e) { /* 重试 */ }
    await sleep(500 * (a + 1) + Math.floor(Math.random() * 300));
  }
  return null;
}

// 枚举全市场双创（东财选股器分页，本地按代码前缀过滤，剔除 ST/退市）
async function enumerateChuang() {
  const out = [];
  let page = 1;
  while (true) {
    const url = `https://datacenter.eastmoney.com/stock/selection/api/data/get/?type=RPTA_APP_STOCKSELECT&sty=SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,MARKET&filter=(NEW_PRICE%3E0)&p=${page}&ps=500&st=SECURITY_CODE&sr=1&source=SELECT_SECURITIES&client=APP`;
    const j = await fetchJson(url, 'https://data.eastmoney.com/');
    const d = (j && j.result && j.result.data) || [];
    if (!d.length) break;
    d.forEach(x => {
      const c = x.SECURITY_CODE, nm = x.SECURITY_NAME_ABBR || '';
      if (/ST|退/.test(nm)) return;
      if (c.startsWith('30')) out.push({ code: c, name: nm, board: 'cyb' });
      else if (c.startsWith('688')) out.push({ code: c, name: nm, board: 'kcb' });
    });
    if (!j.result.nextpage) break;
    page++;
    if (page > 20) break;
    await sleep(120);
  }
  return out;
}

// 拉单支日K（腾讯 ifzq，前复权）→ [[YYYYMMDD,open,close,high,low,vol],...]；失败返回 null（便于续跑补抓）
async function fetchKlineTencent(code, beg = '2023-08-28', end = '2026-06-30') {
  const tc = (/^6/.test(code) ? 'sh' : 'sz') + code;
  const url = `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${tc},day,${beg},${end},800,qfq`;
  const j = await fetchJson(url, 'https://gu.qq.com/');
  const d = j && j.data && j.data[tc];
  const ks = d && (d.qfqday || d.day);
  if (!Array.isArray(ks) || !ks.length) return null;
  const day = [];
  for (const p of ks) {
    if (p.length < 6) continue;
    day.push([p[0].replace(/-/g, ''), +p[1], +p[2], +p[3], +p[4], +p[5]]);
  }
  return day;
}

// 构建 / 续补宇宙 K线（断点续跑：已缓存的跳过，失败的留待下次补）
async function buildUniverse(opts = {}) {
  const OUT = opts.out || 'D:/WorkBuddy/选股结果/universe_klines.json';
  const BEG = opts.beg || '20230828', END = opts.end || '20260630';
  const CONC = opts.conc || 5, CKPT = opts.ckpt || 40, BATCH_GAP = opts.batchGap || 200;
  Logger.info('DATA', `枚举全市场双创…`);
  const list = await enumerateChuang();
  const cyb = list.filter(x => x.board === 'cyb').length, kcb = list.filter(x => x.board === 'kcb').length;
  Logger.info('DATA', `枚举到 创业板 ${cyb} + 科创板 ${kcb} = ${list.length} 支`);

  let store = {};
  if (fs.existsSync(OUT)) {
    try { (JSON.parse(fs.readFileSync(OUT, 'utf8')).items || []).forEach(s => store[s.code] = s); } catch (e) { }
  }
  const todo = list.filter(x => !store[x.code]);
  Logger.info('DATA', `已缓存 ${Object.keys(store).length}，待抓 ${todo.length} 支（并发${CONC}）`);

  let done = 0, ok = 0, skipShort = 0, fail = 0;
  for (let i = 0; i < todo.length; i += CONC) {
    const batch = todo.slice(i, i + CONC);
    await Promise.all(batch.map(async x => {
      const day = await fetchKlineTencent(x.code);
      if (day === null) fail++;
      else if (day.length >= 60) { store[x.code] = { code: x.code, name: x.name, board: x.board, kline: { day } }; ok++; }
      else skipShort++;
    }));
    done += batch.length;
    if (done % CKPT < CONC || done >= todo.length) {
      fs.writeFileSync(OUT, JSON.stringify({ updated: new Date().toISOString().slice(0, 10), period: [BEG, END], items: Object.values(store) }), 'utf8');
      Logger.info('DATA', `进度 ${done}/${todo.length} | 有效 ${ok} | 历史过短 ${skipShort} | 失败待补 ${fail} | 累计 ${Object.keys(store).length}`);
    }
    await sleep(BATCH_GAP);
  }
  if (fail > 0) Logger.warn('DATA', `${fail} 支抓取失败（网络/反爬），重跑可断点续补`);
  const items = Object.values(store);
  const c2 = items.filter(s => s.board === 'cyb').length, k2 = items.filter(s => s.board === 'kcb').length;
  Logger.info('DATA', `完成：universe ${items.length} 支（创业板 ${c2} + 科创板 ${k2}）→ ${OUT}`);
  return items;
}

module.exports = { loadUniverse, loadIndex, loadSwitchIndex, enumerateChuang, fetchKlineTencent, buildUniverse };
