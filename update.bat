@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ============================================================
REM  A股量化选股系统 · 一键更新脚本（Windows）
REM
REM  用途：在自动化不可用时（电脑关机 / WorkBuddy 未运行）
REM        手动完成"拉数据 → 重标定 → 回测 → 构建 → 部署"全套。
REM  用法：双击 update.bat 或在 D:\WorkBuddy 下执行
REM
REM  全链路：
REM    ① [可选] extend_history.js   — 拉取/注入 tdx 真实历史（需 WorkBuddy 内跑过）
REM    ② recalibrate_win.py         — 重标定 winRate 为回测真实胜率
REM    ③ backtest_winrate.js        — 跑回测引擎
REM    ④ build_briefings.js         — 构建每日简报
REM    ⑤ build_deploy.js            — 构建部署包（inject gate + 复制数据）
REM    ⑥ sync_pages.js              — 推送到 GitHub Pages (gh-pages)
REM ============================================================

title 选股系统一键更新
echo ════════════════════════════════════════
echo   A股量化选股系统 · 一键更新
echo   %date% %time%
echo ════════════════════════════════════════
echo.

REM ---- 环境检测 ----
set "ROOT=D:\WorkBuddy"
set "NODE=C:\Users\fanfan\.workbuddy\binaries\node\versions\22.22.2\node.exe"
set "PYTHON=C:\Users\fanfan\.workbuddy\binaries\python\versions\3.13.12\python.exe"

if not exist "%NODE%" (
    echo [错误] 找不到 Node.js: %NODE%
    echo 请确认 Node.js 已安装或修改脚本中的 NODE 路径。
    pause & exit /b 1
)
if not exist "%PYTHON%" (
    echo [错误] 找不到 Python: %PYTHON%
    echo 请确认 Python 已安装或修改脚本中的 PYTHON 路径。
    pause & exit /b 1
)
if not exist "%ROOT%\选股结果\import_final.json" (
    echo [错误] 找不到 import_final.json，选股数据缺失。
    echo 请先运行盘后定稿流程生成该文件。
    pause & exit /b 1
)

echo [OK] Node:    %NODE%
for /f "delims=" %%v in ('"%NODE%" -v') do echo      版本: %%v
echo [OK] Python:  %PYTHON%
for /f "delims=" %%v in ('"%PYTHON%" --version 2^>^&1') do echo      版本: %%v
echo [OK] 工作目录: %ROOT%
echo.

REM ---- Step ①：拉取 tdx 历史（可选）----
echo ──────────────────────────────────────
echo  Step 1/6 : 拉取 tdx 历史数据（extend_history.js）
echo ──────────────────────────────────────
echo 注意：此步骤依赖通达信 MCP (tdx-connector)，仅能在
echo       WorkBuddy 内部运行。若你已在 WorkBuddy 中拉取过，
echo       此步可跳过。
echo.
set SKIP_TDX=0
if not exist "%ROOT%\extend_history.js" (
    echo [跳过] extend_history.js 不存在。
    set SKIP_TDX=1
) else (
    choice /C YN /M "是否运行 extend_history.js（拉取/更新 tdx 历史）？"
    if !errorlevel! equ 2 set SKIP_TDX=1
)

if !SKIP_TDX! equ 0 (
    cd /d "%ROOT%"
    "%NODE%" extend_history.js
    if !errorlevel! neq 0 (
        echo [警告] extend_history.js 返回非零（可能 tdx 数据未更新），继续后续步骤...
    )
) else (
    echo [已跳过] 使用现有 import_final.json 中的 kline 数据。
)
echo.

REM ---- Step ②：重标定 winRate ----
echo ──────────────────────────────────────
echo  Step 2/6 : 重标定 winRate（recalibrate_win.py）
echo ──────────────────────────────────────
if not exist "%ROOT%\recalibrate_win.py" (
    echo [跳过] recalibrate_win.py 不存在。
) else (
    cd /d "%ROOT%"
    "%PYTHON%" recalibrate_win.py
    if !errorlevel! neq 0 (
        echo [错误] recalibrate_win.py 失败！
        pause & exit /b 1
    )
)
echo.

REM ---- Step ③：回测引擎 ----
echo ──────────────────────────────────────
echo  Step 3/6 : 运行回测引擎（backtest_winrate.js）
echo ──────────────────────────────────────
cd /d "%ROOT%"
"%NODE%" backtest_winrate.js
if !errorlevel! neq 0 (
    echo [错误] backtest_winrate.js 失败！
    pause & exit /b 1
)
echo.

REM ---- Step ④：构建简报 ----
echo ──────────────────────────────────────
echo  Step 4/6 : 构建每日简报（build_briefings.js）
echo ──────────────────────────────────────
if not exist "%ROOT%\build_briefings.js" (
    echo [跳过] build_briefings.js 不存在。
) else (
    cd /d "%ROOT%"
    "%NODE%" build_briefings.js
    REM 简报失败不阻断（可能无 markdown 文件可生成）
)
echo.

REM ---- Step ⑤：构建部署包 ----
echo ──────────────────────────────────────
echo  Step 5/6 : 构建部署包（build_deploy.js）
echo ──────────────────────────────────────
cd /d "%ROOT%"
"%NODE%" build_deploy.js
if !errorlevel! neq 0 (
    echo [错误] build_deploy.js 失败！
    pause & exit /b 1
)
echo.

REM ---- Step ⑥：同步推送 GitHub Pages ----
echo ──────────────────────────────────────
echo  Step 6/6 : 推送至 GitHub Pages（sync_pages.js）
echo ──────────────────────────────────────
cd /d "%ROOT%"
"%NODE%" sync_pages.js
if !errorlevel! neq 0 (
    echo [错误] 推送失败！请检查网络或 .github_remote 令牌。
    pause & exit /b 1
)
echo.

REM ---- 完成：显示结果摘要 ----
echo ════════════════════════════════════════
echo   ✅ 全部步骤完成！
echo ════════════════════════════════════════
echo.
echo 最新回测摘要：
if exist "%ROOT%\选股结果\backtest_winrate.json" (
    "%NODE%" -e "const j=require('%ROOT:/=\%/选股结果/backtest_winrate.json');console.log('  胜率:',(j.winRate*100).toFixed(1)+'%','| 笔数:',j.trades,'| 期望:'+((j.expectancy||0)*100).toFixed(2)+'/笔');if(j.calibration){const c=j.calibration;console.log('  标定:预测',(c.predMean*100).toFixed(1)+'%','实现',(c.realized*100).toFixed(1)+'%','偏差'+(c.bias*100).toFixed(1)+'pp')}if(j.portfolio){const p=j.portfolio;console.log('  组合层:原始',p.rawTrades,'→最终',p.finalTrades,'|回撤暂停',p.drawdownPause?.dropped)}"
)
echo.
echo 线上地址: https://fanai666.github.io/astock-system/
echo 口令: stock2026
echo.
pause
