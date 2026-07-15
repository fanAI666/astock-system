// 交易胜率回测：基于系统选股结果（import_final.json）的实时 K 线，
// 按"已定交易规则"在 2025.7.1–2026.6.30 区间回测，输出胜率等统计。
//
// 规则（与买入触发面板一致）：
//   - 候选：每日按 success-probability(win) 降序取 Top3
//   - 基准：信号日 D 收盘 close[D]
//   - 入场：次日开盘 open[D+1]，要求 |(open-baseline)/baseline| <= 容差
//        主板(main) ±2%；创业板(cyb)/科创板(kcb) ±3%
//   - 出场（分市场）：主板固定 2%/6% 强制止损；创业板/科创板走 ATR 动态止损（止损距离随波动放大、止盈×3 保持3:1、持有封顶1周、跟踪止损封顶6%）
//   - 持有：逐根扫描，先触止损→亏损，先触止盈→盈利；超出持有窗口则按窗口末收盘结算
//
// 本轮迭代（对应 5 点路线图）：
//   ① 地基：winRate 用回测真实胜率标定 + 分层校验（按板块 / 按预测胜率档）
//   ③ 提效：趋势 + 量能 + 缺口 过滤，应用到全市场（不仅双创）
//   ④ 稳健：拉长历史（320 根真实日线，2025-03 起，由 extend_history.js 注入）
//            + 扩大候选池（全候选股回测，非仅 Top3）+ 分市场回测（byBoard 已含）
//
// K 线格式：bar = [日期"YYYYMMDD", 开, 收, 高, 低, 量]

const fs = require('fs');
const path = require('path');

const SRC = 'D:/WorkBuddy/选股结果/import_final.json';
const OUT = 'D:/WorkBuddy/选股结果/backtest_winrate.json';

const PERIOD = { from: '20250701', to: '20260630' };

// ---- 分市场止损参数 ----
const MAX_HOLD_MAIN = 10;   // 主板持有窗口（交易日）
const MAX_HOLD_DYN  = 5;    // 双创持有封顶：1 周 ≈ 5 交易日
const K_ATR    = 1.05;      // 动态止损倍数（× ATR14）—— v1.0.2 由 1.5 收窄至 1.05
const TRAIL_PCT = 0.03;     // 跟踪止损回撤比例
const TRAIL_CAP = 0.06;     // 跟踪止损封顶（最多锁定 6% 利润）
const ATR_WIN  = 14;        // ATR 窗口
// ---- ③ 提效：趋势 / 量能 / 缺口 过滤（v1.0.3 起全市场应用）----
const MA_WIN_TREND = 20;    // 趋势均线窗口
const MA_WIN_SHORT = 5;     // 短期均线窗口
const VOL_MULT = 1.2;       // 量能：信号日量 ≥ 1.2 × 20 日均量
const GAP_DOWN = 0.04;      // 缺口过滤：信号日向下跳空 ≥4% → 弱势，不触发
const GAP_UP   = 0.06;      // 缺口过滤：信号日向上跳空 ≥6% → 透支，不触发

// 截至 idx 的 ATR(ATR_WIN)，需 idx >= ATR_WIN
function atr14(bars, idx) {
  if (idx < ATR_WIN) return null;
  let s = 0;
  for (let k = idx - ATR_WIN + 1; k <= idx; k++) {
    const c0 = bars[k - 1][2];
    const h = bars[k][3], l = bars[k][4];
    const tr = Math.max(h - l, Math.abs(h - c0), Math.abs(l - c0));
    s += tr;
  }
  return s / ATR_WIN;
}

// 简单移动平均：bars[idx][field] 前 win 根的均值；不足返回 null
// bar 字段：0=日期,1=开,2=收,3=高,4=低,5=量
function sma(bars, idx, win, field) {
  if (idx < win - 1 || idx >= bars.length) return null;
  let s = 0;
  for (let k = idx - win + 1; k <= idx; k++) s += bars[k][field];
  return s / win;
}

