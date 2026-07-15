#!/usr/bin/env node
// version_bump.js — 按既定规则推进系统版本号
//
// 规则（见 README 第一章）：
//   以 1.0.0 为基准；每新增 1 个功能点 +0.0.1；
//   满 10 个点进 1（即 0.0.9 → 0.1.0，相对基准为 1.0.9 → 1.1.0）；
//   满 10 个次版本进 1（1.9.0 → 2.0.0）。
//   版本号 = 基准主版本 + 功能点数按 10 进 1 进位。
//
// 用法：
//   node version_bump.js "本次新增功能描述"        // +1 功能点
//   node version_bump.js 3 "本次新增 3 个功能"     // +3 功能点（N 范围 1–10）
//
// 作用：更新 VERSION.json（机器状态）与 CHANGELOG.md（人类日志）。

const fs = require('fs');
const path = require('path');

const VF = path.join(__dirname, 'VERSION.json');
const CL = path.join(__dirname, 'CHANGELOG.md');

// ---- 解析参数 ----
const args = process.argv.slice(2);
let n = 1;
let desc = '';
if (args.length && /^\d+$/.test(args[0])) {
  n = parseInt(args[0], 10);
  desc = args.slice(1).join(' ').trim();
} else {
  desc = args.join(' ').trim();
}
if (!Number.isInteger(n) || n < 1 || n > 10) {
  console.error('用法: node version_bump.js [N=1..10] "功能描述"');
  process.exit(1);
}
if (!desc) {
  console.error('请提供本次新增功能描述。');
  process.exit(1);
}

// ---- 读取状态 ----
let state;
try {
  state = JSON.parse(fs.readFileSync(VF, 'utf8'));
} catch (e) {
  console.error('无法读取 VERSION.json:', e.message);
  process.exit(1);
}

const BASE = state.baseVersion || '1.0.0';
const baseMaj = parseInt(BASE.split('.')[0], 10);
const points = (state.featurePoints || 0) + n;

function verOf(p) {
  const major = baseMaj + Math.floor(p / 100);
  const minor = Math.floor(p / 10) % 10;
  const patch = p % 10;
  return `${major}.${minor}.${patch}`;
}

const newVer = verOf(points);
const date = new Date().toISOString().slice(0, 10);

// ---- 写 VERSION.json ----
state.featurePoints = points;
state.version = newVer;
state.history = state.history || [];
state.history.push({ version: newVer, date, points: n, desc });
fs.writeFileSync(VF, JSON.stringify(state, null, 2) + '\n', 'utf8');

// ---- 更新 CHANGELOG.md ----
let log = '';
try { log = fs.readFileSync(CL, 'utf8'); } catch (e) { log = ''; }
if (!log.trim().startsWith('#')) {
  log = '# 版本变更日志\n\n## 历史\n\n' + log;
}
const entry = `- **v${newVer}** (${date}) +${n} 功能点：${desc}\n`;
const idx = log.indexOf('\n## ');
if (idx === -1) {
  log = log.replace(/\n*$/, '\n') + entry;
} else {
  log = log.slice(0, idx) + entry + log.slice(idx);
}
fs.writeFileSync(CL, log, 'utf8');

console.log(`✓ 版本已推进：${BASE} + ${points} 功能点 → v${newVer}`);
console.log(`  本次 +${n}：${desc}`);
