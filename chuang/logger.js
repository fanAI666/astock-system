'use strict';
// chuang/logger.js — 统一日志与错误处理
// 分级日志：DEBUG < INFO < WARN < ERROR；默认 INFO。可通过 LOG_LEVEL env 控制。
// 提供 withError 包装器，统一 try/catch + 记录 + 返回兜底值，避免单点异常中断整轮回测。

const LEVELS = { DEBUG: 10, INFO: 20, WARN: 30, ERROR: 40 };
const curLevel = LEVELS[(process.env.LOG_LEVEL || 'INFO').toUpperCase()] || LEVELS.INFO;

function ts() {
  const d = new Date();
  return d.toISOString().slice(11, 23); // HH:MM:SS.mmm
}

function log(level, tag, msg) {
  if (LEVELS[level] < curLevel) return;
  const head = `${ts()} [${level.padEnd(5)}] ${tag ? '[' + tag + '] ' : ''}`;
  if (level === 'ERROR') console.error(head + msg);
  else if (level === 'WARN') console.warn(head + msg);
  else console.log(head + msg);
}

const Logger = {
  debug: (tag, msg) => log('DEBUG', tag, msg),
  info: (tag, msg) => log('INFO', tag, msg),
  warn: (tag, msg) => log('WARN', tag, msg),
  error: (tag, msg) => log('ERROR', tag, msg),
  // 进度条式单行（覆盖上一行）：用于长循环（如宇宙抓取）
  progress: (tag, msg) => {
    if (LEVELS.INFO < curLevel) return;
    process.stdout.write(`\r${ts()} [INFO] ${tag ? '[' + tag + '] ' : ''}${msg}`);
  },
  // 包裹函数：异常时记录并返回 fallback（不抛出）
  withError: async (fn, tag, fallback, ...args) => {
    try { return await fn(...args); }
    catch (e) {
      log('ERROR', tag, `异常(${e.message})，返回兜底值`);
      if (process.env.LOG_STACK) log('DEBUG', tag, e.stack || '');
      return fallback;
    }
  },
  // 同步版包裹
  withErrorSync: (fn, tag, fallback, ...args) => {
    try { return fn(...args); }
    catch (e) {
      log('ERROR', tag, `异常(${e.message})，返回兜底值`);
      if (process.env.LOG_STACK) log('DEBUG', tag, e.stack || '');
      return fallback;
    }
  },
};

module.exports = { Logger, LEVELS };