// ③ 买入前过滤（全市场）：趋势 + 量能 + 缺口
//   趋势：站上 MA20 + 短中期多头(MA5 > MA20) + 中期向上(MA20 > 前一日 MA20)
//   量能：信号日量 ≥ VOL_MULT × MA20 量
//   缺口：信号日与昨收之间跳空不过大（向下弱势 / 向上透支均拒）
// 返回 { trendOk, volOk, gapOk }
function passPreFilter(bars, i) {
  const close = bars[i][2];
  const open = bars[i][1];
  const vol = bars[i][5];
  const prevClose = i > 0 ? bars[i - 1][2] : close;

  // 缺口
  const gap = (open - prevClose) / prevClose;
  const gapOk = gap >= -GAP_DOWN && gap <= GAP_UP;

  // 趋势 + 量能
  const ma5 = sma(bars, i, MA_WIN_SHORT, 2);
  const ma20 = sma(bars, i, MA_WIN_TREND, 2);
  const ma20Prev = sma(bars, i - 1, MA_WIN_TREND, 2);
  const ma20Vol = sma(bars, i, MA_WIN_TREND, 5);

  let trendOk = false;
  if (ma20 != null && ma5 != null) {
    const rising = ma20Prev != null ? (ma20 > ma20Prev) : true;
    trendOk = (close > ma20) && (ma5 > ma20) && rising;
  }
  let volOk = false;
  if (ma20Vol != null && ma20Vol > 0) volOk = vol >= ma20Vol * VOL_MULT;

  return { trendOk, volOk, gapOk };
}

function tolFor(board) {
  if (board === 'cyb' || board === 'kcb' || board === 'kc') return 0.03;
  return 0.02;
}

const data = JSON.parse(fs.readFileSync(SRC, 'utf8'));
const items = data.items || [];

// 实际 K 线数据覆盖区间（用于诚实标注有效回测窗口）
let dataFrom = '99999999', dataTo = '00000000';
items.forEach(s => {
  const bars = (s.kline && s.kline.day) || [];
  bars.forEach(b => { if (b[0] < dataFrom) dataFrom = b[0]; if (b[0] > dataTo) dataTo = b[0]; });
});
const fmt = d => d.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3');

// 按 win 降序排，取 Top3 作为系统每日候选（与线上买入触发一致）
const ranked = items.slice().sort((a, b) => (b.win || 0) - (a.win || 0));
const top3 = ranked.slice(0, 3);

const skippedNoData = [];
const skippedNoAtr = [];   // 双创票信号日 ATR 窗口不足，跳过

// ③ 全市场前过滤漏斗统计
const preStats = { total: 0, pass: 0, skipTrend: 0, skipVol: 0, skipGap: 0 };

// 候选信号（Phase A：逐票逐日生成，未做组合层约束）
const candidates = [];

