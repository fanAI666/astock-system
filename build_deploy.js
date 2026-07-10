const fs = require('fs');
const path = require('path');

const SRC = 'D:/WorkBuddy/stock-selection-system.html';
const OUT_DIR = 'D:/WorkBuddy/deploy';
const DATA_DIR = path.join(OUT_DIR, 'data');

const GATE_CSS = `
#gate{position:fixed;inset:0;z-index:9999;background:rgba(15,23,42,.93);backdrop-filter:blur(6px);display:flex;align-items:center;justify-content:center;font-family:system-ui,'Microsoft YaHei','PingFang SC',sans-serif}
#gate .box{background:#fff;padding:30px 34px;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,.35);text-align:center;max-width:320px;width:86%}
#gate h3{margin:0 0 6px;color:#0f172a;font-size:19px}
#gate p{margin:0 0 16px;color:#64748b;font-size:13px}
#gate input{width:100%;padding:11px 12px;border:1px solid #cbd5e1;border-radius:9px;font-size:15px;box-sizing:border-box;outline:none}
#gate input:focus{border-color:#2563eb}
#gate button{margin-top:14px;width:100%;padding:11px;border:0;border-radius:9px;background:#2563eb;color:#fff;font-size:15px;cursor:pointer}
#gate button:hover{background:#1d4ed8}
#gate .err{color:#dc2626;font-size:12.5px;min-height:17px;margin-top:9px}`;

const GATE_DIV = `<div id="gate"><div class="box"><h3>访问保护</h3><p>请输入访问口令后进入</p><input id="gatePw" type="password" placeholder="访问口令" autocomplete="off"><div class="err" id="gateErr"></div><button id="gateBtn">进入系统</button></div></div>`;

const GATE_JS = `<script>
(function(){
  var PW='stock2026';
  function open(){var v=document.getElementById('gatePw').value;if(v===PW){document.getElementById('gate').style.display='none';}else{document.getElementById('gateErr').textContent='口令错误，请重试';}}
  document.getElementById('gateBtn').addEventListener('click',open);
  document.getElementById('gatePw').addEventListener('keydown',function(e){if(e.key==='Enter')open();});
  document.getElementById('gatePw').focus();
})();
<\/script>`;

fs.mkdirSync(DATA_DIR, { recursive: true });
let html = fs.readFileSync(SRC, 'utf8');

// 1) 数据路径：选股结果/ -> data/
const before = (html.match(/选股结果\//g) || []).length;
html = html.split('选股结果/').join('data/');

// 2) 注入访问口令保护（与本地 serve.js 口令一致）
html = html.replace('</style>', GATE_CSS + '\n</style>');
html = html.replace(/<body[^>]*>/, m => m + '\n' + GATE_DIV);
html = html.replace('</body>', GATE_JS + '\n</body>');

fs.writeFileSync(path.join(OUT_DIR, 'index.html'), html, 'utf8');

// 3) 复制数据快照
for (const f of ['import_pre.json', 'import_final.json']) {
  fs.copyFileSync(path.join('D:/WorkBuddy/选股结果', f), path.join(DATA_DIR, f));
}

console.log('build done. 替换选股结果/ 次数 =', before);
console.log('deploy/index.html size =', fs.statSync(path.join(OUT_DIR,'index.html')).size);
console.log('data files =', fs.readdirSync(DATA_DIR));
console.log('gate injected =', html.includes('id="gate"'), '| path replaced =', html.includes('data/import_final.json'));
