// build_briefings.js
// 将「选股结果/」下按日期生成的简报 markdown 包装成系统可读取的稳定 JSON：
//   briefing_final.json (盘后定稿简报, 最新 YYYY-MM-DD.md)
//   注：预选简报(briefing_pre.json)已停用，不再生成。
// 页面 fetch 这两个固定文件名即可，无需关心每日文件名变化。
const fs = require('fs');
const path = require('path');

const DIR = 'D:/WorkBuddy/选股结果';

function parseBrief(file) {
  const raw = fs.readFileSync(path.join(DIR, file), 'utf8');
  const lines = raw.split(/\r?\n/);
  const full = raw;

  // 文档标题：第一个 # 行
  let title = '';
  const tIdx = lines.findIndex(l => /^#\s+/.test(l));
  if (tIdx >= 0) title = lines[tIdx].replace(/^#\s+/, '').trim();

  // 报告日期（标题括号里第一个 YYYY-MM-DD）
  const dateM = title.match(/(\d{4}-\d{2}-\d{2})/);
  const date = dateM ? dateM[1] : '';

  // 数据日（兼容半角/全角冒号）
  const ddM = full.match(/数据日[：:]\s*(\d{4}-\d{2}-\d{2})/);
  const dataDate = ddM ? ddM[1] : '';

  // 生成时间
  const gM = full.match(/生成时间[：:]\s*([^｜|]+)/);
  const generatedAt = gM ? gM[1].trim() : '';

  // 风险提示标识
  const warning = /[⚠❗]|警示/.test(full);

  // 正文：去掉首个 H1 标题行及其前后空行
  let body = lines.slice();
  if (tIdx >= 0) body.splice(tIdx, 1);
  while (body.length && body[0].trim() === '') body.shift();
  while (body.length && body[body.length - 1].trim() === '') body.pop();
  const md = body.join('\n');

  return { title, date, dataDate, generatedAt, warning, md };
}

function latest(re) {
  const files = fs.readdirSync(DIR).filter(f => re.test(f));
  if (!files.length) return null;
  files.sort(); // ISO 日期字符串升序，取最后一个即最新
  return files[files.length - 1];
}

function write(name, file) {
  if (!file) { console.log(`跳过 ${name}：未找到对应 markdown`); return; }
  const b = parseBrief(file);
  const out = { type: 'final',
    file, title: b.title, date: b.date, dataDate: b.dataDate,
    generatedAt: b.generatedAt, warning: b.warning, md: b.md };
  fs.writeFileSync(path.join(DIR, name), JSON.stringify(out, null, 2), 'utf8');
  console.log(`写出 ${name}（源=${file}, 日期=${b.date||'-'}, 预警=${b.warning}, 正文 ${b.md.length} 字）`);
}

const finalFile = latest(/^\d{4}-\d{2}-\d{2}\.md$/);

write('briefing_final.json', finalFile);
console.log('briefings 构建完成（仅盘后定稿，预选简报已停用）。');
