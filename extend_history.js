// extend_history.js — 用通达信(TDX) MCP 拉取的 320 根真实日线，
// 替换 import_final.json 中各候选股的 kline.day（原仅 70 根，2026-03 起）。
// 同时把上证指数 000001 单独存出，供 ⑤ 大盘硬过滤使用。
//
// 列映射（TDX Rows 对象 → backtest bar）：
//   bar = [ date, open, close, high, low, volume ]
//   Data→日期, Open→开, Close→收, High→高, Low→低, Volume→量
// 与 import_final.json 既有 kline.day 格式完全一致（date 为 "YYYYMMDD" 字符串）。

const fs = require('fs');
const path = require('path');

// 仅刷新指数模式：ONLY_INDEX=1 node extend_history.js 只重写 index_sh.json，
// 不覆盖 import_final.json 的个股 kline（避免误伤已校准的候选数据）。
const ONLY_INDEX = process.env.ONLY_INDEX === '1';

// tdx 缓存按会话分散在 d-WorkBuddy/<sessionId>/tool-results/ 下。
// 硬编码单目录会漏掉新会话的缓存（如 rebuild_index.py 拉的 440 根上证），
// 故扫描所有 session 的 tool-results；并保留兜底旧路径以防 glob 落空。
const TOOL_BASE = 'C:/Users/fanfan/.workbuddy/projects/d-WorkBuddy';
const TOOL_DIRS = (() => {
  const dirs = [];
  try {
    for (const proj of fs.readdirSync(TOOL_BASE)) {
      const p = path.join(TOOL_BASE, proj, 'tool-results');
      if (fs.existsSync(p) && fs.statSync(p).isDirectory()) dirs.push(p);
    }
  } catch (e) {}
  return dirs.length ? dirs
    : ['C:/Users/fanfan/.workbuddy/projects/d-WorkBuddy/e0b70369-9b1d-4187-a9f3-62e9dcb5fced/tool-results'];
})();
const SRC = 'D:/WorkBuddy/选股结果/import_final.json';
const BAK = 'D:/WorkBuddy/选股结果/import_final.bak';
const INDEX_OUT = 'D:/WorkBuddy/选股结果/index_sh.json';

// 上证指数识别：TDX 中 Code='000001' 在 setcode=0(深交所)时为【平安银行】，
// 在 setcode=1(上交所)时才为【上证指数】。单靠 Code 会误把平安银行当上证写出
// （历史错标指数即源于此：缓存里存在 Setcode=None/0、Name=平安银行、Code=000001 的文件）。
// 故必须按 Setcode+Code 精确识别，并以 Name 关键字兜底，再用量纲守卫双保险。
const SH_INDEX_NAME_KW = '上证';
const SH_INDEX_SETCODE = '1';   // 上交所
const SH_INDEX_CODE = '000001';
let shIndexCand = null;          // 上证指数候选（取最长序列）

// 1) 扫描所有 tdx 文件，按 Code 聚合（保留最长序列）
const files = [];
for (const d of TOOL_DIRS) {
  for (const f of fs.readdirSync(d)) if (f.includes('tdx_kline')) files.push(path.join(d, f));
}
const byCode = {}; // code -> { name, bars:[[...]] }

