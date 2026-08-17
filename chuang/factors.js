'use strict';
// chuang/factors.js — 双创因子层（2026-08-12 因子挖掘 14 轮验证产物）
//
// 只落地「唯一通过全部验证的因子」：idioVol60 = 低特质波动（对市场等权收益做 60 日滚动回归后的残差波动）
//
// 验证证据链（脚本：chuang_factor_mining.py / chuang_factor_validate2-4.py，结果落 选股结果/factor_*.json）：
//   R1  横截面 RankIC: IC=-0.0936 ICIR=-0.52（h=20，方向为负 → 低波更优），441 个交易日
//   R10 流动性中性池(成交额 Q2-Q4)内 vs 同池随机基线：
//         胜率 36.28% vs 31.11%   期望 +0.773%/笔 vs +0.465%   PF 1.61 vs 1.34
//         F3 +0.334 vs +0.165     holdout +0.320 vs +0.040     ← 唯一 F3 与 holdout 双正的因子
//   R11 生产级流动性池(≥1亿)同样成立：35.32% / +0.669% / PF1.52，holdout +0.163 vs 随机 +0.032
//   R12 相对 edge 对滑点不敏感（+0.36~0.47pp 恒定，滑点对因子与基线等量伤害）
//   R14 block-bootstrap 1000 次按日整块重采样：期望差 +0.35~0.39pp，95%CI [0.18,0.60]，P(差>0)=1.000
//   R13 所有双因子组合（配 pePct/rev20/dip250/skew60/aboveMA20/vol20）均劣于单因子 → 保持单因子
//
// 已否决（不落地）：
//   turn20 / amihud20  低流动性 = 边界套利：下限抬到 5000万+ 或流动性中性化后归零（R6/R10b）
//   skew60 / vol20 / pePct / rev20 / dip250   流动性中性池内不优于随机基线（R10b）
//   npGrowth / revGrowth / g5Quality / peg / rev4w / fy1NpYoY
//                      静态快照回填历史 = 未来函数，R1 的"通过"无效（R2 剔除）
//   peadAccel          经济含义最干净（十分位 2.19%→5.59% 单调，mono=0.88）但仅 7 个横截面，样本不足
//
// 已知短板（必须写在这里，防止后人误以为已转正）：
//   分年度 2024 +0.343% / 2025 +0.417% / 2026YTD -0.349%（0.6% 双边滑点口径）
//   → 因子相对优势稳定，但绝对期望在 2026 弱市为负；默认关闭，等中报季 5.7 闸门用真实数据定夺。
//
// 输出：buildFactorPass(cfg) → { passByDate: Map(date→Set(code)), stats }
// 默认不调用（config.factors.enabled=false → 回测 parity 不变）。

const { loadUniverse } = require('./data');

const ANN = Math.sqrt(252);

function buildFactorPass(cfg) {
  const F = cfg.factors;
  const universe = loadUniverse(F.universeFile);
  const W = F.idioVolWindow;
  const MINB = F.minBars;

  // ---- 1) 市场等权日收益（横截面均值，无未来函数）----
  const mktSum = new Map(), mktCnt = new Map();
  const per = [];
  for (const s of universe) {
    const bars = (s.kline && s.kline.day) || [];
    const n = bars.length;
    if (n < MINB + 5) continue;
    const D = new Array(n), C = new Float64Array(n), V = new Float64Array(n);
    for (let i = 0; i < n; i++) { D[i] = bars[i][0]; C[i] = bars[i][2]; V[i] = bars[i][5]; }
    const R = new Float64Array(n).fill(NaN);
    for (let i = 1; i < n; i++) if (C[i - 1] > 0) R[i] = C[i] / C[i - 1] - 1;
    per.push({ code: s.code, D, C, V, R, n });
    for (let i = 1; i < n; i++) {
      if (!Number.isFinite(R[i])) continue;
      mktSum.set(D[i], (mktSum.get(D[i]) || 0) + R[i]);
      mktCnt.set(D[i], (mktCnt.get(D[i]) || 0) + 1);
    }
  }
  const mkt = new Map();
  for (const [d, sum] of mktSum) mkt.set(d, sum / mktCnt.get(d));

  // ---- 2) 逐股 idioVol60 + turnover20 ----
  const byDate = new Map();   // date -> [{code, iv, t20}]
  let skippedShort = 0;
  for (const p of per) {
    const { D, C, V, R, n } = p;
    const M = new Float64Array(n).fill(NaN);
    for (let i = 0; i < n; i++) { const m = mkt.get(D[i]); if (m != null) M[i] = m; }
    // 滚动 60 日：beta = cov(r,m)/var(m)，残差 e = r - beta*m，idioVol = std(e)*sqrt(252)
    for (let i = MINB; i < n; i++) {
      let sr = 0, sm = 0, srm = 0, smm = 0, k = 0;
      for (let j = i - W + 1; j <= i; j++) {
        const r = R[j], m = M[j];
        if (!Number.isFinite(r) || !Number.isFinite(m)) continue;
        sr += r; sm += m; srm += r * m; smm += m * m; k++;
      }
      if (k < W * 0.8) continue;
      const mr = sr / k, mm = sm / k;
      const varM = smm / k - mm * mm;
      if (!(varM > 1e-12)) continue;
      const beta = (srm / k - mr * mm) / varM;
      let se = 0, se2 = 0, ke = 0;
      for (let j = i - W + 1; j <= i; j++) {
        const r = R[j], m = M[j];
        if (!Number.isFinite(r) || !Number.isFinite(m)) continue;
        const e = r - beta * m; se += e; se2 += e * e; ke++;
      }
      if (ke < 2) continue;
      const iv = Math.sqrt(Math.max(0, se2 / ke - (se / ke) ** 2)) * ANN;
      // turnover20（元）：与 G1 同口径
      let amt = 0, ka = 0;
      for (let j = i - 19; j <= i; j++) { if (j >= 0) { amt += V[j] * 100 * C[j]; ka++; } }
      const t20 = ka === 20 ? amt / 20 : null;
      if (t20 == null || !(t20 >= F.minTurnover)) continue;
      if (!Number.isFinite(iv)) continue;
      let arr = byDate.get(D[i]); if (!arr) { arr = []; byDate.set(D[i], arr); }
      arr.push({ code: p.code, iv });
    }
    if (n < MINB + 5) skippedShort++;
  }

  // ---- 3) 每日取 idioVol 最低的 maxPct 比例（横截面排序）----
  const passByDate = new Map();
  let dayKept = 0, dayTot = 0, poolSum = 0, passSum = 0;
  for (const [d, arr] of byDate) {
    dayTot++;
    if (arr.length < F.minCrossSection) continue;
    arr.sort((a, b) => a.iv - b.iv);
    const keep = Math.max(F.minKeep, Math.floor(arr.length * F.maxPct));
    const set = new Set();
    for (let i = 0; i < keep && i < arr.length; i++) set.add(arr[i].code);
    passByDate.set(d, set);
    dayKept++; poolSum += arr.length; passSum += set.size;
  }
  return {
    passByDate,
    stats: {
      factor: 'idioVol60(low)', window: W, maxPct: F.maxPct,
      minTurnover: F.minTurnover, universe: per.length, skippedShort,
      daysTotal: dayTot, daysWithPass: dayKept,
      avgPoolPerDay: dayKept ? +(poolSum / dayKept).toFixed(1) : 0,
      avgPassPerDay: dayKept ? +(passSum / dayKept).toFixed(1) : 0,
    },
  };
}

module.exports = { buildFactorPass };
