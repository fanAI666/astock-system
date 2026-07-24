// 选股系统发布服务器
// 用法:
//   node serve.js                                正常启动(无口令)
//   SITE_TOKEN=你的口令 node serve.js           启用口令保护
//   node serve.js --token 你的口令              (同上, 命令行方式)
//   PORT=9000 node serve.js                    自定义端口
const http = require("http");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const os = require("os");

const ROOT = "D:/WorkBuddy"; // 注意: 必须用正斜杠, 反斜杠会让 path.join 吞掉 D:\ 根路径
const PORT = parseInt(process.env.PORT || "8080", 10);
const HOST = "0.0.0.0"; // 绑定所有网卡, 接受局域网/公网入站

// 口令: 优先环境变量, 其次命令行 --token, 再否则使用默认
let TOKEN = process.env.SITE_TOKEN || "";
const ti = process.argv.indexOf("--token");
if (ti >= 0 && process.argv[ti + 1]) TOKEN = process.argv[ti + 1];
if (!TOKEN) TOKEN = "stock2026"; // 默认口令, 请尽快修改

const TOK_VAL = crypto.createHash("sha256").update("sss::" + TOKEN).digest("hex");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".md": "text/markdown; charset=utf-8"
};

function parseCookies(s) {
  const o = {};
  s.split(";").forEach(c => {
    const i = c.indexOf("=");
    if (i > 0) o[c.slice(0, i).trim()] = decodeURIComponent(c.slice(i + 1).trim());
  });
  return o;
}

function loginHtml() {
  return `<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>访问保护</title>
  <style>body{font-family:system-ui,"Microsoft YaHei",sans-serif;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
  .box{background:#1e293b;padding:32px 28px;border-radius:14px;box-shadow:0 10px 40px rgba(0,0,0,.4);width:300px}
  h2{margin:0 0 6px;font-size:18px}.sub{color:#94a3b8;font-size:13px;margin-bottom:20px}
  input{width:100%;box-sizing:border-box;padding:11px 12px;border:1px solid #334155;border-radius:8px;background:#0f172a;color:#e2e8f0;font-size:15px;margin-bottom:14px}
  button{width:100%;padding:11px;border:0;border-radius:8px;background:#e23b3b;color:#fff;font-size:15px;cursor:pointer}
  .err{color:#f87171;font-size:13px;min-height:18px;margin-bottom:8px}</style></head>
  <body><div class="box"><h2>选股系统 · 访问保护</h2><div class="sub">请输入访问口令</div>
  <div class="err" id="err"></div>
  <input id="pw" type="password" placeholder="访问口令" autofocus>
  <label style="display:flex;align-items:center;gap:7px;font-size:13px;color:#94a3b8;margin:0 0 12px;cursor:pointer"><input type="checkbox" id="rm" checked style="width:auto;margin:0"> 记住我（30 天内免口令）</label>
  <button onclick="go()">进入</button></div>
  <script>function go(){var p=document.getElementById('pw').value;var rm=document.getElementById('rm');fetch('/_login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:p,remember:!!(rm&&rm.checked)})}).then(r=>r.json()).then(function(d){if(d.ok){location.reload();}else{document.getElementById('err').textContent='口令错误';}}).catch(function(){document.getElementById('err').textContent='网络错误';});}
  document.getElementById('pw').addEventListener('keydown',function(e){if(e.key==='Enter')go();});</script></body></html>`;
}

function lanIPs() {
  const out = [];
  const ifs = os.networkInterfaces();
  for (const k in ifs) {
    for (const a of ifs[k]) {
      if (a.family === "IPv4" && !a.internal) out.push(a.address);
    }
  }
  return out;
}

const server = http.createServer((req, res) => {
  // 登录接口
  if (req.method === "POST" && req.url === "/_login") {
    let b = "";
    req.on("data", c => (b += c));
    req.on("end", () => {
      let pwd = "", remember = false;
      try { const o = JSON.parse(b); pwd = o.password || ""; remember = o.remember === true; } catch (e) {}
      if (pwd === TOKEN) {
        // 勾选“记住我” → 30 天持久 Cookie；未勾选 → 会话 Cookie（关浏览器即失效）
        const cookie = `tok=${TOK_VAL}; Path=/; HttpOnly; SameSite=Strict` + (remember ? `; Max-age=2592000` : ``);
        res.setHeader("Set-Cookie", cookie);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end('{"ok":true}');
      } else {
        res.writeHead(401, { "Content-Type": "application/json" });
        res.end('{"ok":false}');
      }
    });
    return;
  }

  // 退出登录：清除 Cookie
  if (req.method === "GET" && req.url === "/_logout") {
    res.setHeader("Set-Cookie", `tok=; Path=/; HttpOnly; SameSite=Strict; Max-age=0`);
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(`<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>已退出</title><style>body{font-family:system-ui,"Microsoft YaHei",sans-serif;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}.box{background:#1e293b;padding:30px 28px;border-radius:14px;text-align:center}.box a{color:#e23b3b;text-decoration:none;font-weight:700}</style></head><body><div class="box"><h2>已退出登录</h2><p style="color:#94a3b8;font-size:13px">本机记住已清除</p><p><a href="/">重新登录</a></p></div></body></html>`);
    return;
  }

  // 口令校验
  const cookies = parseCookies(req.headers.cookie || "");
  if (cookies.tok !== TOK_VAL) {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(loginHtml());
    return;
  }

  // 静态文件服务
  let p = decodeURIComponent(req.url.split("?")[0]);
  if (p === "/") p = "/stock-selection-system.html";
  const fp = path.normalize(path.join(ROOT, p.replace(/^\/+/, "")));
  if (!fp.startsWith(path.normalize(ROOT))) {
    res.writeHead(403);
    res.end("forbidden");
    return;
  }
  fs.readFile(fp, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end("not found: " + p);
      return;
    }
    let out = data;
    const ext = path.extname(fp);
    if (ext === ".html") {
      const htmlStr = data.toString("utf8");
      // 避免与已自带 gate 的页面（deploy/index.html）重复注入
      if (!htmlStr.includes("gateLogout") && !htmlStr.includes("svLogout")) {
        const widget = `<div id="svLogout" style="position:fixed;right:12px;bottom:12px;z-index:9998;font-size:12px;color:#64748b;background:rgba(255,255,255,.92);border:1px solid #e2e8f0;border-radius:8px;padding:5px 11px;cursor:pointer;font-family:system-ui,'Microsoft YaHei',sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.08)" onclick="fetch('/_logout').then(()=>location.href='/')">退出登录</div>`;
        out = Buffer.from(htmlStr.replace("</body>", widget + "</body>"), "utf8");
      }
    }
    res.writeHead(200, {
      "Content-Type": MIME[ext] || "application/octet-stream; charset=utf-8"
    });
    res.end(out);
  });
});

server.listen(PORT, HOST, () => {
  const ips = lanIPs();
  console.log("==================================================");
  console.log(" 选股系统发布服务器已启动");
  console.log(" 监听: " + HOST + ":" + PORT + "  (所有网络接口)");
  console.log(" 本机: http://localhost:" + PORT + "/stock-selection-system.html");
  ips.forEach(ip => console.log(" 局域网: http://" + ip + ":" + PORT + "/stock-selection-system.html"));
  console.log(" 口令保护: 已启用  (当前口令 = '" + TOKEN + "', 请尽快修改)");
  console.log("==================================================");
});