function genSignals(stock) {
  const bars = (stock.kline && stock.kline.day) || [];
  if (bars.length < 2) { skippedNoData.push(stock.code); return; }
  const board = stock.board;
  const isDyn = (board === 'cyb' || board === 'kcb' || board === 'kc'); // 创业板/科创板 → 动态止损
  const tol = tolFor(board);

  for (let i = 0; i < bars.length - 1; i++) {
    const d = bars[i];
    const nd = bars[i + 1];
    const dateD = d[0];
    if (dateD < PERIOD.from || dateD > PERIOD.to) continue; // 仅统计周期内信号

    const baseline = d[2];          // 信号日收盘

    // ③ 全市场：趋势 + 量能 + 缺口 过滤，未过则不触发
    preStats.total++;
    const f = passPreFilter(bars, i);
    if (!f.trendOk) { preStats.skipTrend++; continue; }
    if (!f.volOk)   { preStats.skipVol++;   continue; }
    if (!f.gapOk)   { preStats.skipGap++;   continue; }
    preStats.pass++;

    const nextOpen = nd[1];         // 次日开盘
    if (!baseline || !nextOpen) continue;
    const dev = (nextOpen - baseline) / baseline;
    if (Math.abs(dev) > tol) continue; // 不满足入场条件 → 当日不交易
    const entry = nextOpen;

    let sl, tp, maxHold, slDist;
    if (isDyn) {
      const a = atr14(bars, i); // 用信号日及之前 14 根算 ATR
      if (a == null) { skippedNoAtr.push(stock.code); continue; }
      slDist = K_ATR * a;          // 止损距离随波动放大
      sl = entry - slDist;          // 动态止损线
      tp = entry + 3 * slDist;     // 止盈按比例放大（保持 3:1）
      maxHold = MAX_HOLD_DYN;      // 1 周封顶
    } else {
      slDist = entry * 0.02;
      sl = entry * 0.98;           // 主板强制止损 -2%
      tp = entry * 1.06;           // 主板强制止盈 +6%
      maxHold = MAX_HOLD_MAIN;
    }
    const trailCap = entry * (1 + TRAIL_CAP); // 跟踪封顶价（双创）
    let curSL = sl;

    let outcome = null, exitPrice = entry, exitIdx = i + 1, holdDays = 0;
    for (let j = i + 1; j < bars.length && j <= i + maxHold; j++) {
      const h = bars[j][3], l = bars[j][4];
      holdDays++;
      if (l <= curSL) { outcome = 'loss'; exitPrice = curSL; exitIdx = j; break; } // 止损/跟踪止损
      if (h >= tp)    { outcome = 'win';  exitPrice = tp;    exitIdx = j; break; } // 止盈
      if (isDyn) { // 跟踪止损上移（封顶 6%）
        const newSL = Math.min(trailCap, Math.max(curSL, h * (1 - TRAIL_PCT)));
        if (newSL > curSL) curSL = newSL;
      }
    }
    if (!outcome) { // 到封顶日仍未触发 → 按收盘结算
      const jlast = Math.min(bars.length - 1, i + maxHold);
      exitPrice = bars[jlast][2];
      outcome = exitPrice >= entry ? 'win' : 'loss';
      holdDays = jlast - i;
    }

    const ret = (exitPrice - entry) / entry;
    candidates.push({
      code: stock.code, name: stock.name, board, isDyn,
      signalDate: dateD, entryDate: nd[0],
      baseline: +baseline.toFixed(4), entry: +entry.toFixed(4),
      slDist: +slDist.toFixed(4), maxHold,
      exitDate: bars[exitIdx][0], exit: +exitPrice.toFixed(4),
      dev: +dev.toFixed(5), tol, outcome, ret: +ret.toFixed(5), holdDays,
      predicted: stock.win // ① 标定用：系统预测成功概率
    });
  }
}

// ④ 稳健：扩大候选池 —— 对全部候选股（非仅 Top3）回测，样本更足、结论更可信。
//   注：线上每日触发仍取 Top3（见 top3 字段），此处为策略规则本身的稳健性检验。
items.forEach(genSignals);

// ==================== ⑤ 组合层约束 ====================
// 在"全候选池信号(candidates)"之上叠加三层风控：
//   (1) 大盘硬过滤：信号日 上证指数 收盘 < MA20(20日) → 视为空头，当日全市场不交易
//   (2) 同日上限：每个信号日最多开仓 MAX_BUY_PER_DAY 笔（按预测胜率降序取优先）
//   (3) 回撤上限：权益曲线自峰值回撤 > DD_PAUSE → 暂停下一交易日开仓（冷却一天）
// 注：前三层(①地基/②止血/③提效)决定单笔规则；⑤只做组合层风险裁剪，不改单笔逻辑。

const INDEX_FILE = 'D:/WorkBuddy/选股结果/index_sh.json';
const MAX_BUY_PER_DAY = 3;   // 同日开仓上限
const DD_PAUSE = 0.08;       // 权益回撤上限 8% → 暂停下一交易日
const IDX_MA_WIN = 20;

// 加载上证指数，构建 日期→收盘 / 日期→MA20
let idxClose = {}, idxMA20 = {};
try {
  const idx = JSON.parse(fs.readFileSync(INDEX_FILE, 'utf8'));
  const ib = idx.bars || [];
  ib.forEach(b => { idxClose[b[0]] = b[2]; });            // b[2]=收盘
  for (let i = 0; i < ib.length; i++) {
    if (i >= IDX_MA_WIN - 1) {
      let s = 0; for (let k = i - IDX_MA_WIN + 1; k <= i; k++) s += ib[k][2];
      idxMA20[ib[i][0]] = s / IDX_MA_WIN;
    }
  }
} catch (e) { console.log('⚠ 未加载上证指数(' + INDEX_FILE + ')：' + e.message); }

