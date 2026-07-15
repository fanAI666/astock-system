/**
 * package_singlefile.js
 * 生成「单文件离线版」选股系统：把数据内嵌进 HTML，双击浏览器即可打开，
 * 零安装 / 零 .NET / 零联网。源码仍走 http 在线版，互不影响。
 *
 * 用法：node package_singlefile.js
 * 产出：D:/WorkBuddy/选股系统_离线版.html
 */
const fs = require('fs');
const path = require('path');

const SRC = 'D:/WorkBuddy/stock-selection-system.html';
const DATA_DIR = 'D:/WorkBuddy/选股结果';
const OUT = 'D:/WorkBuddy/选股系统_离线版.html';

// 需要内嵌的数据文件（键名 = 离线 loader 读取的 EMBED_DATA 键）
const EMBED_MAP = {
  import_final:      'import_final.json',
  backtest_winrate: 'backtest_winrate.json',
  backtest_midfreq: 'backtest_midfreq.json',
  briefing_final:    'briefing_final.json',
  buy_signal:       'buy_signal.json',
};

function loadJSON(name) {
  const p = path.join(DATA_DIR, name);
  if (!fs.existsSync(p)) { console.log('⚠️ 跳过（缺失）: ' + name); return null; }
  try {
    const obj = JSON.parse(fs.readFileSync(p, 'utf8'));
    const sizeKB = (fs.statSync(p).size / 1024).toFixed(0);
    console.log('  ✓ ' + name + '  (' + sizeKB + ' KB)');
    return obj;
  } catch (e) {
    console.log('⚠️ 解析失败: ' + name + ' → ' + e.message);
    return null;
  }
}

console.log('==> 读取内嵌数据');
const EMBED_DATA = {};
for (const [key, file] of Object.entries(EMBED_MAP)) {
  const obj = loadJSON(file);
  if (obj) EMBED_DATA[key] = obj;
}

// 把 JSON 注入 <script>，并转义 </script 防止提前闭合
const jsonStr = JSON.stringify(EMBED_DATA).replace(/<\/script/gi, '<\\/script');
const embedScript =
  '\n<!-- ===== 离线内嵌数据包（package_singlefile.js 自动生成） ===== -->\n' +
  '<script>window.EMBED_DATA=' + jsonStr + ';</script>\n';

console.log('==> 读取源码 HTML');
let html = fs.readFileSync(SRC, 'utf8');

// 1) 注入内嵌数据（放到 <body> 之后，确保在主脚本执行前定义）
if (!html.includes('window.EMBED_DATA=')) {
  html = html.replace('<body>', '<body>' + embedScript);
} else {
  console.log('⚠️ 源码已含 EMBED_DATA，疑似重复打包');
}

// 2) 给 4 个 loader + 初始化行打补丁（file:// 优先读内嵌，http 回退 fetch）
const patches = [
  {
    name: 'importToday',
    from: 'const files=["选股结果/import_final.json"];',
    to:   'const files=["选股结果/import_final.json"];\n' +
          '  if(window.EMBED_DATA&&window.EMBED_DATA.import_final){ showImportMsg(mergeItems(window.EMBED_DATA.import_final.items)); return; }',
  },
  {
    name: 'loadBuySignal',
    from: 'if(location.protocol.indexOf("http")!==0){ renderTrigger(); renderBuySignal(); return; }',
    to:   'if(window.EMBED_DATA&&window.EMBED_DATA.buy_signal){ window.buySignal=window.EMBED_DATA.buy_signal; renderTrigger(); renderBuySignal(); return; }\n' +
          '  if(location.protocol.indexOf("http")!==0){ renderTrigger(); renderBuySignal(); return; }',
  },
  {
    name: 'loadWinRate',
    from: "if(location.protocol.indexOf('http')!==0){ return; } // file:// 下无 fetch，留占位",
    to:   "const __df = MODE_CONFIG[currentMode].dataFile; const __emb=__df.replace(/\\.json$/,'');\n" +
          "  if(window.EMBED_DATA&&window.EMBED_DATA[__emb]){ renderWinRate(window.EMBED_DATA[__emb]); return; }\n" +
          "  if(location.protocol.indexOf('http')!==0){ return; } // file:// 下无 fetch，留占位",
  },
  {
    name: 'loadBriefings',
    from: 'if(location.protocol.indexOf("http")!==0) return; // file:// 下无 fetch，留占位',
    to:   "if(window.EMBED_DATA&&window.EMBED_DATA.briefing_final){ renderBriefCard('final', window.EMBED_DATA.briefing_final); return; }\n" +
          '  if(location.protocol.indexOf("http")!==0) return; // file:// 下无 fetch，留占位',
  },
  {
    name: 'init',
    from: 'if(location.protocol.indexOf("http")===0){ importToday(); loadBuySignal(); loadWinRate(); loadBriefings(); }',
    to:   'importToday(); loadBuySignal(); loadWinRate(); loadBriefings();',
  },
];

let allOk = true;
for (const p of patches) {
  if (html.includes(p.from)) {
    html = html.replace(p.from, p.to);
    console.log('  ✓ 补丁生效: ' + p.name);
  } else {
    console.log('  ❌ 未找到锚点: ' + p.name + '（可能源码已变，需同步本脚本）');
    allOk = false;
  }
}

if (!allOk) {
  console.log('\n✗ 部分补丁未生效，已中止写入以免产出半残文件');
  process.exit(1);
}

fs.writeFileSync(OUT, html, 'utf8');
const outKB = (fs.statSync(OUT).size / 1024 / 1024).toFixed(2);
console.log('\n==> 已生成: ' + OUT + '  (' + outKB + ' MB)');
console.log('==> 双击即可在浏览器打开，数据全部内嵌，无需联网/安装');
