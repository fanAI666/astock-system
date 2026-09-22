"""本地日K库同步器（baostock → SQLite，前复权）

设计目标：替换盘后选股里对 1270 只逐只打腾讯 fqkline 的低效做法。

口径说明（09-21 实测已验证）：
  adjustflag=2（前复权）与现有系统腾讯 qfq 近端偏差 0.000%，
  末根收盘 = 真实价 → 止损止盈绝对价位零误差，可无缝替换。
  🚫 不可用 adjustflag=1（后复权），与 qfq 偏差达千倍。

用法：
  python klines_sync.py --backfill      # 全量回填（首次，约 1 小时，可断点续传）
  python klines_sync.py                 # 增量同步（默认，带守卫；也会补齐新进候选的缺口）
  python klines_sync.py --status        # 查库状态
  python klines_sync.py --refit         # 全量重拉（前复权在除权后会变，建议每月一次）

代码集：默认取四源并集（盘后候选池 import_final + 回测宇宙 universe_klines
        + chuang_signals + sanqizhou_report）。候选池只增不减，新增代码会在
        下次 `python klines_sync.py` 时自动补齐全历史。

五重风控守卫（09-20 曾因全市场空转被 baostock 拉黑 IP）：
  1. 探针探测「最新可得交易日」——当日日K官方 17:30 才入库
  2. 探针末根 <= 库内最新日期 → 无新数据，直接退出（不做任何批量请求）
  3. 只对真缺口的股票发起请求
  4. 并发上限 4（实测 8 并发失败率 30%）
  5. 失败率超阈值熔断，保护 IP
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "klines.db"

# 🔴 代码集必须是「实际候选池 + 回测宇宙」的并集：
#    盘后链路评分用的是 选股结果/import_final.json（候选池只增不减，且与 universe_klines
#    大量不重叠 —— 09-21 实测 197 只中 138 只不在那 1270 只里），只按 universe_klines 建库
#    会导致盘后脚本大面积走腾讯兜底。故默认取四源并集。
CODE_SOURCES = [
    ("选股结果/import_final.json",      ("items",)),          # 盘后候选池（核心）
    ("选股结果/universe_klines.json",   ("items",)),          # 回测/长历史宇宙
    ("选股结果/chuang_signals.json",    ("buys",)),           # 双创信号
    ("选股结果/sanqizhou_report.json",  ("stocks",)),         # 三周期
]

START_DATE = "2022-01-01"  # 约 1130 交易日，满足 MA250 与长历史回测
ADJUSTFLAG = "2"          # 前复权 —— 与腾讯 qfq 同口径
RECONNECT_EVERY = 200     # 每 N 只重连一次，防长连接超时
MAX_RETRIES = 3
PROBE_CODE = "sh.600000"  # 探针：浦发银行，老牌活跃股
MAX_FAIL_RATE = 0.30      # 失败率熔断阈值

SCHEMA = """
CREATE TABLE IF NOT EXISTS kline_daily (
    symbol TEXT NOT NULL,
    date   TEXT NOT NULL,
    open   REAL, high REAL, low REAL, close REAL,
    volume REAL, amount REAL,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_kd_symbol_date ON kline_daily(symbol, date);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


# ────────────────────── 库操作 ──────────────────────

def db_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def load_universe(conn: sqlite3.Connection | None = None) -> list[tuple[str, str, str]]:
    """返回「库内已有 symbol ∪ 四源并集」[(symbol, name, board)]，symbol 为 6 位纯数字。

    先纳入库内已有代码，保证即使外部信号源/宇宙文件被清理，已入库股票也不会
    从维护范围中掉出（避免增量同步覆盖不全导致库内数据陈旧）。
    """
    seen: dict[str, tuple[str, str, str]] = {}
    if conn is not None:
        for (sym,) in conn.execute("SELECT DISTINCT symbol FROM kline_daily"):
            sym = str(sym).strip()
            if len(sym) == 6:
                seen[sym] = (sym, "", "")
    for rel, keys in CODE_SOURCES:
        fp = BASE / rel
        if not fp.exists():
            continue
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"  [!] 跳过 {rel}: {exc}")
            continue
        arr = None
        if isinstance(d, list):
            arr = d
        else:
            for k in keys:
                if isinstance(d.get(k), list):
                    arr = d[k]
                    break
        if not arr:
            continue
        for it in arr:
            if not isinstance(it, dict):
                continue
            code = str(it.get("code", "")).strip()
            if len(code) != 6:
                continue
            nm = it.get("name", "") or it.get("stockName", "") or ""
            # 库内已有代码若名称为空（DB 只存 symbol），用外部源补全
            if code not in seen or not seen[code][1]:
                seen[code] = (code, nm, it.get("board", "") or seen.get(code, ("", "", ""))[2])
    return list(seen.values())


