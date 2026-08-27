'use strict';
// chuang/sanqizhou.js — 「三周期」选股分析报告生成器
// 职责：读取 选股结果/universe_klines.json（双创 1270 支日K），本地把日K重采样为周/月，
//       用 MA 斜率 + 价格相对 MA 位置判定 月/周/日 三周期趋势(up/down/flat)，
//       按「日线转强且非双长周期空头」选股，综合评分后排前 N 名，
//       产出 选股结果/sanqizhou_report.json（与 stock-selection-system.html 的 renderSanZhou 严格对齐）。
// 数据刷新：默认尝试探测腾讯 ifzq 端点，若通则刷新每支最近 ~40 根日K（合并到本地快照）；
//           网络不可达时自动回退到本地 universe_klines.json 快照，保证每日仍能产出报告。
// 注意：仅生成「多周期共振研究参考」报告，非实盘建议；不真实下单。

const fs = require('fs');
const path = require('path');

const ROOT = 'D:/WorkBuddy';
const UNI = path.join(ROOT, '选股结果/universe_klines.json');
const OUT = path.join(ROOT, '选股结果/sanqizhou_report.json');

const DO_REFRESH = process.env.SANQIZHOU_REFRESH !== '0';
const CONC = 6;          // 刷新并发
const TOP_N = 20;        // 报告最多输出（精选展示）标的数
const MAX_CANDIDATES = 300;  // 候选股池硬上限：优中选优前先把候选股收敛到 300 以内

// ===== 工具：MA / 重采样 / 趋势 =====
function sma(arr, n) {
  const out = new Array(arr.length).fill(NaN);
  let s = 0;
  for (let i = 0; i < arr.length; i++) {
    s += arr[i];
    if (i >= n) s -= arr[i - n];
    if (i >= n - 1) out[i] = s / n;
  }
  return out;
}

function isoWeekKey(dt) {
  const d = new Date(Date.UTC(dt.getUTCFullYear(), dt.getUTCMonth(), dt.getUTCDate()));
  const dayNum = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - dayNum + 3);
  const firstThu = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
  const week = 1 + Math.round(((d - firstThu) / 86400000 - 3 + ((firstThu.getUTCDay() + 6) % 7)) / 7);
  return d.getUTCFullYear() + '-W' + String(week).padStart(2, '0');
}

function resampleWeek(days) {
  const map = {};
  for (const d of days) {
    const ds = String(d[0]);
    const dt = new Date(+ds.slice(0, 4), +ds.slice(4, 6) - 1, +ds.slice(6, 8));
    const k = isoWeekKey(dt);
    if (!map[k]) map[k] = { date: ds, o: +d[1], c: +d[2], h: +d[3], l: +d[4], v: +d[5] };
    else { const m = map[k]; m.c = +d[2]; m.h = Math.max(m.h, +d[3]); m.l = Math.min(m.l, +d[4]); m.v += +d[5]; m.date = ds; }
  }
  return Object.values(map).sort((a, b) => a.date < b.date ? -1 : 1).map(m => [m.date, m.o, m.c, m.h, m.l, m.v]);
}

function resampleMonth(days) {
  const map = {};
  for (const d of days) {
    const ds = String(d[0]); const mk = ds.slice(0, 6);
    if (!map[mk]) map[mk] = { date: ds, o: +d[1], c: +d[2], h: +d[3], l: +d[4], v: +d[5] };
    else { const m = map[mk]; m.c = +d[2]; m.h = Math.max(m.h, +d[3]); m.l = Math.min(m.l, +d[4]); m.v += +d[5]; m.date = ds; }
  }
  return Object.values(map).sort((a, b) => a.date < b.date ? -1 : 1).map(m => [m.date, m.o, m.c, m.h, m.l, m.v]);
}

function closesOf(bars) { return bars.map(b => +b[2]); }

function trend(bars, maN) {
  const c = closesOf(bars);
  const n = c.length;
  if (n < maN + 2) return 'flat';
  const ma = sma(c, maN);
  const maNow = ma[n - 1], maPrev = ma[n - 2];
  if (isNaN(maNow) || isNaN(maPrev)) return 'flat';
  const close = c[n - 1];
  const slope = maPrev > 0 ? (maNow - maPrev) / maPrev : 0;
  if (close > maNow && slope > 0.0008) return 'up';
  if (close < maNow && slope < -0.0008) return 'down';
  return 'flat';
}

