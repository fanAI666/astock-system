// extend_fundamental.js — 双创升级 4.0 数据补采集
// 为 G5(盈利质量)/G6(机构认同) 采集双创基本面数据，写入【边车文件】选股结果/fundamental.json。
//
// 为什么用边车而不是写进 import_final.json：
//   build_final.py 每个交易日【从零重建】import_final.json（不读旧文件），任何写入其中的
//   额外字段都会在次日 16:00 自动化被抹掉。边车文件 build_final 完全不碰，天然规避每日覆盖，
//   且无需改动 build_final.py / extend_history.js，兼容性最优。G5/G6 门后续从本文件读取。
//
// 数据源：东方财富公开 F10 接口（Node 直接 HTTP，无需 tdx/westock 连接器——当前二者均断开）。
//   - 财务主指标: datacenter.eastmoney.com RPT_F10_FINANCE_MAINFINADATA（累计值，需拆单季算 TTM）
//   - 研报覆盖数: reportapi.eastmoney.com report/list（近90日 hits 计数）
//
// 运行：node extend_fundamental.js            （采集 import_final 中全部 board∈{cyb,kcb,kc}）
//      node extend_fundamental.js 301520 688621 （只采集指定代码，便于增量刷新）
// 幂等可重跑：读取既有 fundamental.json，仅更新本次采集的 code，保留其余；写前备份 .bak。

const fs = require('fs');
const SRC = 'D:/WorkBuddy/选股结果/import_final.json';
const OUT = 'D:/WorkBuddy/选股结果/fundamental.json';
const BAK = 'D:/WorkBuddy/选股结果/fundamental.bak';
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// A股代码 → 东方财富 SECUCODE：6 开头(含 688 科创)→.SH，0/3 开头→.SZ
function secucode(code) { return /^6/.test(code) ? code + '.SH' : code + '.SZ'; }

async function fetchJson(url, referer) {
  const r = await fetch(url, { headers: { 'Referer': referer, 'User-Agent': 'Mozilla/5.0' } });
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}

// 拉最近 16 期财务主指标（累计值）
async function getFin(sec) {
  const cols = 'SECUCODE,REPORT_DATE,REPORT_TYPE,TOTALOPERATEREVE,PARENTNETPROFIT,PARENTNETPROFITTZ,TOTALOPERATEREVETZ';
  const url = `https://datacenter.eastmoney.com/securities/api/data/v1/get?reportName=RPT_F10_FINANCE_MAINFINADATA&columns=${encodeURIComponent(cols)}&filter=${encodeURIComponent(`(SECUCODE="${sec}")`)}&pageNumber=1&pageSize=16&sortTypes=-1&sortColumns=REPORT_DATE&source=HSF10&client=PC`;
  const j = await fetchJson(url, 'https://emweb.securities.eastmoney.com/');
  return (j.result && j.result.data) || [];
}

// 把累计(YTD)净利润拆成单季序列 { 'YYYY-MM': 单季NP }
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

const YI = 1e8;
async function collect(code) {
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
  await sleep(200);
  const researchCount90d = await getResearchCount(code);
  const npTtmYi = npTtm != null ? +(npTtm / YI).toFixed(3) : null;
  const g5Quality = (npTtm != null && npTtm > 0) && ((npTtmYoY != null && npTtmYoY > 0) || (revGrowth != null && revGrowth > 0));
  return {
    code, sec, source: 'eastmoney-f10', fetchedAt: new Date().toISOString().slice(0, 10),
    latestReport: latest.REPORT_DATE.slice(0, 10), reportType: latest.REPORT_TYPE,
    npTtm: npTtmYi,                                     // 归母净利润TTM（亿元）
    npTtmYoY: npTtmYoY != null ? +npTtmYoY.toFixed(1) : null, // TTM同比（%）
    revGrowth: revGrowth != null ? +revGrowth.toFixed(1) : null, // 最新期营收同比（%）
    npGrowth: npGrowth != null ? +npGrowth.toFixed(1) : null,   // 最新期净利同比（%）
    annualNp: annual && annual.PARENTNETPROFIT != null ? +(annual.PARENTNETPROFIT / YI).toFixed(3) : null, // 最新年报归母净利（亿）
    researchCount90d,                                   // G6 近90日研报覆盖数
    g5Quality,                                          // G5 硬门槛：TTM>0 且（TTM同比>0 或 营收同比>0）
    g6Covered: researchCount90d != null ? researchCount90d > 0 : null  // G6 加分项
  };
}

(async () => {
  const arg = process.argv.slice(2);
  const data = JSON.parse(fs.readFileSync(SRC, 'utf8'));
  const items = (data.items || []).filter(s => ['cyb', 'kcb', 'kc'].includes(s.board));
  let codes = arg.length ? arg : items.map(s => s.code);
  const nameOf = {}; items.forEach(s => nameOf[s.code] = s.name);

  // 读取既有边车，便于增量合并
  let store = {};
  if (fs.existsSync(OUT)) { try { store = JSON.parse(fs.readFileSync(OUT, 'utf8')).items || {}; } catch (e) { } }
  if (fs.existsSync(OUT)) fs.writeFileSync(BAK, fs.readFileSync(OUT)); // 写前备份

  console.log(`=== 4.0 双创基本面采集（${codes.length} 支）→ 边车 fundamental.json ===`);
  const rows = [];
  for (const code of codes) {
    try {
      const f = await collect(code);
      store[code] = f;
      rows.push(f);
      console.log(`${code} ${nameOf[code] || ''} | NP_TTM=${f.npTtm}亿 TTM同比=${f.npTtmYoY}% 营收同比=${f.revGrowth}% 研报=${f.researchCount90d} | G5=${f.g5Quality ? '✅' : '❌'}`);
    } catch (e) {
      console.log(`${code} ${nameOf[code] || ''} | 采集失败: ${e.message}`);
      rows.push({ code, error: e.message });
    }
    await sleep(300); // 限速
  }
  fs.writeFileSync(OUT, JSON.stringify({ updated: new Date().toISOString().slice(0, 10), source: 'eastmoney-f10', items: store }, null, 2), 'utf8');
  const ok = rows.filter(r => !r.error), pass = ok.filter(r => r.g5Quality);
  console.log(`\n完成: 成功 ${ok.length}/${codes.length}，G5达标 ${pass.length}/${ok.length} → ${OUT}`);
})();