for (const f of files) {
  const txt = fs.readFileSync(f, 'utf8');
  const j = txt.indexOf('{');
  if (j < 0) continue;
  let obj; try { obj = JSON.parse(txt.slice(j)); } catch (e) { continue; }
  const code = obj.Code;
  if (!code) continue;
  const rows = obj.Rows || [];
  if (!rows.length) continue;
  const setcode = obj.Setcode;                       // 关键：区分同 Code 不同市场
  const idxName = obj.AttachInfo && obj.AttachInfo.Name;

  const bars = [];
  const seen = new Set();
  for (const r of rows) {
    const d = String(r.Data);
    if (!d || seen.has(d)) continue;
    const open = parseFloat(r.Open), close = parseFloat(r.Close),
          high = parseFloat(r.High), low = parseFloat(r.Low);
    let vol = parseFloat(r.Volume);
    if (!isFinite(vol)) vol = (parseFloat(r.RawVolume) || 0) / 100;
    if (![open, close, high, low].every(isFinite)) continue;
    seen.add(d);
    bars.push([d, +open.toFixed(4), +close.toFixed(4), +high.toFixed(4), +low.toFixed(4), +vol.toFixed(2)]);
  }
  bars.sort((a, b) => (a[0] < b[0] ? -1 : 1));

  if (!byCode[code] || byCode[code].bars.length < bars.length) {
    byCode[code] = { name: idxName, bars };
  }
  // 识别上证指数：setcode=1 且 code=000001，或名称含"上证"。取最长序列作为候选。
  const isShIndex = (String(setcode) === SH_INDEX_SETCODE && String(code) === SH_INDEX_CODE) ||
                    (typeof idxName === 'string' && idxName.includes(SH_INDEX_NAME_KW));
  if (isShIndex && (!shIndexCand || shIndexCand.bars.length < bars.length)) {
    shIndexCand = { code, name: idxName || '上证指数', board: 'index', setcode, bars };
  }
}
console.log('解析到代码:', Object.keys(byCode).join(', '));

// 2) 上证指数单独存出（精确识别 + 量纲守卫，杜绝平安银行等个股误写）
let indexSaved = null;
if (shIndexCand) {
  const closes = shIndexCand.bars.map(b => b[2]);
  const med = closes.slice().sort((a, b) => a - b)[Math.floor(closes.length / 2)];
  if (med < 1000) {
    // 量级异常：真实上证收盘长期在 2000~6000，平安银行等个股仅 ~10~20
    console.log(`⚠ 上证指数量级异常(中位收盘 ${med.toFixed(2)})，疑似个股非指数，拒绝写出 ${INDEX_OUT}`);
  } else {
    const out = {
      code: shIndexCand.code,
      name: shIndexCand.name || '上证指数',
      board: 'index',
      setcode: shIndexCand.setcode,
      bars: shIndexCand.bars,
      updated: new Date().toISOString().slice(0, 10)
    };
    fs.writeFileSync(INDEX_OUT, JSON.stringify(out, null, 2), 'utf8');
    indexSaved = { code: out.code, name: out.name, bars: out.bars.length };
    console.log(`上证指数已存: ${out.name} (setcode=${out.setcode}, ${out.bars.length} 根, ${out.bars[0][0]}~${out.bars[out.bars.length-1][0]}, 中位收盘 ${med.toFixed(2)})`);
  }
}
if (!indexSaved) console.log('⚠ 未找到上证指数(000001, setcode=1)数据');

// 3) 替换 import_final.json 各票 kline.day
if (ONLY_INDEX) {
  console.log('（ONLY_INDEX=1，跳过个股 kline 替换，仅刷新指数）');
} else {
const data = JSON.parse(fs.readFileSync(SRC, 'utf8'));
fs.copyFileSync(SRC, BAK); // 备份原 70 根版本
const items = data.items || [];
let matched = 0, totalBars = 0, minBars = 1e9, maxBars = 0;
for (const s of items) {
  const hit = byCode[s.code];
  if (!hit) { console.log(`⚠ 未匹配到 TDX 数据: ${s.code} ${s.name}`); continue; }
  s.kline = s.kline || {};
  s.kline.day = hit.bars;
  matched++;
  totalBars += hit.bars.length;
  minBars = Math.min(minBars, hit.bars.length);
  maxBars = Math.max(maxBars, hit.bars.length);
}
data.updated = new Date().toISOString();
fs.writeFileSync(SRC, JSON.stringify(data), 'utf8'); // 紧凑写回（面板读取无影响）

console.log(`\n替换完成: ${matched}/${items.length} 支匹配`);
console.log(`每票根数: min=${minBars}, max=${maxBars}, 均值=${(totalBars/matched).toFixed(0)}`);
console.log(`备份原文件 → ${BAK}`);
console.log(`新文件大小: ${(fs.statSync(SRC).size/1024).toFixed(1)} KB (原 ${(fs.statSync(BAK).size/1024).toFixed(1)} KB)`);
}