def to_bs_code(symbol: str) -> str:
    return ("sh." if symbol.startswith(("6", "9")) else "sz.") + symbol


def last_dates(conn: sqlite3.Connection) -> dict[str, str]:
    return {s: d for s, d in conn.execute("SELECT symbol, MAX(date) FROM kline_daily GROUP BY symbol")}


def db_state(conn: sqlite3.Connection) -> dict:
    n = conn.execute("SELECT COUNT(*) FROM kline_daily").fetchone()[0]
    syms = conn.execute("SELECT COUNT(DISTINCT symbol) FROM kline_daily").fetchone()[0]
    mn, mx = conn.execute("SELECT MIN(date), MAX(date) FROM kline_daily").fetchone()
    return {"rows": n, "symbols": syms, "min": mn, "max": mx}


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, value))
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


# ────────────────────── baostock 封装 ──────────────────────

def bs_login(bs) -> bool:
    lg = bs.login()
    if lg.error_code != "0":
        print(f"  [!] baostock 登录失败: {lg.error_msg}")
        if "黑名单" in str(lg.error_msg) or "blacklist" in str(lg.error_msg).lower():
            print("  [!] 当前 IP 被 baostock 风控，需等待解除（通常次日自动恢复）")
        return False
    return True


def bs_login_retry(bs, tries: int = 4) -> bool:
    """登录带重试 —— baostock 偶发套接字层错误（WinError 10057），属瞬时故障。
    实测 2026-09-21：连续登录失败后 20s 再试即恢复，故加退避重试。"""
    for i in range(tries):
        if bs_login(bs):
            return True
        if i < tries - 1:
            wait = 8 * (i + 1)
            print(f"      登录重试 {i + 1}/{tries - 1}，等待 {wait}s …")
            time.sleep(wait)
    return False


def probe_latest_trade_date(bs) -> str | None:
    """守卫1：探测「最新可得交易日」。返回末根K线日期，失败返回 None。"""
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=30)).isoformat()
    for attempt in range(3):
        try:
            rs = bs.query_history_k_data_plus(
                PROBE_CODE, "date,close", start_date=start, end_date=end,
                frequency="d", adjustflag=ADJUSTFLAG,
            )
            if rs.error_code != "0":
                raise RuntimeError(rs.error_msg)
            last = None
            while rs.next():
                row = rs.get_row_data()
                if row[0]:
                    last = row[0]
            return last
        except Exception as exc:  # noqa: BLE001
            print(f"  探针第{attempt + 1}次失败: {exc}")
            time.sleep(3 * (attempt + 1))
    return None


def fetch_one(bs, symbol: str, start: str, end: str) -> list[list]:
    """单只查询，带重试。返回 [[symbol,date,o,h,l,c,vol,amount],...]"""
    bs_code = to_bs_code(symbol)
    for attempt in range(MAX_RETRIES):
        try:
            rs = bs.query_history_k_data_plus(
                bs_code, "date,open,high,low,close,volume,amount",
                start_date=start, end_date=end, frequency="d", adjustflag=ADJUSTFLAG,
            )
            if rs.error_code != "0":
                raise RuntimeError(rs.error_msg)
            rows = []
            while rs.next():
                r = rs.get_row_data()
                if not r[0] or not r[4]:
                    continue
                rows.append([symbol] + r)
            return rows
        except Exception as exc:  # noqa: BLE001
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** (attempt + 1))
                bs.logout()
                time.sleep(0.5)
                bs_login_retry(bs, tries=3)
            else:
                print(f"    [{symbol}] {MAX_RETRIES}次均失败: {exc}")
    return []


