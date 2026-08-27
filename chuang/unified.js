'use strict';
// chuang/unified.js — 总选股「优中选优」聚合器
// 职责：合并 主板(import_final.json) + 双创(chuang_signals.json) + 三周期(sanqizhou_report.json)
//       三支选股模块的输出，按 code 去重（同一标的可能被多模块选中），
//       用统一「适应度 fitness = 模块原生评分 × 验证系数」全局排名，
//       保留前 CAP(50) 支作为总选股池，其余判为淘汰（优胜劣汰），
//       产出 选股结果/unified_selection.json，供 stock-selection-system.html 的「优中选优」Tab 渲染。
//
// 验证系数 EDGE 含义（反映各模块回测验证可信度，可调）：
//   main   1.00 — 主板 main_only 回测期望 +0.59%/笔、PF 1.45，已转正；
//   tri    0.90 — 三周期仅多周期共振研究参考，未经回测验证；
//   chuang 0.75 — 双创全市场回测期望为负，仅作预警/研究，系数下调使其需更高原生分才能挤入 50。
// 说明：本脚本只做「跨模块汇总排名 + 硬上限」，不改动任何模块自身选股逻辑。

const fs = require('fs');
const path = require('path');

const ROOT = 'D:/WorkBuddy';
const SEL = path.join(ROOT, '选股结果');
const OUT = path.join(SEL, 'unified_selection.json');

const CAP = 50;                                    // 总选股硬上限：主板+双创+三周期 合计 ≤ 50
const EDGE = { main: 1.0, tri: 0.9, chuang: 0.75 }; // 验证系数（可信度权重）

function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }

function loadJson(f) {
  const p = path.join(SEL, f);
  if (!fs.existsSync(p)) { console.warn('[skip] 缺失', f); return null; }
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); }
  catch (e) { console.warn('[skip] 解析失败', f, e.message); return null; }
}

// —— 主板（import_final.json）——
function fromMain(d) {
  const arr = (d && d.items) || [];
  return arr
    .map(x => ({
      code: x.code, name: x.name, board: x.board,
      nativeScore: typeof x.score === 'number' ? x.score : 0,
      win: typeof x.win === 'number' ? x.win : null,
      entry: x.entry, stop: x.stopPrice, target: x.targetPrice,
      reasons: (Array.isArray(x.reasons) && x.reasons.length) ? x.reasons : [x.category || x.sector || ''].filter(Boolean),
      source: 'main',
    }))
    .filter(r => r.code);
}

// —— 双创（chuang_signals.json → buys）——
// 该模块无 0–100 原生评分，按信号自身属性派生：已了结胜/负 + 仓位置信度 + 市况。
function fromChuang(d) {
  const arr = (d && d.buys) || [];
  return arr
    .map(x => {
      const resolved = x.resolved && x.resolved.outcome; // 'win' | 'loss' | ...
      let sc = 50;
      if (resolved === 'win') sc += 22;
      else if (resolved === 'loss') sc -= 16;
      const pos = typeof x.positionPct === 'number' ? x.positionPct : 0;
      sc += Math.min(22, pos * 380);                      // 仓位越重=模型置信越高
      if (x.regime && x.regime !== 'n/a') sc += 3;
      return {
        code: x.code, name: x.name, board: x.board,
        nativeScore: clamp(Math.round(sc), 0, 100),
        win: resolved === 'win' ? 100 : (resolved === 'loss' ? 0 : null),
        entry: x.entry, stop: x.stopLoss, target: x.takeProfit,
        reasons: Array.isArray(x.reasons) ? x.reasons : [],
        source: 'chuang',
      };
    })
    .filter(r => r.code);
}

// —— 三周期（sanqizhou_report.json → stocks）——
function fromTri(d) {
  const arr = (d && d.stocks) || [];
  return arr
    .map(x => ({
      code: x.code, name: x.name, board: x.board,
      nativeScore: typeof x.score === 'number' ? x.score : 0,
      win: null,
      entry: x.entry, stop: x.stopLoss, target: x.target,
      reasons: Array.isArray(x.reasons) ? x.reasons : [],
      source: 'tri',
      cycle: { month: x.month, week: x.week, day: x.day },
    }))
    .filter(r => r.code);
}

function main() {
  const main = fromMain(loadJson('import_final.json'));
  const chuang = fromChuang(loadJson('chuang_signals.json'));
  const tri = fromTri(loadJson('sanqizhou_report.json'));
  console.log(`加载: 主板 ${main.length} | 双创 ${chuang.length} | 三周期 ${tri.length}`);

  // 合并 + 按 code 去重（保留最高适应度，记录全部来源模块）
  const byCode = {};
  for (const r of [...main, ...chuang, ...tri]) {
    const fit = r.nativeScore * EDGE[r.source];
    if (!byCode[r.code]) {
      byCode[r.code] = Object.assign({}, r, { fitness: fit, bestSource: r.source, sources: [r.source] });
    } else {
      const cur = byCode[r.code];
      cur.sources.push(r.source);
      if (fit > cur.fitness) { cur.fitness = fit; cur.bestSource = r.source; }
      if (r.cycle && !cur.cycle) cur.cycle = r.cycle;
    }
  }

  const all = Object.values(byCode);
  const dedupTotal = all.length;
  all.sort((a, b) => b.fitness - a.fitness);

  const survived = all.slice(0, CAP);
  const eliminated = all.slice(CAP);
  const srcCnt = s => survived.filter(x => x.sources.includes(s)).length;

  const stocks = survived.map((x, i) => ({
    rank: i + 1,
    code: x.code, name: x.name, board: x.board,
    sources: Array.from(new Set(x.sources)),
    nativeScore: x.nativeScore,
    edge: EDGE[x.bestSource],
    fitness: Math.round(x.fitness * 10) / 10,
    win: x.win,
    entry: x.entry, stop: x.stop, target: x.target,
    reasons: x.reasons || [],
    cycle: x.cycle || null,
  }));

  const elim = eliminated.map(x => ({
    code: x.code, name: x.name, board: x.board,
    sources: Array.from(new Set(x.sources)),
    nativeScore: x.nativeScore,
    fitness: Math.round(x.fitness * 10) / 10,
  }));

  const report = {
    generatedAt: new Date().toISOString().slice(0, 10),
    cap: CAP,
    dedupTotal,
    survived: stocks.length,
    eliminated: elim.length,
    sources: { main: srcCnt('main'), chuang: srcCnt('chuang'), tri: srcCnt('tri') },
    edge: EDGE,
    stocks,
    eliminated: elim,
  };

  fs.writeFileSync(OUT, JSON.stringify(report, null, 2), 'utf8');
  console.log('✅ 已生成', OUT);
  console.log(`   去重后合计 ${dedupTotal} | 入选 ${stocks.length} | 淘汰 ${elim.length} | 来源: 主板${report.sources.main} 双创${report.sources.chuang} 三周期${report.sources.tri}`);
  if (stocks.length) console.log('   头部:', stocks.slice(0, 3).map(s => `${s.name}(${s.code}) 适应度${s.fitness}`).join(' | '));
}

main();
