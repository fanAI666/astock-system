const fs = require('fs');
const path = require('path');

// 部署前先从最新简报 markdown 重新生成 briefing_*.json（若不存在则跳过）
try { require('./build_briefings.js'); } catch (e) { console.log('build_briefings 跳过:', e.message); }

// 路径改为相对仓库根(__dirname)，使本地与 GitHub Actions(Linux) 均可运行
const SRC = path.join(__dirname, 'stock-selection-system.html');
const OUT_DIR = path.join(__dirname, 'deploy');
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
#gate .err{color:#dc2626;font-size:12.5px;min-height:17px;margin-top:9px}
#gateRememberWrap{display:flex;align-items:center;gap:7px;margin-top:13px;font-size:13px;color:#475569;justify-content:flex-start;cursor:pointer}
#gateRememberWrap input{width:auto;margin:0;cursor:pointer}
#gateForgot{display:inline-block;margin-top:11px;font-size:12px;color:#2563eb;cursor:pointer;text-decoration:underline}
#gateLogout{position:fixed;right:12px;bottom:12px;z-index:9998;font-size:12px;color:#64748b;background:rgba(255,255,255,.92);border:1px solid #e2e8f0;border-radius:8px;padding:5px 11px;cursor:pointer;display:none;font-family:system-ui,'Microsoft YaHei',sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.08)}
#gateLogout:hover{border-color:#94a3b8;color:#334155}`;

const GATE_DIV = `<div id="gate"><div class="box"><h3>访问保护</h3><p>请输入访问口令后进入</p><input id="gatePw" type="password" placeholder="访问口令" autocomplete="off"><label id="gateRememberWrap"><input type="checkbox" id="gateRemember"> 在本机记住我（下次免口令）</label><div class="err" id="gateErr"></div><button id="gateBtn">进入系统</button><span id="gateForgot">清除本机记住</span></div></div>`;

const GATE_JS = `<script>
(function(){
  var PW='stock2026';
  var REM='astock_remember';
  // 口令散列后存储，避免明文落盘（纯前端 gate 仅作遮挡，无真实安全边界）
  function token(){var s=PW+'::astock-salt',h=0;for(var i=0;i<s.length;i++){h=(h*31+s.charCodeAt(i))>>>0;}return 't'+h.toString(16);}
  var gate=document.getElementById('gate');
  function showLogout(){var lb=document.getElementById('gateLogout');if(lb)lb.style.display='inline-block';}
  function hideGate(){gate.style.display='none';showLogout();}
  function relock(){try{localStorage.removeItem(REM);}catch(e){}gate.style.display='flex';var lb=document.getElementById('gateLogout');if(lb)lb.style.display='none';var pw=document.getElementById('gatePw');if(pw)pw.value='';var err=document.getElementById('gateErr');if(err)err.textContent='';var rm=document.getElementById('gateRemember');if(rm)rm.checked=false;}
  function open(){
    var v=document.getElementById('gatePw').value;
    if(v===PW){
      hideGate();
      var rm=document.getElementById('gateRemember');
      try{ if(rm&&rm.checked){localStorage.setItem(REM,token());}else{localStorage.removeItem(REM);} }catch(e){}
    }else{
      document.getElementById('gateErr').textContent='口令错误，请重试';
    }
  }
  // 浮动退出按钮（动态注入，免改 HTML 结构）
  var lb=document.createElement('div');
  lb.id='gateLogout';lb.textContent='退出登录';
  lb.addEventListener('click',relock);
  document.body.appendChild(lb);
  // 自动登录：本机已记住且口令未变更
  try{ if(localStorage.getItem(REM)===token()){hideGate();} }catch(e){}
  document.getElementById('gateBtn').addEventListener('click',open);
  var pw=document.getElementById('gatePw');
  pw.addEventListener('keydown',function(e){if(e.key==='Enter')open();});
  var forgot=document.getElementById('gateForgot');
  if(forgot)forgot.addEventListener('click',relock);
  if(gate.style.display!=='none')pw.focus();
})();
<\/script>`;