def upsert(conn: sqlite3.Connection, rows: list[list], replace: bool = False) -> int:
    """replace=True 时先删除该股票区间数据（用于 --refit）"""
    if not rows:
        return 0
    if replace:
        sym = rows[0][0]
        conn.execute("DELETE FROM kline_daily WHERE symbol=?", (sym,))
    cur = conn.executemany(
        "INSERT OR REPLACE INTO kline_daily(symbol,date,open,high,low,close,volume,amount) "
        "VALUES(?,?,?,?,?,?,?,?)",
        [(r[0], r[1], _f(r[2]), _f(r[3]), _f(r[4]), _f(r[5]), _f(r[6]), _f(r[7])) for r in rows],
    )
    conn.commit()
    return cur.rowcount


def _f(v) -> float | None:
    try:
        return float(v) if v not in ("", None) else None
    except (TypeError, ValueError):
        return None


# ────────────────────── 主流程 ──────────────────────

def cmd_status() -> None:
    conn = db_connect()
    st = db_state(conn)
    print("=" * 66)
    print(f"库文件   : {DB_PATH}")
    print(f"存在     : {DB_PATH.exists()}  大小: {DB_PATH.stat().st_size / 1e6:.1f} MB" if DB_PATH.exists() else "不存在")
    print(f"记录数   : {st['rows']:,}")
    print(f"股票数   : {st['symbols']}")
    print(f"日期区间 : {st['min']} ~ {st['max']}")
    print(f"口径     : 前复权(adjustflag={ADJUSTFLAG})")
    print(f"最近回填 : {get_meta(conn, 'last_backfill') or '-'}")
    print(f"最近同步 : {get_meta(conn, 'last_sync') or '-'}")
    print(f"最近重拉 : {get_meta(conn, 'last_refit') or '-'}")
    conn.close()
    print("=" * 66)


def cmd_backfill(refit: bool = False) -> None:
    import baostock as bs

    conn = db_connect()
    universe = load_universe(conn)
    existing = last_dates(conn)
    today = date.today().isoformat()

    print("=" * 66)
    print(f"{'全量重拉(--refit)' if refit else '全量回填'} | 宇宙 {len(universe)} 只 | 起始 {START_DATE} | 前复权")
    print("=" * 66)

    if not bs_login_retry(bs):
        conn.close()
        return

    # 守卫3：只处理真缺口的股票
    todo = []
    for symbol, name, board in universe:
        if refit:
            todo.append((symbol, name))
            continue
        ld = existing.get(symbol)
        if not ld:
            todo.append((symbol, name))
        elif ld < today:
            todo.append((symbol, name))
    print(f"需处理 {len(todo)} 只（已最新 {len(universe) - len(todo)} 只跳过）\n")

    ok = fail = skipped = 0
    since_reconnect = 0
    t0 = time.time()

    for i, (symbol, name) in enumerate(todo, 1):
        since_reconnect += 1
        if since_reconnect >= RECONNECT_EVERY:
            bs.logout()
            time.sleep(1)
            if not bs_login_retry(bs, tries=3):
                print("  重连失败，终止（已入库数据保留，可重跑续传）")
                break
            since_reconnect = 0

        start = START_DATE
        if refit:
            rows = fetch_one(bs, symbol, START_DATE, today)
        else:
            ld = existing.get(symbol)
            start = (date.fromisoformat(ld) + timedelta(days=1)).isoformat() if ld else START_DATE
            rows = fetch_one(bs, symbol, start, today)

        if rows:
            upsert(conn, rows, replace=refit)
            ok += 1
        else:
            fail += 1

        if i % 50 == 0 or i == len(todo):
            el = time.time() - t0
            eta = el / i * (len(todo) - i) / 60
            print(f"  [{i}/{len(todo)}] 成功{ok} 失败{fail} 已用{el / 60:.1f}min 预计剩余{eta:.1f}min")

    bs.logout()
    st = db_state(conn)
    set_meta(conn, "last_refit" if refit else "last_backfill", datetime.now().strftime("%Y-%m-%d %H:%M"))
    set_meta(conn, "adjustflag", ADJUSTFLAG)
    conn.close()

    print("\n" + "=" * 66)
    print(f"完成：成功 {ok} / 失败 {fail} / 跳过 {skipped}")
    print(f"库状态：{st['rows']:,} 行 / {st['symbols']} 只 / {st['min']} ~ {st['max']}")
    print("=" * 66)


