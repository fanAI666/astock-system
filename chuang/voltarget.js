'use strict';
// chuang/voltarget.js — 波动率目标叠加层（risk-overlay，2026-08-17 P1）
//
// 动机（专家视角诊断报告 2026-08-15，方向 A/B 之外的「最快可测」杠杆）：
//   双创亏损集中在高波动 regime；纯动量/价量选股在波动放大期无 alpha。
//   用「板块等权收益滚动已实现波动」做 regime 门，高波日暂停入场 —— 不改任何选股/止损/止盈规则，
//   只在不该出手的日子收手。验证假设「择时贡献 > 选股」。
//
// 度量：
//   r[d] = 双创板块（300/301/688/689）等权日收益均值
//   vol[d] = std(r[d-W+1..d]) * sqrt(252)   （W=滚动窗，默认 60）
// 判定（两种，env 可切）：
//   绝对阈值 mode='abs'：vol[d] > volPause → 暂停（volPause 默认 0.40，即年化 40%）
//   z 分数   mode='z'  ：z = (vol[d]-mean(vol[d-L..d-1]))/std(...) > zThresh → 暂停（L 默认 250，zThresh 默认 1.5）
//   ※ z 模式只用 d 之前的历史，无未来函数。
//
// 输出：buildVolTarget(cfg) → { okByDate: Map(date→bool 是否可交易), stats }
// 默认不调用（config.volTarget.enabled=false → 回测 parity 不变）。

const { loadUniverse } = require('./data');
const ANN = Math.sqrt(252);

function isChuang(code) {
  return code.startsWith('300') || code.startsWith('301') || code.startsWith('688') || code.startsWith('689');
}

function buildVolTarget(cfg) {
  const V = cfg.volTarget;
  const universe = loadUniverse(V.universeFile);
  const W = V.window;

  // ---- 1) 板块等权日收益 ----
  const sum = new Map(), cnt = new Map();
  for (const s of universe) {
    if (!isChuang(s.code)) continue;
    const bars = (s.kline && s.kline.day) || [];
    const n = bars.length;
    if (n < W + 5) continue;
    const D = new Array(n), C = new Float64Array(n);
    for (let i = 0; i < n; i++) { D[i] = bars[i][0]; C[i] = bars[i][2]; }
    for (let i = 1; i < n; i++) {
      if (C[i - 1] > 0) {
        const r = C[i] / C[i - 1] - 1;
        sum.set(D[i], (sum.get(D[i]) || 0) + r);
        cnt.set(D[i], (cnt.get(D[i]) || 0) + 1);
      }
    }
  }
  const dates = [...sum.keys()].sort();
  const rArr = dates.map(d => sum.get(d) / cnt.get(d));

  // ---- 2) 滚动已实现波动（年化）----
  const vol = new Map();
  for (let i = W; i < dates.length; i++) {
    let m = 0; for (let j = i - W + 1; j <= i; j++) m += rArr[j]; m /= W;
    let v = 0; for (let j = i - W + 1; j <= i; j++) { const x = rArr[j] - m; v += x * x; }
    v = Math.sqrt(v / W) * ANN;
    vol.set(dates[i], v);
  }

  // ---- 3) regime 判定 → okByDate ----
  const okByDate = new Map();
  let pauseDays = 0, totalDays = 0;
  const volDates = [...vol.keys()].sort();
  for (let k = 0; k < volDates.length; k++) {
    const d = volDates[k]; const v = vol.get(d); totalDays++;
    let ok = true;
    if (V.mode === 'z') {
      const L = V.zLook;
      if (k >= L) {
        let m = 0; for (let j = k - L; j < k; j++) m += vol.get(volDates[j]); m /= L;
        let s2 = 0; for (let j = k - L; j < k; j++) { const x = vol.get(volDates[j]) - m; s2 += x * x; }
        const sd = Math.sqrt(s2 / L);
        if (sd > 1e-9) { const z = (v - m) / sd; if (z > V.zThresh) ok = false; }
      }
    } else {
      if (v > V.volPause) ok = false;
    }
    if (!ok) pauseDays++;
    okByDate.set(d, ok);
  }

  return {
    okByDate,
    stats: {
      mode: V.mode, window: W,
      volPause: V.mode === 'abs' ? V.volPause : undefined,
      zThresh: V.mode === 'z' ? V.zThresh : undefined, zLook: V.mode === 'z' ? V.zLook : undefined,
      boardStocks: universe.filter(s => isChuang(s.code)).length,
      volDaysComputed: totalDays, pauseDays,
      pauseRate: totalDays ? +(pauseDays / totalDays).toFixed(3) : 0,
      sampleVolAnnualized: totalDays ? +(volDates.reduce((a, d) => a + vol.get(d), 0) / totalDays).toFixed(3) : 0,
    },
  };
}

module.exports = { buildVolTarget, isChuang };
