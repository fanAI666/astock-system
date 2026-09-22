"""本地日K库读取模块（供盘后选股等脚本 import）

设计原则：
  - 纯标准库（sqlite3），不引入第三方依赖，任何 Python 都能跑
  - 返回格式与现有 `_auto_screen_*.py::fetch_recent()` 完全一致：
      [date('YYYY-MM-DD'), open, close, high, low, volume]，老 → 新
  - 库缺失/无数据时返回 None，调用方自动降级到腾讯端点

口径：库内为 baostock 前复权，与腾讯 qfq 近端偏差 0.000%（末收盘零误差），
可直接作为 fetch_recent() 的替换源。注意：baostock 当日日K 17:30 才入库，
15:40 盘后链路取到的最后一日为 T-1，当日棒仍须由 qt.gtimg.cn 叠加。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "klines.db"

__all__ = ["recent_bars", "last_date", "db_available", "coverage"]


def db_available() -> bool:
    try:
        return DB_PATH.exists() and DB_PATH.stat().st_size > 0
    except OSError:
        return False


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)


def recent_bars(code: str, start: str | None = None, end: str | None = None,
                limit: int | None = None) -> list[list] | None:
    """读本地库日K。返回 [date, open, close, high, low, volume] 老->新；无数据返回 None。

    start/end 接受 'YYYY-MM-DD' 或 'YYYYMMDD'；limit 为取最近 N 根。
    """
    if not db_available():
        return None
    sym = str(code).strip()
    if len(sym) != 6:
        return None

    def norm(d: str | None) -> str | None:
        if not d:
            return None
        d = d.replace("-", "")
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"

    s, e = norm(start), norm(end)
    sql = "SELECT date, open, close, high, low, volume FROM kline_daily WHERE symbol = ?"
    params: list = [sym]
    if s:
        sql += " AND date >= ?"
        params.append(s)
    if e:
        sql += " AND date <= ?"
        params.append(e)
    sql += " ORDER BY date DESC" if limit else " ORDER BY date ASC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))

    try:
        with _connect() as conn:
            rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return None

    if not rows:
        return None
    if limit:
        rows.reverse()
    return [[r[0], r[1], r[2], r[3], r[4], r[5]] for r in rows]


def last_date(code: str) -> str | None:
    """该股在库内最新日期（'YYYY-MM-DD'）"""
    if not db_available():
        return None
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT MAX(date) FROM kline_daily WHERE symbol = ?", (str(code).strip(),)
            ).fetchone()
    except sqlite3.Error:
        return None
    return row[0] if row and row[0] else None


def coverage() -> dict:
    """库覆盖情况，用于盘后脚本的健康检查输出"""
    if not db_available():
        return {"available": False}
    try:
        with _connect() as conn:
            n, syms, mn, mx = conn.execute(
                "SELECT COUNT(*), COUNT(DISTINCT symbol), MIN(date), MAX(date) FROM kline_daily"
            ).fetchone()
    except sqlite3.Error as exc:
        return {"available": False, "error": str(exc)}
    return {"available": True, "rows": n, "symbols": syms, "min": mn, "max": mx,
            "size_mb": round(DB_PATH.stat().st_size / 1e6, 1)}


if __name__ == "__main__":
    import json
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(coverage(), ensure_ascii=False, indent=2))
    for c in ("600000", "300750"):
        bars = recent_bars(c, limit=3)
        print(c, "->", bars)
