// expand_universe.js — 双创升级 4.3：扩候选池到全市场双创
// 枚举全部创业板(30xxxx)/科创板(688xxx)，拉取 2023-08-28~2026-06-30 前复权日K，
// 写入 选股结果/universe_klines.json（格式与 import_final.kline.day 一致 [date,open,close,high,low,vol]）。
//
// 数据源：东方财富公开接口（push2his kline 可用；datacenter 选股器枚举——push2 clist 被封）。
// 并发 8 + 断点缓存（每 40 支落盘），可中断重跑（已抓的跳过）。
// 剔除：ST/*ST/退市（涨跌幅限制与退市风险不适合本策略）；历史 <60 根（无法算 MA60/ATR）。
// 运行：node expand_universe.js

const fs = require('fs');
const OUT = 'D:/WorkBuddy/选股结果/universe_klines.json';
const BEG = '20230828', END = '20260630';
// 数据源：腾讯 ifzq K线（web.ifzq.gtimg.cn）——东财 push2his 初次并发突发后 IP 被临时限制，
//   改走腾讯（qt.gtimg.cn 同域，资金动态页长期可用）。并发 5 + 批次延时 + 抖动退避。
const CONC = 5, CKPT = 40, BATCH_GAP = 200;
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

// 1) 枚举全市场双创（选股器分页，本地按代码前缀过滤）
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
      if (/ST|退/.test(nm)) return;                       // 剔除 ST/退市
      if (c.startsWith('30')) out.push({ code: c, name: nm, board: 'cyb' });
      else if (c.startsWith('688')) out.push({ code: c, name: nm, board: 'kcb' });
    });
    if (!j.result.nextpage) break;
    page++;
    if (page > 20) break;                                 // 安全上限
    await sleep(120);
  }
  return out;
}

// 2) 拉单支日K（腾讯 ifzq，前复权）→ [[YYYYMMDD,open,close,high,low,vol],...]；失败返回 null 便于续跑补抓
async function fetchKline(code) {
  const tc = (/^6/.test(code) ? 'sh' : 'sz') + code;
  const url = `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${tc},day,2023-08-28,2026-06-30,800,qfq`;
  const j = await fetchJson(url, 'https://gu.qq.com/');
  const d = j && j.data && j.data[tc];
  const ks = d && (d.qfqday || d.day);
  if (!Array.isArray(ks) || !ks.length) return null;   // 失败/无效 → null
  const day = [];
  for (const p of ks) {
    if (p.length < 6) continue;
    day.push([p[0].replace(/-/g, ''), +p[1], +p[2], +p[3], +p[4], +p[5]]);
  }
  return day;
}

(async () => {
  console.log('=== 4.3 扩池：枚举全市场双创 ===');
  const list = await enumerateChuang();
  console.log(`枚举到 创业板 ${list.filter(x => x.board === 'cyb').length} + 科创板 ${list.filter(x => x.board === 'kcb').length} = ${list.length} 支`);

  // 断点缓存
  let store = {};
  if (fs.existsSync(OUT)) { try { (JSON.parse(fs.readFileSync(OUT, 'utf8')).items || []).forEach(s => store[s.code] = s); } catch (e) { } }
  const todo = list.filter(x => !store[x.code]);
  console.log(`已缓存 ${Object.keys(store).length}，待抓 ${todo.length} 支（并发${CONC}）`);

  let done = 0, ok = 0, skipShort = 0, fail = 0;
  for (let i = 0; i < todo.length; i += CONC) {
    const batch = todo.slice(i, i + CONC);
    await Promise.all(batch.map(async x => {
      const day = await fetchKline(x.code);
      if (day === null) fail++;                     // 抓取失败：不缓存，下次重跑补
      else if (day.length >= 60) { store[x.code] = { code: x.code, name: x.name, board: x.board, kline: { day } }; ok++; }
      else skipShort++;                              // 真实历史过短（<60根）
    }));
    done += batch.length;
    if (done % CKPT < CONC || done >= todo.length) {
      fs.writeFileSync(OUT, JSON.stringify({ updated: new Date().toISOString().slice(0, 10), period: [BEG, END], items: Object.values(store) }), 'utf8');
      console.log(`  进度 ${done}/${todo.length} | 有效 ${ok} | 历史过短 ${skipShort} | 失败待补 ${fail} | 缓存累计 ${Object.keys(store).length}`);
    }
    await sleep(BATCH_GAP);
  }
  if (fail > 0) console.log(`⚠️ ${fail} 支抓取失败（网络/反爬），重跑 node expand_universe.js 可断点续补`);
  const items = Object.values(store);
  const cyb = items.filter(s => s.board === 'cyb').length, kcb = items.filter(s => s.board === 'kcb').length;
  console.log(`\n完成：universe ${items.length} 支（创业板 ${cyb} + 科创板 ${kcb}）→ ${OUT}`);
})();
