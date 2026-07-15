// 将最新选股结果同步到 GitHub Pages（gh-pages 分支）。
// 设计：1) 重建 deploy/ 2) 复制到 pages/ 工作仓库 3) 提交并推送 gh-pages
// 凭据：从 .github_remote 读取（含令牌的远程地址，已被 .gitignore 忽略，不会进版本库）
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = 'D:/WorkBuddy';
const PAGES = path.join(ROOT, 'pages');
const DEPLOY = path.join(ROOT, 'deploy');

// 1) 读取远程地址
let remote = '';
try { remote = fs.readFileSync(path.join(ROOT, '.github_remote'), 'utf8').trim(); } catch (e) {}
if (!remote) { console.error('未找到 .github_remote（含 GitHub 令牌），无法推送'); process.exit(1); }

// 2) 重新构建 deploy/
console.log('==> 重新构建 deploy/');
const b = spawnSync('node', [path.join(ROOT, 'build_deploy.js')], { stdio: 'inherit', cwd: ROOT });
if (b.status !== 0) { console.error('build_deploy.js 失败'); process.exit(1); }

// 3) 同步到 pages/ 工作仓库
function copyDir(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const e of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, e.name), d = path.join(dst, e.name);
    if (e.isDirectory()) copyDir(s, d); else fs.copyFileSync(s, d);
  }
}
copyDir(path.join(DEPLOY, 'data'), path.join(PAGES, 'data'));
fs.copyFileSync(path.join(DEPLOY, 'index.html'), path.join(PAGES, 'index.html'));

// 4) 提交并推送 gh-pages
const git = (...args) => spawnSync('git', args, { cwd: PAGES, stdio: 'inherit' });
try { git('remote', 'remove', 'origin'); } catch (e) {}
git('remote', 'add', 'origin', remote);

const st = spawnSync('git', ['status', '--porcelain'], { cwd: PAGES });
const changed = st.stdout.toString().trim();
if (changed) {
  const d = new Date().toISOString().slice(0, 16).replace('T', ' ');
  git('add', '-A');
  git('commit', '-q', '-m', 'sync ' + d);
  console.log('==> 已提交当天更新');
} else {
  console.log('==> 无内容变化，跳过提交');
}
console.log('==> 推送到 gh-pages');
const r = git('push', '-u', 'origin', 'gh-pages');
process.exit(r.status || 0);