function trendOf(day) {
  const week = resampleWeek(day), month = resampleMonth(day);
  const c = closesOf(day);
  const L = c.length;
  const ret5 = L > 5 ? c[L - 1] / c[L - 6] - 1 : 0;
  const v5 = day.slice(-5).reduce((s, b) => s + +b[5], 0);
  const v10 = day.slice(-10).reduce((s, b) => s + +b[5], 0) / 2;
  return {
    day: trend(day, 20),
    week: trend(week, 20),
    month: trend(month, 12),
    lastClose: +day[day.length - 1][2],
    low10: Math.min(...day.slice(-10).map(b => +b[4])),
    ret5,
    vol5: v10 > 0 ? v5 / v10 : 1,
  };
}

// ===== 评分 / 理由 / 选股 =====
function scoreOf(t) {
  let s = 0;
  s += t.month === 'up' ? 28 : t.month === 'flat' ? 8 : 0;
  s += t.week === 'up' ? 24 : t.week === 'flat' ? 8 : 0;
  s += t.day === 'up' ? 20 : t.day === 'flat' ? 6 : 0;
  const ups = [t.month, t.week, t.day].filter(x => x === 'up').length;
  s += ups === 3 ? 15 : ups === 2 ? 6 : 0;
  if (t.ret5 > 0) s += Math.min(8, Math.round(t.ret5 * 100 * 1.5));
  return Math.max(0, Math.min(100, s));
}

function reasonsOf(t) {
  const r = [];
  r.push(t.month === 'up' ? '月线站上MA12、多头排列' : t.month === 'flat' ? '月线横盘整理' : '月线空头排列');
  r.push(t.week === 'up' ? '周线MA20上行' : t.week === 'flat' ? '周线横向盘整' : '周线走弱');
  r.push(t.day === 'up' ? (t.vol5 > 1.1 ? '日线放量站上MA20、短线转强' : '日线站上MA20、短线转强') : t.day === 'flat' ? '日线中性' : '日线偏弱');
  const ups = [t.month, t.week, t.day].filter(x => x === 'up').length;
  if (ups === 3) r.push('三周期共振，趋势最强');
  else if (ups === 2) r.push('短中期共振，长周期待确认');
  else if (t.day === 'up') r.push('仅日线转强，逆长周期需谨慎');
  if (t.ret5 > 0.03) r.push('近5日涨幅 ' + (t.ret5 * 100).toFixed(1) + '%');
  return r;
}

