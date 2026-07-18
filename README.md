# A股量化选股系统（v1.2.1）

> 单文件、零后端依赖的 A 股量化选股与交易信号系统。基于已定交易规则（3:1 风险回报、主板 2% 止损 / 6% 止盈）做选股展示、成功概率（回测标定）评分、买入触发信号、系统回测胜率与每日简报、盘后资金动态与浅色/深色皮肤切换。**仅生成信号，不接券商、不真实下单。**

---

## 一、版本

| 项 | 值 |
|---|---|
| 当前版本 | **1.2.1**（基准 1.0.0 + 21 功能点） |
| 基准日期 | 2026-07-11 |
| 版本规则 | 以 1.0.0 为基准；每新增 **1 个功能点 +0.0.1**；满 **10 个点进 1**（0.0.9 → 0.1.0）；满 **10 个次版本进 1**（1.9.0 → 2.0.0） |

> 版本推进请用 `node version_bump.js [N] "功能描述"`，自动更新 `VERSION.json` 与 `CHANGELOG.md`（N 默认 1，最大 10）。**不要手动改版本号。**

---

## 二、核心交易规则（全部模块共用）

- **风险回报比**：3 : 1
- **主板**：止损 入场价 − 2% / 止盈 入场价 + 6%（固定）
- **创业板（300 开头）**：主板比例 ×1.5 → 止损 −3% / 止盈 +9%，走 ATR 动态止损（K_ATR=1.05，止盈×3，持有封顶 5 日，跟踪止损封顶 6%）
- **科创板（688 开头，独立规则 v1.1.8）**：止损 −5% / 止盈 +15% / K_ATR=2.5 / 持有 ≤12 日（按用户要求原样保留，未做有效性修复）
- **入场条件**：以成功概率 Top3 个股的**信号日（昨日）收盘价**为基准；**次日开盘价**相对基准波动 ≤ 2%（主板）/ ≤ 3%（创业板·科创板）才入场
- **选股排序**：按「综合强度分」降序取 Top3
- **信号性质**：仅生成买卖信号，**不接券商、不真实下单**
- **双模式（v1.1.0）**：Header 模式切换栏（高频 / 中频，localStorage 记忆）
  - 高频：加载 `backtest_winrate.json`；止损 −2%/+6%；K_ATR=1.05；持有 ≤10 日(主)/≤5 日(创)
  - 中频：加载 `backtest_midfreq.json`；止损 −3.5%/+10%；K_ATR=1.8；持有 ≤20 日(主)/≤12 日(创)；需 MACD(DIF>0) 确认

---

## 三、功能清单（v1.0.0 基准）

1. **选股评分（🔍 选股评分）**：6 维评分 → 综合强度分（原"成功概率"展示已回填回测真实胜率）；Canvas 手绘 K 线五图引擎（当日 / 五日 / 日K / 周K / 月K），日K/周K/月K **右侧新增筹码分布带**（橙虚线=筹码峰、青虚线=筹码均价(量加权成本)），仅对带历史量价的候选股生效。
2. **策略概览（📋 策略概览）**：策略核心参数、交易胜率（系统回测）卡片。
3. **买入触发（📑 每日简报 内）**：以 Top3 基准 + 次日开盘容差判定「建议买入 / 不触发」。
4. **交易胜率回测**：基于 `import_final.json` 真实 K 线（已拉长至约 320 根/支，2025-03 起），按既定规则回测（设定周期 2025.7.1–2026.6.30）：全候选池 243 笔、胜率 27.2%、每笔期望 +0.09%；⑤组合层后 81 笔、期望 −0.04%。标定偏差 −2.9pp（v1.0.7 重标定：预测均值 24.4% vs 实现 27.4%）。
5. **每日简报（📑 每日简报）**：盘后简报 + 买入触发，含轻量 Markdown 渲染器（标题 / 表格 / 风控引用块 / 列表 / 代码）。
6. **仓位计算（🧮 仓位计算）**：按账户资金与止损比例计算单笔仓位。
7. **交易日志（📓 交易日志）**：信号与交易记录展示。
8. **风控看板（📊 风控看板）**：风险相关指标可视化（权益曲线 / 胜负分布）。
9. **口令保护（gate）**：站点访问需输入口令（默认 `stock2026`）。
10. **自动化与部署**：交易日 09:30 自动化抓开盘（tdx-connector）→ 写 `buy_signal.json`；16:00 策略选股定稿+K线+资金动态 → 17:00 自动化构建并推送 GitHub Pages。

> 后续迭代在「四、迭代演进」汇总，不重复展开。

---

## 四、迭代演进（v1.0.1 → v1.2.0）

