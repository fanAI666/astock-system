#!/usr/bin/env bash
# ============================================================
#  A股量化选股系统 · 一键更新脚本（跨平台 / macOS / Linux）
#
#  用途：在自动化不可用时（电脑关机 / WorkBuddy 未运行）
#        手动完成"拉数据 → 重标定 → 回测 → 构建 → 部署"全套。
#  用法：chmod +x update.sh && ./update.sh
#
#  全链路：
#    ① [可选] extend_history.js   — 注入 tdx 真实历史（需 WorkBuddy）
#    ② recalibrate_win.py         — 重标定 winRate 为回测真实胜率
#    ③ backtest_winrate.js        — 跑回测引擎
#    ④ build_briefings.js         — 构建每日简报
#    ⑤ build_deploy.js            — 构建部署包
#    ⑥ sync_pages.js              — 推送到 GitHub Pages
# ============================================================

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
TS="$(date '+%Y-%m-%d %H:%M:%S')"

echo "=========================================="
echo "  A股量化选股系统 · 一键更新"
echo "  $TS"
echo "=========================================="
echo

# ---- 自动探测运行时 ----
detect_runtime() {
    # Node: 优先用管理版，fallback 系统 PATH
    if command -v node &>/dev/null; then
        NODE="$(command -v node)"
    elif [ -f "$HOME/.workbuddy/binaries/node/versions/22.22.2/node" ] 2>/dev/null; then
        NODE="$HOME/.workbuddy/binaries/node/versions/22.22.2/node"
    elif [ -f "/c/Users/fanfan/.workbuddy/binaries/node/versions/22.22.2/node.exe" ] 2>/dev/null; then
        NODE="/c/Users/fanfan/.workbuddy/binaries/node/versions/22.22.2/node.exe"
    else
        echo "[错误] 找不到 Node.js" >&2; exit 1
    fi

    # Python: 优先用管理版 3.13，fallback 系统 PATH
    if command -v python3 &>/dev/null; then
        PYTHON="$(command -v python3)"
    elif [ -f "$HOME/.workbuddy/binaries/python/versions/3.13.12/python" ] 2>/dev/null; then
        PYTHON="$HOME/.workbuddy/binaries/python/versions/3.13.12/python"
    elif [ -f "/c/Users/fanfan/.workbuddy/binaries/python/versions/3.13.12/python.exe" ] 2>/dev/null; then
        PYTHON="/c/Users/fanfan/.workbuddy/binaries/python/versions/3.13.12/python.exe"
    else
        echo "[错误] 找不到 Python 3" >&2; exit 1
    fi
}

detect_runtime

echo "[OK] Node:   $NODE  ($($NODE -v))"
echo "[OK] Python: $PYTHON  ($($PYTHON --version 2>&1 | head -1))"
echo "[OK] 工作目录: $ROOT"
echo

# ---- 前置检查 ----
[ -f "$ROOT/选股结果/import_final.json" ] || {
    echo "[错误] 找不到 $ROOT/选股结果/import_final.json，选股数据缺失。" >&2
    exit 1
}

# ---- Step ①：拉取 tdx 历史（可选）----
step_tdx() {
    echo "------------------------------------------"
    echo " Step 1/6 : 拉取 tdx 历史数据 (extend_history.js)"
    echo "------------------------------------------"
    echo "注意：此步骤依赖通达信 MCP (tdx-connector)，"
    echo "      仅能在 WorkBuddy 内部运行。"
    echo

    [ ! -f "$ROOT/extend_history.js" ] && { echo "[跳过] extend_history.js 不存在。"; return; }

    if [ "${1:-}" = "--skip-tdx" ]; then
        echo "[已跳过] 使用现有 kline 数据。"; return
    fi

    read -rp "是否运行 extend_history.js？[y/N] " ans
    case "$ans" in
        [yY]*) ;;
        *) echo "[已跳过]"; return ;;
    esac

    (cd "$ROOT" && "$NODE" extend_history.js) || {
        echo "[警告] extend_history.js 返回非零（可能 tdx 数据未更新），继续..."
    }
    echo
}

# ---- Step ②：重标定 winRate ----
step_recalibrate() {
    echo "------------------------------------------"
    echo " Step 2/6 : 重标定 winRate (recalibrate_win.py)"
    echo "------------------------------------------"
    [ ! -f "$ROOT/recalibrate_win.py" ] && { echo "[跳过] 不存在"; return; }
    (cd "$ROOT" && "$PYTHON" recalibrate_win.py) || {
        echo "[错误] recalibrate_win.py 失败！"; exit 1;
    }
    echo
}

# ---- Step ③：回测引擎 ----
step_backtest() {
    echo "------------------------------------------"
    echo " Step 3/6 : 运行回测引擎 (backtest_winrate.js)"
    echo "------------------------------------------"
    (cd "$ROOT" && "$NODE" backtest_winrate.js) || {
        echo "[错误] backtest_winrate.js 失败！"; exit 1;
    }
    echo
}

# ---- Step ④：构建简报 ----
step_briefing() {
    echo "------------------------------------------"
    echo " Step 4/6 : 构建每日简报 (build_briefings.js)"
    echo "------------------------------------------"
    [ ! -f "$ROOT/build_briefings.js" ] && { echo "[跳过] 不存在"; return; }
    (cd "$ROOT" && "$NODE" build_briefings.js) || true  # 简报失败不阻断
    echo
}

# ---- Step ⑤：构建部署包 ----
step_build() {
    echo "------------------------------------------"
    echo " Step 5/6 : 构建部署包 (build_deploy.js)"
    echo "------------------------------------------"
    (cd "$ROOT" && "$NODE" build_deploy.js) || {
        echo "[错误] build_deploy.js 失败！"; exit 1;
    }
    echo
}

# ---- Step ⑥：同步推送 ----
step_sync() {
    echo "------------------------------------------"
    echo " Step 6/6 : 推送至 GitHub Pages (sync_pages.js)"
    echo "------------------------------------------"
    (cd "$ROOT" && "$NODE" sync_pages.js) || {
        echo "[错误] 推送失败！请检查网络或 .github_remote 令牌。"; exit 1;
    }
    echo
}

# ---- 执行 ----
step_tdx "${1:-}"
step_recalibrate
step_backtest
step_briefing
step_build
step_sync

# ---- 结果摘要 ----
BW="$ROOT/选股结果/backtest_winrate.json"
echo "=========================================="
echo "  ✅ 全部步骤完成！"
echo "=========================================="
echo
echo "最新回测摘要："
if [ -f "$BW" ]; then
    # Windows Git Bash 兼容：转反斜杠
    BW_WIN=$(cygpath -w "$BW" 2>/dev/null || echo "$BW")
    "$NODE" -e "
const j=require('$BW_WIN');
process.stdout.write('  胜率: '+(j.winRate*100).toFixed(1)+'% | 笔数: '+j.trades+' | 期望: '+((j.expectancy||0)*100).toFixed(2)+'/笔\n');
if(j.calibration){const c=j.calibration;process.stdout.write('  标定: 预测 '+(c.predMean*100).toFixed(1)+'% | 实现 '+(c.realized*100).toFixed(1)+'% | 偏差 '+(c.bias*100).toFixed(1)+'pp\n');}
if(j.portfolio){const p=j.portfolio;process.stdout.write('  组合层: 原始 '+p.rawTrades+' → 最终 '+p.finalTrades+' | 回撤暂停 '+(p.drawdownPause?.dropped)+'\n');}
"
fi
echo
echo "线上地址: https://fanai666.github.io/astock-system/"
echo "口令:     stock2026"
echo