// ===== 分析报告（文字叙述，供前端独立展示）=====
function buildAnalysis(all, out, mu, wu, du, resonance, partial, diverge, total, candidates) {
  const pct = x => (x * 100).toFixed(0);
  const tot = Math.max(total, 1);

  // —— 市场三周期叙述 ——
  let market = '';
  if (mu >= 0.4) market += `月线多头占比 ${pct(mu)}%，中期趋势整体向上，处于中期多头区间；`;
  else if (mu >= 0.2) market += `月线多头占比 ${pct(mu)}%，中期多空大致平衡，趋势尚未明确；`;
  else market += `月线多头占比仅 ${pct(mu)}%，中期仍偏空，绝大多数标的处于月线调整；`;

  if (wu >= 0.4) market += `周线多头 ${pct(wu)}%，中期次级趋势同步走强；`;
  else if (wu >= 0.2) market += `周线多头 ${pct(wu)}%，周线处于蓄势 / 整理；`;
  else market += `周线多头仅 ${pct(wu)}%，周线仍在回调，中期整理未结束；`;

  if (du >= 0.4) market += `日线多头 ${pct(du)}%，短线资金活跃、个股普遍转强，具备交易性机会。`;
  else if (du >= 0.2) market += `日线多头 ${pct(du)}%，短线分化，仅少数个股转强。`;
  else market += `日线多头仅 ${pct(du)}%，短线疲弱，缺乏普遍交易机会。`;

  if (resonance > 0) market += ` 候选股池 ${candidates} 支（已收敛至 300 以内），优中选优筛选出 ${total} 支达标标的，其中 ${resonance} 支为月 / 周 / 日三周期共振（趋势最强），占候选池 ${pct(resonance / Math.max(candidates, 1))}%，处于主升结构。`;
  if (diverge > 0) market += ` 另有 ${diverge} 支属周期背离（日线转强但长周期仍空），属逆势反弹性质，需严格止损。`;

  // —— 关键观察 ——
  const keyPoints = [];
  const byBoard = {};
  out.forEach(x => { byBoard[x.board] = (byBoard[x.board] || 0) + 1; });
  const boardTxt = Object.keys(byBoard).map(b => {
    const name = b === 'kcb' ? '科创板' : (b === 'cyb' ? '创业板' : '主板');
    return name + byBoard[b] + '支';
  }).join('、');
  if (boardTxt) keyPoints.push(`达标标的板块分布：${boardTxt}。`);

  if (resonance >= 5) keyPoints.push(`三周期共振标的达 ${resonance} 支，数量较多，说明多周期同向个股具备赚钱效应，可适度参与。`);
  else if (resonance > 0) keyPoints.push(`三周期共振标的 ${resonance} 支，数量有限，宜精选其中评分最高者跟踪。`);
  else keyPoints.push(`当前无三周期共振标的，市场以日线级别反弹为主，趋势性机会稀缺。`);

  if (diverge > 0) keyPoints.push(`${diverge} 支标的日线转强但长周期（月 / 周）仍空，属逆势反弹，务必按 3:1 风险回报设止损，破位即离。`);

  if (du - mu > 0.15) keyPoints.push(`日线多头占比(${pct(du)}%)明显高于月线(${pct(mu)}%)，呈「短强长弱」结构，当前更可能是反弹而非反转，仓位宜轻。`);
  else if (mu - du > 0.15) keyPoints.push(`月线多头占比(${pct(mu)}%)高于日线(${pct(du)}%)，长周期已转强、短线在消化，属健康的回踩确认，回调可视为机会。`);

  // —— 策略建议 ——
  let strategy = '';
  if (resonance >= 5 && du >= 0.4) strategy = '三周期共振标的较多且日线活跃，可适度参与短线，优先选择评分≥80、月周共振的标的，按 3:1 风险回报设止损止盈。';
  else if (resonance > 0) strategy = '共振标的有限，以「精选 + 轻仓」为主，仅跟踪评分最高的 1–2 支，等待回踩确认后再介入。';
  else strategy = '缺乏三周期共振，趋势性机会稀缺，建议以观望或极小仓位试错为主，不追高。';
  strategy += ' 所有标的均须严格执行单笔止损纪律（主板 2% 止损 / 6% 止盈、双创 ATR 动态止损），破位即离场。';

  const method = '选股逻辑：以双创（创业板 / 科创板）1270 支为样本，本地把日 K 重采样为周 / 月，用 MA 斜率 + 收盘价相对 MA 位置判定月 / 周 / 日三周期趋势（↑多 / ↓空 / →平）。筛选条件：日线转强（↑）且非「月空 & 周空」双长周期空头；综合评分（长周期权重更高 + 三周期齐多加分 + 近 5 日动量）降序排列。优中选优两层：① 先按评分取候选股池前 300 支（候选股池上限 300，避免市况好时膨胀）；② 再从候选池中精选评分最高的 20 支展示。入场价取最新收盘价，止损价取近 10 日低或 −5%，目标价 = 入场 + (入场 − 止损) × 3（3:1 风险回报）。';

  const risk = '⚠️ 本报告由程序基于历史 K 线自动生成，仅用于多周期共振策略研究参考，不构成任何实盘买卖建议。多周期共振可提升胜率但并非 100%，市场存在黑天鹅与流动性风险，请独立决策、自负盈亏。';

  return {
    market,
    keyPoints,
    strategy,
    method,
    risk,
    cycleCounts: { monthUp: pct(mu), weekUp: pct(wu), dayUp: pct(du) },
  };
}

// ===== 可选：网络刷新最近日K =====
async function fetchRecent(code) {
  const tc = (/^6/.test(code) ? 'sh' : 'sz') + code;
  const end = new Date();
  const beg = new Date(); beg.setDate(beg.getDate() - 40);
  const p = x => x.toISOString().slice(0, 10);
  const url = `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${tc},day,${p(beg)},${p(end)},60,qfq`;
  const ctrl = new AbortController(); const to = setTimeout(() => ctrl.abort(), 7000);
  try {
    const r = await fetch(url, { signal: ctrl.signal, headers: { 'Referer': 'https://gu.qq.com/', 'User-Agent': 'Mozilla/5.0' } });
    if (!r.ok) return null;
    const j = await r.json();
    const d = j && j.data && j.data[tc];
    const ks = d && (d.qfqday || d.day);
    if (!Array.isArray(ks) || !ks.length) return null;
    return ks.map(x => [String(x[0]).replace(/-/g, ''), +x[1], +x[2], +x[3], +x[4], +x[5]]);
  } catch (e) { return null; }
  finally { clearTimeout(to); }
}

async function probe() {
  try {
    const ctrl = new AbortController(); const to = setTimeout(() => ctrl.abort(), 6000);
    const r = await fetch('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600000,day,2026-08-20,2026-08-25,5,qfq',
      { signal: ctrl.signal, headers: { 'Referer': 'https://gu.qq.com/', 'User-Agent': 'Mozilla/5.0' } });
    clearTimeout(to);
    return r.ok;
  } catch (e) { return false; }
}