| 版本 | 日期 | 要点 |
|---|---|---|
| v1.0.1 | 07-11 | 分市场止损：创业板/科创板 ATR 动态止损（封顶 1 周 / 跟踪封顶 6% / 止盈×3） |
| v1.0.2 | 07-11 | 双创加趋势(站上MA20+MA5>MA20+MA20上行)+量能(≥1.2×20日均量)过滤；K_ATR 1.5→1.05 |
| v1.0.3 | 07-11 | winRate 用回测真实胜率标定 + 分层校验(按板块/按预测胜率档≥70) |
| v1.0.4 | 07-11 | 趋势+量能+缺口过滤应用到全市场(不仅双创)；缺口拒向下≥4%/向上≥6%跳空 |
| v1.0.5 | 07-11 | 拉长历史至 320 根真实日线(2025-03起)+扩大候选池(全7支)+分市场回测 |
| v1.0.6 | 07-11 | ⑤组合层风控：大盘硬过滤(上证<MA20不交易)+同日上限≤3笔+回撤>8%暂停次日 |
| v1.0.7 | 07-12 | winRate 重标定：展示回填回测真实胜率，偏差 48.5pp→−2.9pp；公式分保留为综合强度分 |
| v1.0.8 | 07-13 | 新增「买入信号·开盘抓取」专属 Tab |
| v1.0.9 | 07-13 | 取消尾盘预选（删预选卡片/标签，停用预选简报生成与导入入口） |
| v1.1.0 | 07-14 | ⑥双模式：高频/中频切换，参数面板/回测数据/徽章随模式联动 |
| v1.1.4 | 07-15 | P1 胜率→综合强度分 + P2 ATR分位打分 + P3 涨幅>9.5%追高硬拒 + P4 RSI>72 超买硬拒 |
| v1.1.8 | 07-16 | P5 板块RPS分位 + P6 行业≤2 + P7 MA60向上硬拒 + P8 walk-forward；科创板独立规则(止损5%/止盈15%/K_ATR=2.5) |
| v1.1.9 | 07-16 | 资金动态接入盘后真实数据（腾讯指数/风格 + 东方财富行业净流入/北向），跟随每日云端同步上线 |
| v1.2.0 | 07-17 | 皮肤切换(浅色/深色)：token 覆盖层 + 红涨绿跌语义保留，Header 切换按钮 + LocalStorage 持久化，三图表随主题重绘 |
| v1.2.1 | 07-18 | 候选排名 K 线右侧新增筹码峰(橙)/筹码均价(青)分布带；选股评分模块布局对调（候选排名上、评分下） |

---

## 五、目录结构

```
D:\WorkBuddy\
├─ stock-selection-system.html   # 系统主文件（单文件，含内联 CSS/JS）
├─ 选股系统_离线版.html          # 内嵌数据的离线单文件版（package_singlefile.js 生成）
├─ serve.js                      # 本地预览服务器（端口 8080，口令 gate）
├─ build_deploy.js              # 打包 deploy/ + 注入 gate + 复制数据(VERSION/fundflow/…)
├─ sync_pages.js                # 构建并推送 GitHub Pages（gh-pages）
├─ version_bump.js              # 版本推进工具（更新 VERSION.json + CHANGELOG.md）
├─ backtest_winrate.js          # 高频回测脚本
├─ backtest_walkforward.py      # P8 walk-forward 回测（扩大标定样本）
├─ build_final.py               # 选股定稿 + K线注入 + 评分（写 import_final.json）
├─ build_briefings.js           # 简报 markdown → JSON 转换
├─ recalibrate_win.py          # win 重标定（回测真实胜率回填）
├─ fetch_fundflow.py           # 资金动态盘后抓取（腾讯指数/风格 + 东财行业/北向）
├─ extend_history.js            # 从 tdx-connector 拉长 K 线至 320 根
├─ package_singlefile.js        # 生成内嵌数据离线版
├─ VERSION.json                 # 版本状态（机器可读）
├─ CHANGELOG.md                # 版本变更日志（人类可读）
├─ 选股结果/                    # 数据源
│  ├─ import_final.json         # 盘后定稿候选（含 K 线，~130KB）
│  ├─ import_pre.json          # 收盘前预选（已停用，build_final.py 依赖保留）
│  ├─ buy_signal.json          # 当日买入信号（09:30 自动化写）
│  ├─ backtest_winrate.json    # 高频回测结果
│  ├─ backtest_midfreq.json    # 中频回测结果（v1.1.0 双模式）
│  ├─ briefing_final.json      # 盘后简报
│  ├─ walkforward_calib.json   # P8 walk-forward 标定库
│  ├─ fundflow.json           # 资金动态（16:00 抓）
│  ├─ index_sh.json           # 上证指数（⑤大盘过滤）
│  └─ YYYY-MM-DD.md           # 盘后简报原文
├─ deploy/                     # 构建产物（build_deploy.js 生成）
│  ├─ index.html               # 注入口令 gate 后的系统
│  └─ data/                    # 上述 JSON 的副本（含 VERSION.json / fundflow.json）
└─ pages/                      # GitHub Pages 工作仓库（gh-pages 分支）
```

