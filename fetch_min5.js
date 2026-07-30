#!/usr/bin/env node
/**
 * fetch_min5.js — 刷新「五日分时」数据 (kline.min5)
 *
 * 背景：腾讯自选股 westock 连接器 data_kline 仅支持 day/week/month，不含分钟级，
 * 故五日分时(min5)无法经 westock 刷新。本脚本改用腾讯官方代理行情接口
 *   proxy.finance.qq.com/ifzqgtimg/appstock/app/minute/query?code=<市场前缀+代码>&day=YYYY-MM-DD
 * 拉取最近 N 个交易日的 1 分钟分时，聚合为 5 分钟 OHLC，写回
 * import_final.json 中每只股票的 kline.min5，供前端 ts5(五日分时)/ts1(当日分时) 渲染。
 *
 * min5 单根格式（与 stock-selection-system.html prepData 完全一致）：
 *   [ "YYYYMMDD HHMM", open, close, high, low, vol(手) ]
 *
 * 容错原则：
 *  - 某股票某交易日拉取失败 / 返回空 → 跳过该日，不编造数据
 *  - 某股票全部交易日都失败 → 保留其原有 min5（不清空，避免数据丢失）
 *  - 网络层异常 → 记录并继续，整体不中断
 *
 * 用法：
 *   node fetch_min5.js [importFinalPath] [days] [--out=path]
 *   默认 importFinalPath = 选股结果/import_final.json，days = 5
 */
'use strict';

const fs = require('fs');
const path = require('path');

// ---------- 参数 ----------
const argv = process.argv.slice(2);
let importPath = 'D:/WorkBuddy/选股结果/import_final.json';
let days = 5;
let outPath = null;
for (const a of argv) {
  if (a.startsWith('--out=')) outPath = a.slice('--out='.length);
  else if (/^\d+$/.test(a)) days = parseInt(a, 10);
  else if (a && !a.startsWith('--')) importPath = a;
}
if (!outPath) outPath = importPath;

const PROXY = 'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/minute/query';
const CONCURRENCY = 5;       // 并发请求数
const REQ_TIMEOUT = 9000;    // 单请求超时(ms)
const RETRIES = 1;           // 失败重试次数

// ---------- 工具 ----------
function marketPrefix(code) {
  const c = String(code).trim();
  const lead = c[0];
  return (lead === '6' || lead === '9') ? 'sh' : 'sz';
}
function ymdToCompact(ymd) { // "2026-07-28" -> "20260728"
  return ymd.replace(/-/g, '');
}
function pad2(n) { return n < 10 ? '0' + n : '' + n; }

// 生成候选交易日（从今天往回 lookback 个日历日，仅工作日），返回 YYYY-MM-DD 数组（新->旧）
function candidateTradingDates(n, lookback) {
  const out = [];
  const today = new Date();
  for (let i = 0; i < lookback && out.length < n; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const dow = d.getDay();
    if (dow === 0 || dow === 6) continue; // 跳过周末
    out.push(d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()));
  }
  return out; // 新->旧
}

// 单日 1 分钟分时 -> 5 分钟 OHLC 聚合
// points: 数组，每项字符串 "HHMM price cumVol cumAmt"
// dateCompact: "20260728"
function aggregateDay(points, dateCompact) {
  const bars = [];
  let prevCum = 0;          // 当日累计量（每根5分钟bar量 = 末尾累计 - 上一根末尾累计）
  let cur = null;
  let bi = -1;
  for (let i = 0; i < points.length; i++) {
    const parts = String(points[i]).trim().split(/\s+/);
    if (parts.length < 3) continue;
    const hhmm = parts[0];
    const price = parseFloat(parts[1]);
    const cumVol = parseFloat(parts[2]);
    if (!hhmm || isNaN(price) || isNaN(cumVol)) continue;

    const bucket = Math.floor(i / 5); // 按数组下标分桶，天然跨午休不串桶
    if (cur === null || bucket !== bi) {
      if (cur) {
        cur.vol = Math.max(0, cur.cumEnd - prevCum);
        bars.push(cur);
        prevCum = cur.cumEnd;
      }
      bi = bucket;
      cur = {
        t: dateCompact + ' ' + hhmm,
        open: price, high: price, low: price, close: price,
        cumEnd: cumVol
      };
    } else {
      if (price > cur.high) cur.high = price;
      if (price < cur.low) cur.low = price;
      cur.close = price;
      cur.cumEnd = cumVol;
    }
  }
  if (cur) {
    cur.vol = Math.max(0, cur.cumEnd - prevCum);
    bars.push(cur);
  }
  // 转成紧凑数组格式
  return bars.map(b => [b.t, b.open, b.close, b.high, b.low, b.vol]);
}

