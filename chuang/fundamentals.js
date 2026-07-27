'use strict';
// chuang/fundamentals.js — 双创基本面采集与边车（接管 extend_fundamental.js）
// 数据源：东方财富公开 F10 接口（Node 直接 HTTP，无需 tdx/westock 连接器）。
// 为什么写【边车】选股结果/fundamental.json：build_final.py 每日从零重建 import_final.json，
//   任何写入其中的字段次日被抹；边车 build_final 完全不碰，天然规避覆盖，兼容性最优。
// 新增：PE/PB（估值接口，best-effort，失败为 null），供 extraFilters 使用（默认关闭，不影响 parity）。
// 运行：node 经 index/cli 或直接 require 本模块调用 buildFundamentals({...})。

const fs = require('fs');
const { Logger } = require('./logger');

function secucode(code) { return /^6/.test(code) ? code + '.SH' : code + '.SZ'; }

async function fetchJson(url, referer, retries = 3) {
  for (let a = 0; a <= retries; a++) {
    try {
      const r = await fetch(url, { headers: { 'Referer': referer, 'User-Agent': 'Mozilla/5.0' } });
      if (r.ok) return await r.json();
    } catch (e) { /* 重试 */ }
    await new Promise(r => setTimeout(r, 400 * (a + 1)));
  }
  return null;
}

// 拉最近 16 期财务主指标（累计值）
async function getFin(sec) {
  const cols = 'SECUCODE,REPORT_DATE,REPORT_TYPE,TOTALOPERATEREVE,PARENTNETPROFIT,PARENTNETPROFITTZ,TOTALOPERATEREVETZ';
  const url = `https://datacenter.eastmoney.com/securities/api/data/v1/get?reportName=RPT_F10_FINANCE_MAINFINADATA&columns=${encodeURIComponent(cols)}&filter=${encodeURIComponent(`(SECUCODE="${sec}")`)}&pageNumber=1&pageSize=16&sortTypes=-1&sortColumns=REPORT_DATE&source=HSF10&client=PC`;
  const j = await fetchJson(url, 'https://emweb.securities.eastmoney.com/');
  return (j.result && j.result.data) || [];
}

// 累计(YTD)净利润拆单季 { 'YYYY-MM': 单季NP }
function singleQuarters(rows) {
  const byYear = {};
  rows.forEach(r => {
    const y = r.REPORT_DATE.slice(0, 4), m = r.REPORT_DATE.slice(5, 7);
    (byYear[y] = byYear[y] || {})[m] = r.PARENTNETPROFIT;
  });
  const sq = {};
  Object.keys(byYear).forEach(y => {
    const g = byYear[y];
    if (g['03'] != null) sq[y + '-03'] = g['03'];
    if (g['03'] != null && g['06'] != null) sq[y + '-06'] = g['06'] - g['03'];
    if (g['06'] != null && g['09'] != null) sq[y + '-09'] = g['09'] - g['06'];
    if (g['09'] != null && g['12'] != null) sq[y + '-12'] = g['12'] - g['09'];
  });
  return sq;
}

// 近90日研报覆盖数
async function getResearchCount(code) {
  const end = new Date(), begin = new Date(Date.now() - 90 * 864e5);
  const fmt = d => d.toISOString().slice(0, 10);
  const url = `https://reportapi.eastmoney.com/report/list?pageSize=1&pageNo=1&qType=0&code=${code}&beginTime=${fmt(begin)}&endTime=${fmt(end)}`;
  try { const j = await fetchJson(url, 'https://data.eastmoney.com/'); return (j.hits != null) ? j.hits : null; }
  catch (e) { return null; }
}

// PE/PB（估值接口，best-effort；失败为 null，不影响采集主流程）
async function getValuation(sec) {
  try {
    const url = `https://datacenter.eastmoney.com/securities/api/data/v1/get?reportName=RPT_VALUEANALYSIS_DET&columns=SECUCODE,SECURITY_CODE,PE_TTM,PB&filter=${encodeURIComponent(`(SECUCODE="${sec}")`)}&pageNumber=1&pageSize=1&sortTypes=-1&sortColumns=SECUCODE&source=HSF10&client=PC`;
    const j = await fetchJson(url, 'https://emweb.securities.eastmoney.com/');
    const d = (j.result && j.result.data && j.result.data[0]) || null;
    if (!d) return { pe: null, pb: null };
    return {
      pe: (d.PE_TTM != null && isFinite(+d.PE_TTM)) ? +d.PE_TTM : null,
      pb: (d.PB != null && isFinite(+d.PB)) ? +d.PB : null,
    };
  } catch (e) { return { pe: null, pb: null }; }
}