// (1) 大盘硬过滤
const idxFiltered = [];
const afterIndex = [];
const idxBearishDays = new Set();
candidates.forEach(c => {
  const ma = idxMA20[c.signalDate], cl = idxClose[c.signalDate];
  if (ma != null && cl != null && cl < ma) { idxFiltered.push(c); idxBearishDays.add(c.signalDate); }
  else afterIndex.push(c);
});

// (2) 同日上限（按预测胜率降序优先保留）
const byDay = {};
afterIndex.forEach(c => { (byDay[c.signalDate] = byDay[c.signalDate] || []).push(c); });
const afterCap = [];
let perDayCapped = 0;
Object.keys(byDay).sort().forEach(d => {
  const arr = byDay[d].slice().sort((a, b) => (b.predicted || 0) - (a.predicted || 0));
  perDayCapped += Math.max(0, arr.length - MAX_BUY_PER_DAY);
  arr.slice(0, MAX_BUY_PER_DAY).forEach(c => afterCap.push(c));
});

// (3) 回撤上限（权益曲线自峰值回撤 > 阈 → 暂停下一交易日）
const allDates = [...new Set(afterCap.map(c => c.signalDate))].sort();
const dateIdx = {}; allDates.forEach((d, i) => dateIdx[d] = i);
const ddSorted = afterCap.slice().sort((a, b) =>
  a.signalDate < b.signalDate ? -1 : a.signalDate > b.signalDate ? 1 : (b.predicted || 0) - (a.predicted || 0));
let equity = 1, peak = 1, paused = false, pauseUntil = null, ddPaused = 0;
const trades = [];
for (const c of ddSorted) {
  if (paused) {
    if (pauseUntil == null || c.signalDate <= pauseUntil) { ddPaused++; continue; }
    paused = false;
  }
  equity *= (1 + c.ret);
  if (equity > peak) peak = equity;
  trades.push(c);
  if (peak - equity > DD_PAUSE * peak) {          // 触发回撤上限
    paused = true;
    const i = dateIdx[c.signalDate];
    pauseUntil = (i + 1 < allDates.length) ? allDates[i + 1] : null; // 暂停下一交易日
  }
}

const portfolio = {
  enabled: true,
  indexFilter:   { rule: '上证指数收盘<MA20(20日) → 当日全市场不交易', dropped: idxFiltered.length, bearishDays: idxBearishDays.size },
  perDayCap:     { max: MAX_BUY_PER_DAY, rule: '每个信号日最多开仓 ' + MAX_BUY_PER_DAY + ' 笔（按预测胜率降序优先）', dropped: perDayCapped },
  drawdownPause: { threshold: DD_PAUSE, rule: '权益曲线自峰值回撤>' + (DD_PAUSE * 100).toFixed(0) + '% → 暂停下一交易日开仓', dropped: ddPaused },
  finalTrades: trades.length,
  stageCounts: { raw: candidates.length, afterIndex: afterIndex.length, afterCap: afterCap.length, final: trades.length }
};

// 统计
const total = trades.length;
const wins = trades.filter(t => t.outcome === 'win');
const losses = trades.filter(t => t.outcome === 'loss');
const winRate = total ? wins.length / total : 0;
const avgWin = wins.length ? wins.reduce((s, t) => s + t.ret, 0) / wins.length : 0;
const avgLoss = losses.length ? losses.reduce((s, t) => s + Math.abs(t.ret), 0) / losses.length : 0;
const sumWin = wins.reduce((s, t) => s + t.ret, 0);
const sumLoss = losses.reduce((s, t) => s + Math.abs(t.ret), 0);
const profitFactor = sumLoss ? sumWin / sumLoss : (sumWin ? Infinity : 0);
const avgHold = total ? trades.reduce((s, t) => s + t.holdDays, 0) / total : 0;

