"""从本地日K库导出「长历史宇宙文件」，供 chuang 回测使用

现有 `选股结果/universe_klines.json` 只有约 320 根日K（2023-08 起，且快照停在
2026-08-05），限制了回测窗口。本地库有 2022-01 起的完整前复权日K（约 1130 根），
本脚本按同一格式导出，回测用 BT_SRC 指向它即可：

    BT_SRC=D:/WorkBuddy/data/universe_klines_ext.json \
    BT_OUT=<独立文件> node chuang/index.js backtest

🔴 输出文件较大（约 60-100MB），写在 data/ 下（已 gitignore），禁止提交。

用法：
  python export_universe_ext.py                    # 全量导出
  python export_universe_ext.py --min-bars 600     # 只导出K线数 >= 600 的
  python export_universe_ext.py --start 2021-01-01 # 自定义起点
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "klines.db"
UNIVERSE = BASE / "选股结果" / "universe_klines.json"
OUT_PATH = BASE / "data" / "universe_klines_ext.json"


def main() -> None:
    ap = argparse.ArgumentParser(description="本地库 -> 长历史宇宙文件")
    ap.add_argument("--start", default="2022-01-01", help="起始日期（默认 2022-01-01）")
    ap.add_argument("--min-bars", type=int, default=500, help="最少K线根数，过滤次新股（默认 500）")
    ap.add_argument("--out", default=str(OUT_PATH), help="输出路径")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print("[X] 本地库不存在，请先执行 klines_sync.py --backfill")
        return

    meta = {}
    if UNIVERSE.exists():
        u = json.loads(UNIVERSE.read_text(encoding="utf-8"))
        for it in u.get("items", []):
            meta[str(it.get("code"))] = (it.get("name", ""), it.get("board", ""))

    conn = sqlite3.connect(str(DB_PATH))
    syms = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM kline_daily ORDER BY symbol")]
    print("=" * 70)
    print(f"导出长历史宇宙 | 库内 {len(syms)} 只 | 起始 {args.start} | 最少 {args.min_bars} 根")
    print("=" * 70)

    items = []
    skipped_short = 0
    for i, sym in enumerate(syms, 1):
        rows = conn.execute(
            "SELECT date, open, close, high, low, volume FROM kline_daily "
            "WHERE symbol = ? AND date >= ? ORDER BY date",
            (sym, args.start),
        ).fetchall()
        if len(rows) < args.min_bars:
            skipped_short += 1
            continue
        name, board = meta.get(sym, ("", ""))
        day = [[r[0].replace("-", ""), r[1], r[2], r[3], r[4], r[5]] for r in rows]
        items.append({"code": sym, "name": name or sym, "board": board, "kline": {"day": day}})
        if i % 200 == 0:
            print(f"  [{i}/{len(syms)}] 已收录 {len(items)} 只")
    conn.close()

    if not items:
        print("[X] 无满足条件的股票，请检查 --min-bars 或库内数据")
        return

    period = [items[0]["kline"]["day"][0][0], items[0]["kline"]["day"][-1][0]]
    bars_stat = [len(it["kline"]["day"]) for it in items]
    payload = {
        "updated": __import__("datetime").date.today().isoformat(),
        "period": period,
        "source": "baostock 前复权 (adjustflag=2) / data/klines.db",
        "count": len(items),
        "items": items,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    size_mb = out.stat().st_size / 1e6
    print("-" * 70)
    print(f"收录 {len(items)} 只（因K线不足剔除 {skipped_short} 只）")
    print(f"K线根数：最少 {min(bars_stat)} / 最多 {max(bars_stat)} / 平均 {sum(bars_stat) / len(bars_stat):.0f}")
    print(f"输出：{out}  ({size_mb:.1f} MB)")
    print(f"🔴 大文件，禁止提交 git（已在 .gitignore）")
    print("-" * 70)
    print("回测用法：")
    print(f"  BT_SRC={out.as_posix()} BT_OUT=<独立输出文件> node chuang/index.js backtest")
    print("=" * 70)


if __name__ == "__main__":
    main()