async function fetchOneDay(code, ymd) {
  const url = `${PROXY}?code=${code}&day=${ymd}`;
  for (let attempt = 0; attempt <= RETRIES; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), REQ_TIMEOUT);
    try {
      const r = await fetch(url, {
        headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://gu.qq.com/' },
        signal: ctrl.signal
      });
      clearTimeout(timer);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      const node = j && j.data && j.data[code] && j.data[code].data;
      const arr = node && node.data;
      if (!Array.isArray(arr) || arr.length === 0) return null; // 非交易日/空
      return aggregateDay(arr, ymdToCompact(ymd));
    } catch (e) {
      clearTimeout(timer);
      if (attempt === RETRIES) return { error: e.message };
      await new Promise(r => setTimeout(r, 300));
    }
  }
  return null;
}

// 并发池执行
async function pool(items, worker, conc) {
  const out = new Array(items.length);
  let idx = 0;
  async function run() {
    while (idx < items.length) {
      const my = idx++;
      out[my] = await worker(items[my], my);
    }
  }
  const ps = [];
  for (let i = 0; i < conc; i++) ps.push(run());
  await Promise.all(ps);
  return out;
}

// ---------- 主流程 ----------
async function main() {
  console.log(`[fetch_min5] 读取 ${importPath}`);
  const raw = fs.readFileSync(importPath, 'utf8');
  const data = JSON.parse(raw);
  const items = Array.isArray(data) ? data : (data.items || []);
  if (!items.length) { console.log('[fetch_min5] 无候选股，退出'); return; }

  const dates = candidateTradingDates(days, Math.max(12, days * 3 + 4));
  console.log(`[fetch_min5] 候选交易日(${dates.length}): ${dates.join(', ')}`);

  let okStocks = 0, skipStocks = 0, totalBars = 0, dayHits = 0;
  const perDayCount = {};

  for (const stock of items) {
    const code = stock.code;
    if (!code) { skipStocks++; continue; }
    const full = marketPrefix(code) + code;

    // 为单只股票并发拉取各交易日
    const results = await pool(dates, (ymd) => fetchOneDay(full, ymd), CONCURRENCY);

    const dayBars = [];
    let gotAny = false;
    results.forEach((res, k) => {
      if (res && !res.error && res.length) {
        gotAny = true;
        perDayCount[dates[k]] = (perDayCount[dates[k]] || 0) + 1;
        dayHits++;
        for (const b of res) dayBars.push(b);
      }
    });

    if (!gotAny) {
      // 全部失败：保留原有 min5，不清空
      skipStocks++;
      continue;
    }

    // 按日期+时间升序（旧->新），保证 ts5 跨日连续
    dayBars.sort((a, b) => a[0] < b[0] ? -1 : (a[0] > b[0] ? 1 : 0));

    if (!stock.kline || typeof stock.kline !== 'object') stock.kline = {};
    stock.kline.min5 = dayBars;
    stock.kline.min5UpdatedAt = new Date().toISOString().slice(0, 10);
    okStocks++;
    totalBars += dayBars.length;
  }

  // 写回（先备份）
  const bak = outPath + '.min5bak';
  fs.writeFileSync(bak, raw, 'utf8');
  fs.writeFileSync(outPath, JSON.stringify(data, null, 2), 'utf8');

  console.log(`[fetch_min5] 完成: 成功 ${okStocks} 只 / 跳过(无数据) ${skipStocks} 只 / 总K线 ${totalBars} 根`);
  console.log(`[fetch_min5] 各交易日命中股票数: ${Object.entries(perDayCount).map(([d, c]) => d + '=' + c).join(', ')}`);
  console.log(`[fetch_min5] 备份: ${bak}`);
}

main().then(() => process.exit(0)).catch(e => {
  console.error('[fetch_min5] FATAL', e);
  process.exit(1);
});