// 分市场统计
const byBoard = {};
trades.forEach(t => {
  const b = t.board;
  byBoard[b] = byBoard[b] || { trades: 0, wins: 0 };
  byBoard[b].trades++;
  if (t.outcome === 'win') byBoard[b].wins++;
});
Object.keys(byBoard).forEach(b => {
  const o = byBoard[b];
  o.winRate = o.trades ? +(o.wins / o.trades).toFixed(4) : 0;
});

// ① 分层校验：按预测胜率档（高 ≥70 / 低 <70）
const byWinTier = {
  high: { predMin: 70, trades: 0, wins: 0 },
  low:  { predMin: 0,  trades: 0, wins: 0 }
};
trades.forEach(t => {
  const tier = (t.predicted >= 70) ? byWinTier.high : byWinTier.low;
  tier.trades++;
  if (t.outcome === 'win') tier.wins++;
});
Object.keys(byWinTier).forEach(k => {
  const o = byWinTier[k];
  o.winRate = o.trades ? +(o.wins / o.trades).toFixed(4) : 0;
});

// ① 标定：每票"预测成功概率" vs "回测实现胜率"，并算整体偏差
const perStock = {};
trades.forEach(t => {
  perStock[t.code] = perStock[t.code] || { code: t.code, name: t.name, board: t.board, predicted: t.predicted, trades: 0, wins: 0 };
  perStock[t.code].trades++;
  if (t.outcome === 'win') perStock[t.code].wins++;
});
const perStockArr = Object.values(perStock).map(o => {
  o.realized = o.trades ? +(o.wins / o.trades).toFixed(4) : 0;
  return o;
});
const predList = perStockArr.map(o => o.predicted).filter(v => v != null);
const predMean = predList.length ? predList.reduce((s, v) => s + v, 0) / predList.length : 0;
const calibBias = +(predMean / 100 - winRate).toFixed(4); // 预测均值 - 实现胜率（>0 表示系统过度乐观）

// 期望值（每笔平均收益）
const expectancy = winRate * avgWin - (1 - winRate) * avgLoss;

const result = {
  metric: 'winRate',
  label: '交易胜率',
  period: { from: '2025-07-01', to: '2026-06-30' },
  dataRange: { from: fmt(dataFrom), to: fmt(dataTo) },
  winRate: +winRate.toFixed(4),
  trades: total,
  wins: wins.length,
  losses: losses.length,
  avgWin: +avgWin.toFixed(4),
  avgLoss: +avgLoss.toFixed(4),
  profitFactor: isFinite(profitFactor) ? +profitFactor.toFixed(2) : null,
  expectancy: +expectancy.toFixed(4),
  avgHoldDays: +avgHold.toFixed(2),
  universe: items.length,
  pool: 'full',                                       // ④ 扩大候选池：全候选股回测（非仅 Top3）
  note: '④ 稳健：历史已拉长至 ' + (dataTo ? fmt(dataTo) : '?') + ' 起约320根真实日线；候选池覆盖全部 ' + items.length + ' 支（主板+kcb，无创业板）。',
  top3: top3.map(s => ({ code: s.code, name: s.name, board: s.board, win: s.win })),
  byBoard,
  byWinTier,                                   // ① 分层校验
  calibration: {                                // ① 标定
    predMean: +(predMean / 100).toFixed(4),
    realized: +winRate.toFixed(4),
    bias: calibBias,                            // >0 表示系统预测偏乐观
    perStock: perStockArr
  },
  preFilter: {                                  // ③ 全市场过滤漏斗
    total: preStats.total, pass: preStats.pass,
    skipTrend: preStats.skipTrend, skipVol: preStats.skipVol, skipGap: preStats.skipGap
  },
  ruleMain: '主板：强制止损−2%/止盈+6%（固定3:1），持有≤10日',
  ruleDyn: '创业板/科创板：先过趋势(站上MA20+MA5>MA20+MA20上行)+量能(≥1.2×20日均量)+缺口(±4%~6%)过滤；通过后再走动态止损=入场价−1.05×ATR(14)，止盈×3，持有封顶1周(5日)+跟踪止损封顶6%',
  ruleFilterAll: '全市场(主板+双创)：触发前均需过 趋势+量能+缺口 过滤（v1.0.3 起）',
  rulePortfolio: '⑤ 组合层：大盘硬过滤(上证<MA20当日不交易) + 同日上限(≤' + MAX_BUY_PER_DAY + '笔) + 回撤上限(>' + (DD_PAUSE * 100).toFixed(0) + '%暂停次日)',
  portfolio,
  generatedAt: new Date().toISOString().slice(0, 10),
  trades_detail: trades
};