fs.mkdirSync(DATA_DIR, { recursive: true });
// 写入 .nojekyll，确保 GitHub Pages 以纯静态方式托管（不启用 Jekyll）
fs.writeFileSync(path.join(OUT_DIR, '.nojekyll'), '');
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
  fs.copyFileSync(path.join(__dirname, '选股结果', f), path.join(DATA_DIR, f));
}
// 3.5) 复制买入信号（若存在）
const sigSrc = path.join(__dirname, '选股结果', 'buy_signal.json');
if (fs.existsSync(sigSrc)) {
  fs.copyFileSync(sigSrc, path.join(DATA_DIR, 'buy_signal.json'));
  console.log('buy_signal.json copied');
} else {
  console.log('buy_signal.json 不存在（跳过）');
}
// 3.6) 复制交易胜率回测结果（主板 main_only + 双创独立体系，若存在）
for (const f of ['backtest_phase12.json', 'backtest_chuang.json']) {
  const wrSrc = path.join(__dirname, '选股结果', f);
  if (fs.existsSync(wrSrc)) {
    fs.copyFileSync(wrSrc, path.join(DATA_DIR, f));
    console.log(f + ' copied');
  } else {
    console.log(f + ' 不存在（跳过）');
  }
}
// 3.7) 复制每日简报（预选 + 盘后，若存在）
for (const f of ['briefing_pre.json', 'briefing_final.json']) {
  const src = path.join(__dirname, '选股结果', f);
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, path.join(DATA_DIR, f));
    console.log(f + ' copied');
  } else {
    console.log(f + ' 不存在（跳过，请先运行 build_briefings.js）');
  }
}
// 3.75) 复制盘后真实资金流向（若存在）
const ffSrc = path.join(__dirname, '选股结果', 'fundflow.json');
if (fs.existsSync(ffSrc)) {
  fs.copyFileSync(ffSrc, path.join(DATA_DIR, 'fundflow.json'));
  console.log('fundflow.json copied');
} else {
  console.log('fundflow.json 不存在（跳过，请先运行 fetch_fundflow.py）');
}
// 3.85) 复制版本状态文件（机器可读，供站点/监控读取当前版本）
const verSrc = path.join(__dirname, 'VERSION.json');
if (fs.existsSync(verSrc)) {
  fs.copyFileSync(verSrc, path.join(DATA_DIR, 'VERSION.json'));
  console.log('VERSION.json copied -> data/');
} else {
  console.log('VERSION.json 不存在（跳过）');
}
// 3.86) 复制项目文档到站点根目录（使 CHANGELOG.md / README.md / VERSION.json 在 GitHub Pages 站点根可直接访问）
for (const f of ['VERSION.json', 'CHANGELOG.md', 'README.md']) {
  const docSrc = path.join(__dirname, f);
  if (fs.existsSync(docSrc)) {
    fs.copyFileSync(docSrc, path.join(OUT_DIR, f));
    console.log('站点根文档 copied -> ' + f);
  } else {
    console.log('站点根文档跳过（不存在）: ' + f);
  }
}
// 3.8) 复制单文件离线版（数据内嵌，供站点下载）
const offSrc = path.join(__dirname, '选股系统_离线版.html');
if (fs.existsSync(offSrc)) {
  fs.copyFileSync(offSrc, path.join(OUT_DIR, '选股系统_离线版.html'));
  console.log('选股系统_离线版.html copied');
} else {
  console.log('选股系统_离线版.html 不存在（跳过，请先运行 package_singlefile.js）');
}

console.log('build done. 替换选股结果/ 次数 =', before);
console.log('deploy/index.html size =', fs.statSync(path.join(OUT_DIR,'index.html')).size);
console.log('data files =', fs.readdirSync(DATA_DIR));
console.log('gate injected =', html.includes('id="gate"'), '| path replaced =', html.includes('data/import_final.json'));