def cmd_sync() -> None:
    import baostock as bs

    conn = db_connect()
    today = date.today().isoformat()

    print("=" * 66)
    print(f"增量同步 | {today}")
    print("=" * 66)

    st = db_state(conn)
    if st["rows"] == 0:
        print("[X] 库为空，请先执行 --backfill")
        conn.close()
        return

    if not bs_login_retry(bs):
        conn.close()
        return

    # 守卫1+2：探针探测最新可得交易日
    latest = probe_latest_trade_date(bs)
    print(f"探针 {PROBE_CODE} 最新可得交易日 = {latest or '探测失败'}")

    if not latest:
        print("[X] 探针失败，为避免风控不发起批量请求，本次跳过")
        bs.logout()
        conn.close()
        return

    if latest <= st["max"]:
        # 无新交易日，但仍可能有「库内完全没有」的代码（候选池只增不减 → 新进候选）
        existing0 = last_dates(conn)
        uni0 = load_universe(conn)
        missing0 = [(s, n) for s, n, _ in uni0 if not existing0.get(s)]
        if not missing0:
            print(f"[✓] 无新数据（库内已到 {st['max']}，可得 {latest}）")
            print("    官方时点：当日日K 17:30 入库 —— 15:40 盘后链路无法从 baostock 取当日数据")
            bs.logout()
            conn.close()
            return
        print(f"[→] 无新交易日，但库内缺 {len(missing0)} 只（新进候选），仅补这些\n")
    else:
        print(f"[→] 有新数据（库内 {st['max']} → 可得 {latest}），开始增量")

    # 守卫3：只拉缺口股票（缺失=全历史；已存在=仅增量）
    existing = last_dates(conn)
    universe = load_universe(conn)
    todo: list[tuple[str, str, bool]] = []
    for s, n, _ in universe:
        ld = existing.get(s)
        if not ld:
            todo.append((s, n, True))       # True = 需要全量历史
        elif ld < latest:
            todo.append((s, n, False))
    n_full = sum(1 for _, _, f in todo if f)
    print(f"需处理 {len(todo)} 只（其中全量补历史 {n_full} 只；已最新 "
          f"{len(universe) - len(todo)} 只跳过）\n")

    ok = fail = 0
    since_reconnect = 0
    t0 = time.time()

    for i, (symbol, name, _is_full) in enumerate(todo, 1):
        since_reconnect += 1
        if since_reconnect >= RECONNECT_EVERY:
            bs.logout()
            time.sleep(1)
            if not bs_login_retry(bs, tries=3):
                print("  重连失败，终止（可重跑续传）")
                break
            since_reconnect = 0

        ld = existing.get(symbol)
        start = (date.fromisoformat(ld) + timedelta(days=1)).isoformat() if ld else START_DATE
        rows = fetch_one(bs, symbol, start, latest)
        if rows:
            upsert(conn, rows)
            ok += 1
        else:
            # 库内完全没有的股票返回空 = 真失败（不是「无新数据」）
            fail += 1

        # 守卫5：熔断
        if i >= 20 and fail / i > MAX_FAIL_RATE:
            print(f"  [!] 失败率 {fail / i:.0%} 超阈值 {MAX_FAIL_RATE:.0%}，熔断退出（保护 IP）")
            break

        if i % 50 == 0 or i == len(todo):
            el = time.time() - t0
            print(f"  [{i}/{len(todo)}] 成功{ok} 失败{fail} 已用{el / 60:.1f}min 预计剩余{el / i * (len(todo) - i) / 60:.1f}min")

    bs.logout()
    st2 = db_state(conn)
    set_meta(conn, "last_sync", datetime.now().strftime("%Y-%m-%d %H:%M"))
    conn.close()

    print("\n" + "=" * 66)
    print(f"完成：成功 {ok} / 失败 {fail}")
    print(f"库状态：{st2['rows']:,} 行 / {st2['symbols']} 只 / {st2['min']} ~ {st2['max']}")
    print(f"验证：探针 {PROBE_CODE} 末根 {latest}")
    print("=" * 66)


def main() -> None:
    ap = argparse.ArgumentParser(description="本地日K库同步器（baostock 前复权 → SQLite）")
    ap.add_argument("--backfill", action="store_true", help="全量回填（首次，可断点续传）")
    ap.add_argument("--refit", action="store_true", help="全量重拉（校正除权导致的前复权历史变动）")
    ap.add_argument("--status", action="store_true", help="查看库状态")
    args = ap.parse_args()

    if args.status:
        cmd_status()
    elif args.refit:
        cmd_backfill(refit=True)
    elif args.backfill:
        cmd_backfill(refit=False)
    else:
        cmd_sync()


if __name__ == "__main__":
    main()