fs.writeFileSync(OUT, JSON.stringify(result, null, 2), 'utf8');

console.log('=== 交易胜率回测 ===');
console.log('回测周期 :', PERIOD.from, '~', PERIOD.to);
console.log('数据覆盖 :', fmt(dataFrom), '~', fmt(dataTo), '(实际 K 线起点，非完整周期)');
console.log('候选宇宙 :', items.length, '支 | Top3 =', top3.map(s => s.name + '(' + s.win + ')').join(', '));
console.log('候选池   : 全', items.length, '支（④ 扩大候选池，非仅 Top3）');
console.log('触发交易 :', total, '笔');
console.log('盈利/亏损:', wins.length, '/', losses.length);
console.log('交易胜率 :', (winRate * 100).toFixed(1) + '%');
console.log('平均盈/亏:', (avgWin * 100).toFixed(2) + '% /', (avgLoss * 100).toFixed(2) + '%');
console.log('盈亏比   :', isFinite(profitFactor) ? profitFactor.toFixed(2) : '∞');
console.log('期望值   :', (expectancy * 100).toFixed(2) + '% / 笔');
console.log('平均持有 :', avgHold.toFixed(2), '交易日');
console.log('输出文件 :', OUT, '(', fs.statSync(OUT).size, 'bytes )');
if (skippedNoData.length) console.log('跳过(无K线):', skippedNoData.join(','));
if (skippedNoAtr.length) console.log('跳过(双创ATR不足):', skippedNoAtr.join(','));
if (preStats.total) console.log('全市场过滤: 候选', preStats.total, '| 通过', preStats.pass, '| 趋势未过', preStats.skipTrend, '| 量能未过', preStats.skipVol, '| 缺口未过', preStats.skipGap);
console.log('分市场胜率 :', Object.entries(byBoard).map(([b, o]) => `${b} ${(o.winRate * 100).toFixed(1)}%(${o.wins}/${o.trades})`).join('  '));
console.log('分层(预测≥70):', (byWinTier.high.winRate * 100).toFixed(1) + `%(${byWinTier.high.wins}/${byWinTier.high.trades})`,
            '| 分层(预测<70):', (byWinTier.low.winRate * 100).toFixed(1) + `%(${byWinTier.low.wins}/${byWinTier.low.trades})`);
console.log('标定偏差   : 预测均值', (predMean).toFixed(1) + '% vs 实现', (winRate * 100).toFixed(1) + '% (偏差', (calibBias * 100).toFixed(1) + 'pp)');

console.log('\n=== ⑤ 组合层风控 ===');
console.log('大盘硬过滤 : 剔除', portfolio.indexFilter.dropped, '笔 | 空头交易日', portfolio.indexFilter.bearishDays, '天(上证<MA20)');
console.log('同日上限   : ≤', portfolio.perDayCap.max, '笔/日 | 剔除', portfolio.perDayCap.dropped, '笔');
console.log('回撤上限   : 阈值', (portfolio.drawdownPause.threshold * 100).toFixed(0) + '% | 暂停剔除', portfolio.drawdownPause.dropped, '笔');
console.log('组合后成交 :', portfolio.finalTrades, '笔  (阶段 raw', portfolio.stageCounts.raw,
            '→ 过指', portfolio.stageCounts.afterIndex,
            '→ 过限', portfolio.stageCounts.afterCap,
            '→ 最终', portfolio.stageCounts.final, ')');