const YI = 1e8;
async function collect(code, opts = {}) {
  const sec = secucode(code);
  const rows = await getFin(sec);
  if (!rows.length) return { code, error: 'no_fin_data' };
  const sq = singleQuarters(rows);
  const keys = Object.keys(sq).sort();
  let npTtm = null, npTtmYoY = null;
  if (keys.length >= 4) npTtm = keys.slice(-4).reduce((a, k) => a + sq[k], 0);
  if (keys.length >= 8) {
    const prev = keys.slice(-8, -4).reduce((a, k) => a + sq[k], 0);
    if (prev !== 0 && npTtm != null) npTtmYoY = (npTtm - prev) / Math.abs(prev) * 100;
  }
  const latest = rows[0];
  const annual = rows.find(r => r.REPORT_TYPE === '年报');
  const revGrowth = latest.TOTALOPERATEREVETZ, npGrowth = latest.PARENTNETPROFITTZ;
  let researchCount90d = null;
  if (opts.skipG6 !== true) { await new Promise(r => setTimeout(r, 200)); researchCount90d = await getResearchCount(code); }
  let pe = null, pb = null;
  if (opts.skipVal !== true) { await new Promise(r => setTimeout(r, 200)); const v = await getValuation(sec); pe = v.pe; pb = v.pb; }
  const npTtmYi = npTtm != null ? +(npTtm / YI).toFixed(3) : null;
  const g5Quality = (npTtm != null && npTtm > 0) && ((npTtmYoY != null && npTtmYoY > 0) || (revGrowth != null && revGrowth > 0));
  return {
    code, sec, source: 'eastmoney-f10', fetchedAt: new Date().toISOString().slice(0, 10),
    latestReport: latest.REPORT_DATE.slice(0, 10), reportType: latest.REPORT_TYPE,
    npTtm: npTtmYi, npTtmYoY: npTtmYoY != null ? +npTtmYoY.toFixed(1) : null,
    revGrowth: revGrowth != null ? +revGrowth.toFixed(1) : null,
    npGrowth: npGrowth != null ? +npGrowth.toFixed(1) : null,
    annualNp: annual && annual.PARENTNETPROFIT != null ? +(annual.PARENTNETPROFIT / YI).toFixed(3) : null,
    researchCount90d, pe, pb,
    g5Quality, g6Covered: researchCount90d != null ? researchCount90d > 0 : null,
  };
}

// 边车读写
function loadSidecar(fundFile) {
  if (!fs.existsSync(fundFile)) return {};
  try { return JSON.parse(fs.readFileSync(fundFile, 'utf8')).items || {}; } catch (e) { return {}; }
}
function saveSidecar(fundFile, store) {
  const BAK = fundFile + '.bak';
  if (fs.existsSync(fundFile)) fs.writeFileSync(BAK, fs.readFileSync(fundFile));
  fs.writeFileSync(fundFile, JSON.stringify({ updated: new Date().toISOString().slice(0, 10), source: 'eastmoney-f10', items: store }, null, 2), 'utf8');
}

// 构建 / 增量刷新基本面边车
async function buildFundamentals(opts = {}) {
  const SRC = opts.src || 'D:/WorkBuddy/选股结果/import_final.json';
  const OUT = opts.out || 'D:/WorkBuddy/选股结果/fundamental.json';
  const CODES_FILE = opts.codesFile || '';
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  const data = JSON.parse(fs.readFileSync(SRC, 'utf8'));
  const items = (data.items || []).filter(s => ['cyb', 'kcb', 'kc'].includes(s.board));
  const nameOf = {}; (data.items || []).forEach(s => nameOf[s.code] = s.name);
  let codes;
  if (CODES_FILE) codes = JSON.parse(fs.readFileSync(CODES_FILE, 'utf8'));
  else if (opts.codes) codes = opts.codes;
  else codes = items.map(s => s.code);

  const store = loadSidecar(OUT);
  Logger.info('FUND', `采集 ${codes.length} 支 → 边车 ${OUT}`);
  const rows = [];
  for (const code of codes) {
    try {
      const f = await collect(code, { skipG6: opts.skipG6 === true, skipVal: opts.skipVal === true });
      store[code] = f; rows.push(f);
      if (f.error) Logger.warn('FUND', `${code} ${nameOf[code] || ''} | 采集失败: ${f.error}`);
      else Logger.info('FUND', `${code} ${nameOf[code] || ''} | NP_TTM=${f.npTtm}亿 TTM同比=${f.npTtmYoY}% 营收同比=${f.revGrowth}% PE=${f.pe} PB=${f.pb} 研报=${f.researchCount90d} | G5=${f.g5Quality ? '✅' : '❌'}`);
    } catch (e) {
      Logger.error('FUND', `${code} ${nameOf[code] || ''} | 异常: ${e.message}`);
      rows.push({ code, error: e.message });
    }
    await sleep(300);
  }
  saveSidecar(OUT, store);
  const ok = rows.filter(r => !r.error), pass = ok.filter(r => r.g5Quality);
  Logger.info('FUND', `完成: 成功 ${ok.length}/${codes.length}，G5达标 ${pass.length}/${ok.length} → ${OUT}`);
  return store;
}

module.exports = { secucode, getFin, singleQuarters, getResearchCount, getValuation, collect, loadSidecar, saveSidecar, buildFundamentals };