---

## 六、本地预览

```bash
SITE_TOKEN='stock2026' PORT=8080 node serve.js
# 浏览器打开 http://localhost:8080/stock-selection-system.html
```

> 注：`serve.js` 根目录为 `D:/WorkBuddy`（正斜杠），已修复中文路径 0 字节问题。`http://` 协议下页面自动 `fetch` 最新数据；`file://` 下用文件选择器兜底。皮肤切换与资金动态在刷新后按 LocalStorage / 数据文件生效。

---

## 七、部署到 GitHub Pages

部署采用 **GitHub Actions 自动部署**（推送 `main` 即触发，无需手动 `sync_pages.js`）：

- 工作流：`.github/workflows/deploy-pages.yml`（on push `main`，paths 命中 `stock-selection-system.html` / `build_deploy.js` / `build_briefings.js` / `选股结果/**` / 工作流自身）→ `setup-node@v4` → `node build_deploy.js` 生成 `deploy/` → `peaceiris/actions-gh-pages@v3` 推 `gh-pages` 分支。
- `build_deploy.js` 负责：注入口令 gate、复制数据（`import_final.json` / `buy_signal.json` / `backtest_winrate.json` / `backtest_midfreq.json` / `briefing_*.json` / `fundflow.json` / `VERSION.json` 等到 `deploy/data/`）、并把 **`VERSION.json` / `CHANGELOG.md` / `README.md` 复制至 `deploy/` 根目录**（使站点根可直接访问这三类文档）。
- 每日 **17:00**「选股系统云端同步」自动化仅执行 `git push origin main`，由 Actions 自动构建并发布。

```bash
# 本地手动触发等价流程（如需）
node build_deploy.js          # 生成 deploy/
git add -A && git commit -m "deploy" && git push origin main   # 触发 Actions 自动部署
```

- 固定公网地址：**https://fanai666.github.io/astock-system/**
- 访问口令：**stock2026**
- 站点根文档：`https://fanai666.github.io/astock-system/VERSION.json` · [`CHANGELOG.md`](https://fanai666.github.io/astock-system/CHANGELOG.md) · [`README.md`](https://fanai666.github.io/astock-system/README.md)
- 资金动态数据由 16:00 选股自动化抓取，跟随每日 17:00 云端同步上线（沙箱环境连通 github.com 偶发需重试）。

---

## 八、关键自动化

| 名称 | ID | 触发 | 作用 |
|---|---|---|---|
| 买入信号·开盘抓取 | automation-1783746752370 | 交易日 09:30 | 读 import_final.json → 大盘硬过滤(上证<MA20不交易) → Top3 by 综合强度分 → tdx 抓次日开盘 → 全市场趋势+量能+缺口过滤 + 偏离(±2%/±3%) → 同日上限≤3 → 写 buy_signal.json |
| 每日收盘后策略选股 | automation-1783576262542 | 每日 16:00 | 通达信筛选候选 → 6维评分定稿 → 写 import_final.json（含 K 线）；**末尾合并运行 fetch_fundflow.py 抓取资金动态写 fundflow.json** |
| 选股系统云端同步 | automation-1783705955655 | 每日 17:00 | `git push origin main`，由 GitHub Actions 自动部署（含 import_final.json / fundflow.json / VERSION.json / 站点根文档等） |

---

## 九、已知限制 / 后续优化方向

- **策略实盘仍不可行（诚实结论）**：v1.1.8 部署的是规则结构改进，非有效性修复。P8 walk-forward 回测中科创板仍 **0/7**，整体期望 **−0.89%/笔**（负期望）。候选宇宙仍仅 7 支，统计置信不足。
- **资金动态数据依赖盘后抓取**：指数/风格因子走腾讯行情（稳定真值）；行业主力净流入/北向走东方财富，本机盘后跑通；沙箱共享 IP 偶发限流时前端降级显示「示意数据 / 暂未获取」，非 bug。
- **P4 超买硬拒（RSI>72）、P7 MA60 硬拒（down）已上线验证**：候选股展示区会显式标红拒绝原因。
- **选股描述/资金主线为后端烤死文本**：`build_final.py` / `fetch_fundflow.py` 生成的理由/研判写进 JSON，前端原样渲染；方言切换（计划中的 UI 文案层）不影响这些后端文本，保持普通话。
- **待优化**：① 复盘科创板止损（加宽 K_ATR 或剔除双创）；② 扩大真实候选池（>7 支）做 walk-forward；③ 加交易成本与仓位 sizing；④ 方言 UI 文案层（仅前端固定文案，待实现）。

---

## 十、版本历史

见 [`CHANGELOG.md`](./CHANGELOG.md)。完整功能点明细与每次迭代描述均在该文件维护。
