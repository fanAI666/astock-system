# 选股系统 · 发布与访问说明

服务器文件：`D:\WorkBuddy\serve.js`
已升级：绑定所有网卡（0.0.0.0）+ 服务器端口令保护 + 启动打印访问地址。

---

## 一、家庭局域网访问（已可用）

同一 WiFi 下的手机 / 平板 / 电脑，浏览器打开：

```
http://192.168.3.139:8080/stock-selection-system.html
```

首次打开会要求输入访问口令，当前口令：**stock2026**（请尽快修改，见下文）。

> 若手机访问不通，多半是 Windows 防火墙拦截，按第三节放行 8080 入站即可。

---

## 二、公网访问（通过家庭宽带 · Cloudflare Tunnel）

由本机 `cloudflared` 从家庭网络建立一条到 Cloudflare 边缘节点的隧道，外部获得一个
`https://xxxx.trycloudflare.com` 的公网地址。**无需公网 IP、无需改动路由器**，
且自带 HTTPS、不暴露家庭真实 IP，是最适合家庭宽带的发布方式。口令保护同样生效。

- 启动方式：在本机运行 `cloudflared.exe tunnel --url http://localhost:8080 --no-autoupdate`
- 启动后控制台会打印公网地址，把它发给你自己即可在外网打开
- 选股数据由 WorkBuddy 自动化每日写入 `D:\WorkBuddy\选股结果\`，无需手动上传

### 当前公网地址（本次会话已建立，有效期至本机隧道关闭）

```
https://abroad-impacts-clay-across.trycloudflare.com/stock-selection-system.html
```

> ⚠️ 这是 quick tunnel 随机地址，**本机隧道进程一旦关闭/重启就会失效并更换新地址**。
> 需要稳定不变的公网域名，请按本文附录配置「命名隧道」。

---

## 三、Windows 防火墙放行（局域网必要）

以管理员 PowerShell 运行：

```powershell
New-NetFirewallRule -DisplayName "选股系统8080" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow
```

---

## 四、访问口令修改（强烈建议）

口令通过环境变量或命令行参数传入，不要写死在文件里：

- 方式 A（环境变量）：
  ```bash
  SITE_TOKEN=你的新口令 node serve.js
  ```
- 方式 B（命令行参数）：
  ```bash
  node serve.js --token 你的新口令
  ```

默认口令 `stock2026` 仅作临时占位，请尽快改为你自己的口令。

---

## 五、一键启动（本机 Windows）

双击 `D:\WorkBuddy\start-publish.bat`：
1. 先启动本地服务（带口令）
2. 若 `cloudflared.exe` 已就绪，再启动公网隧道并打印公网地址

---

## 六、注意事项

- 本机需保持开机，且 `serve.js` 与 `cloudflared` 都在运行，外部才能访问。
- quick tunnel 的公网地址**每次重启会变**；如需固定域名，见附录。
- 选股系统本身只读取本地静态文件与 `选股结果/` 下的 JSON，不对外暴露任何交易凭证。

---

## 附录：固定公网域名（命名隧道，可选）

适合长期对外提供稳定地址，需要免费 Cloudflare 账号 + 一个域名：

1. `cloudflared.exe login`（浏览器授权）
2. `cloudflared.exe tunnel create stock`
3. `cloudflared.exe tunnel route dns stock stock.你的域名.com`
4. 建配置文件指向 `http://localhost:8080` 后运行 `cloudflared.exe tunnel run stock`

完成后公网地址固定为 `https://stock.你的域名.com`，不再随重启变化。

---

## 七、正式发布（固定公网地址）：GitHub Pages ⭐

> 这是当前**首选**的持久托管方式，地址**永久不变**，每天自动刷新。

**固定访问地址（直接用）：**
```
https://fanai666.github.io/astock-system/
```
首次打开输入访问口令 **`stock2026`**。

### 关键说明（你已确认的选择）
- **仓库设为「公开」**：GitHub 免费计划**不支持私有仓库启用 Pages**（报错 "Your current plan does not support GitHub Pages for this repository"），故把 `fanAI666/astock-system` 设为公开，Pages 即免费可用。
- **数据对外可见的代价**：因为仓库公开，`/data/import_final.json`、`/data/import_pre.json`（你的选股结果）任何人可直接抓。前端访问口令**只遮挡界面**，不保护原始 JSON。这正是你选的「公开仓库 + GitHub Pages」方案的取舍。
- 若以后想要「数据也保密 + 固定地址」，需改用 Cloudflare Pages + Access（需 Cloudflare 账号），见附录或另行告知。

### 仓库与分支
- 代码备份：`main` 分支
- 站点源：`gh-pages` 分支（Pages 源设为该分支、公开站点）
- 仓库地址：https://github.com/fanAI666/astock-system

### 每日自动同步（已配置自动化）
- 自动化「选股系统云端同步」：交易日下午 **18:30** 自动运行 `node sync_pages.js`
  → 重跑 `build_deploy.js` 生成 `deploy/` → 复制到 `pages/` → 推送到 `gh-pages` 分支 → Pages 自动重新构建
- **地址不变**，无需每次记新链接。自动化跑完会在回复里写出固定地址。

### 手动更新
```bash
cd D:\WorkBuddy && node sync_pages.js
```

### 推送凭据（重要）
- 令牌保存在 **`.github_remote`**（已被 `.gitignore` 忽略，**不会进公开仓库**），`sync_pages.js` 每次运行读取它来推送 `gh-pages`。
- 该令牌也残留在本机 `pages/.git/config` 与 `D:\WorkBuddy\.git/config` 的 origin 地址中（均为本地文件，不上传 GitHub）。
- 如需吊销：去 GitHub → Settings → Developer settings → Personal access tokens 撤销该 `ghp_...` 令牌；之后同步需重新生成并写入 `.github_remote`。

> 注：`serve.js`（局域网 / Cloudflare Tunnel）与 CloudStudio 部署仍可用，但本方案地址固定、无需本机常开，推荐日常使用本 GitHub Pages 地址。