function mergeDay(oldDay, fresh) {
  if (!fresh || !fresh.length) return oldDay;
  const m = {};
  oldDay.forEach(b => m[String(b[0])] = b);
  fresh.forEach(b => m[String(b[0])] = b);
  return Object.values(m).sort((a, b) => String(a[0]) < String(b[0]) ? -1 : 1).slice(-800);
}

async function refreshAll(items) {
  if (!DO_REFRESH) return items;
  const ok = await probe();
  if (!ok) { console.log('[refresh] 网络探测失败，使用本地快照生成'); return items; }
  console.log('[refresh] 探测通过，刷新最近日K（并发 ' + CONC + '）…');
  let done = 0;
  for (let i = 0; i < items.length; i += CONC) {
    const batch = items.slice(i, i + CONC);
    await Promise.all(batch.map(async s => {
      const fr = await fetchRecent(s.code);
      if (fr) s.kline.day = mergeDay(s.kline.day, fr);
    }));
    done += batch.length;
    if (done % 200 < CONC || done >= items.length) console.log(`[refresh] ${done}/${items.length}`);
  }
  return items;
}

// ===== 主流程 =====
(async () => {
  console.log('加载宇宙 K线:', UNI);
  const raw = JSON.parse(fs.readFileSync(UNI, 'utf8'));
  let items = raw.items || [];
  console.log('原始股票数:', items.length);
  items = items.filter(s => s.code && s.kline && Array.isArray(s.kline.day) && s.kline.day.length >= 60);
  console.log('有效(日K≥60):', items.length);

  items = await refreshAll(items);

  const all = items.map(s => ({ name: s.name, code: s.code, board: s.board, t: trendOf(s.kline.day) }));

  // 选股：日线转强(up) 且 非(月空 & 周空)
  const ranked = all
    .map(a => ({ ...a, score: scoreOf(a.t) }))
    .filter(a => a.t.day === 'up' && !(a.t.month === 'down' && a.t.week === 'down'))
    .sort((a, b) => b.score - a.score);

  // 候选股池：按综合评分取前 MAX_CANDIDATES（≤300），优中选优第一层（避免市况好时候选膨胀）
  const cands = ranked.slice(0, MAX_CANDIDATES);

  // 优中选优第二层：从候选池精选展示评分最高的前 TOP_N
  const out = cands.slice(0, TOP_N).map(a => {
    const last = a.t.lastClose;
    let stop = Math.min(a.t.low10, last * 0.95);
    if (!(stop < last)) stop = last * 0.95;
    stop = Math.round(stop * 100) / 100;
    const risk = Math.round((last - stop) * 100) / 100;
    const target = Math.round((last + risk * 3) * 100) / 100;
    const entry = Math.round(last * 100) / 100;
    return {
      name: a.name, code: a.code, board: a.board,
      month: a.t.month, week: a.t.week, day: a.t.day,
      score: a.score, entry, stopLoss: stop, target,
      reasons: reasonsOf(a.t),
    };
  });

  const total = out.length;
  const candidates = cands.length;
  const resonance = out.filter(x => x.month === 'up' && x.week === 'up' && x.day === 'up').length;
  const diverge = out.filter(x => x.week === 'down' || x.month === 'down').length;
  const partial = total - resonance - diverge;

  const mu = all.filter(a => a.t.month === 'up').length / all.length;
  const wu = all.filter(a => a.t.week === 'up').length / all.length;
  const du = all.filter(a => a.t.day === 'up').length / all.length;
  const marketPhase = `月线多头${(mu * 100).toFixed(0)}% / 周线多头${(wu * 100).toFixed(0)}% / 日线多头${(du * 100).toFixed(0)}%`;

  const report = {
    generatedAt: new Date().toISOString().slice(0, 10),
    summary: { candidates, total, resonance, partial, diverge, marketPhase },
    analysis: buildAnalysis(all, out, mu, wu, du, resonance, partial, diverge, total, candidates),
    stocks: out,
  };

  fs.writeFileSync(OUT, JSON.stringify(report, null, 2), 'utf8');
  console.log(`✅ 已生成 ${OUT}`);
  console.log(`   达标 ${total} | 三周期共振 ${resonance} | 部分共振 ${partial} | 周期背离 ${diverge}`);
  console.log('   市场阶段:', marketPhase);
  if (out.length) console.log('   头部:', out.slice(0, 3).map(x => `${x.name}(${x.code}) ${x.month}/${x.week}/${x.day} 分${x.score}`).join(' | '));
})().catch(e => { console.error('生成失败:', e); process.exit(1); });
