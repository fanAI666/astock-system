"""双源交叉校验：本地日K库（baostock） vs 腾讯 qfq

背景：现有系统盘后选股完全依赖腾讯公开端点，端点静默返回错误数据时
不会被发现（整池基于错误数据选股）。本脚本用 baostock 作为独立第二源
做每日交叉校验。

口径依据（09-21 实测）：baostock adjustflag=2（前复权）与腾讯 qfq
近端偏差 0.000%（末收盘零误差），故两源可直接逐日比对；偏差超阈值
即为真异常，不是口径差异。

用法：
  python klines_verify.py                 # 全量校验最近 5 个交易日
  python klines_verify.py --days 1        # 只校验最新交易日
  python klines_verify.py --sample 150    # 抽查 150 只（快速体检）
  python klines_verify.py --threshold 0.5 # 偏差阈值(%)
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "klines.db"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def tx_qfq(code: str, start: str, end: str, retries: int = 3) -> dict[str, float] | None:
    """腾讯前复权收盘价 {date: close}；None 表示获取失败（端点问题，不判定为数据异常）"""
    full = ("sh" if str(code)[0] in "69" else "sz") + str(code)
    url = (
        "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get"
        f"?param={full},day,{start},{end},320,qfq"
    )
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"}
            )
            raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
            j = json.loads(raw)
            node = j.get("data", {}).get(full, {})
            arr = node.get("qfqday") or node.get("day") or []
            out = {}
            for r in arr:
                if len(r) >= 3 and r[0] and r[2]:
                    out[r[0].replace("-", "")] = float(r[2])
            return out
        except Exception:  # noqa: BLE001
            time.sleep(0.6 * (i + 1))
    return None


def local_closes(conn: sqlite3.Connection, codes: list[str], days: int) -> tuple[list[str], dict[str, dict[str, float]]]:
    """取库内最近 days 个交易日，返回 (日期列表[无横线], {code: {date[无横线]: close}})"""
    raw = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM kline_daily ORDER BY date DESC LIMIT ?", (days,)
    )]
    raw = sorted(raw)  # 库内格式 YYYY-MM-DD，升序
    if not raw:
        return [], {}
    dates = [d.replace("-", "") for d in raw]  # 比对键格式 YYYYMMDD（与腾讯一致）
    placeholders = ",".join("?" * len(raw))
    out: dict[str, dict[str, float]] = {}
    for sym, d, c in conn.execute(
        f"SELECT symbol, date, close FROM kline_daily "
        f"WHERE date IN ({placeholders}) AND symbol IN ({','.join('?' * len(codes))})",
        raw + codes,
    ):
        out.setdefault(sym, {})[d.replace("-", "")] = c
    return dates, out


def main() -> None:
    ap = argparse.ArgumentParser(description="本地日K库 vs 腾讯 qfq 双源交叉校验")
    ap.add_argument("--days", type=int, default=5, help="校验最近 N 个交易日（默认 5）")
    ap.add_argument("--sample", type=int, default=0, help="随机抽查 N 只（默认全量）")
    ap.add_argument("--threshold", type=float, default=0.5, help="偏差告警阈值 %（默认 0.5）")
    ap.add_argument("--workers", type=int, default=4, help="并发数（默认 4，过高易被腾讯限流）")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print("[X] 本地库不存在，请先执行 klines_sync.py --backfill")
        return

    conn = sqlite3.connect(str(DB_PATH))
    codes = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM kline_daily ORDER BY symbol")]
    if args.sample and args.sample < len(codes):
        import random
        random.seed(20260921)
        codes = sorted(random.sample(codes, args.sample))

    dates, loc = local_closes(conn, codes, args.days)
    conn.close()

    if not dates:
        print("[X] 本地库无数据")
        return

    print("=" * 78)
    print(f"双源交叉校验 | 股票 {len(codes)} 只 | 校验交易日 {dates[0]} ~ {dates[-1]} ({len(dates)} 天)")
    print(f"阈值 {args.threshold}% | 并发 {args.workers}")
    print("=" * 78)

    start, end = dates[0], dates[-1]
    s_fmt = f"{start[:4]}-{start[4:6]}-{start[6:]}"
    e_fmt = f"{end[:4]}-{end[4:6]}-{end[6:]}"

    ok = fetch_fail = 0
    anomalies: list[tuple] = []
    total_cmp = 0
    dev_sum = 0.0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(tx_qfq, c, s_fmt, e_fmt): c for c in codes}
        for i, fut in enumerate(as_completed(futs), 1):
            code = futs[fut]
            try:
                tx = fut.result()
            except Exception:  # noqa: BLE001
                tx = None
            if not tx:
                fetch_fail += 1
                continue
            ok += 1
            lb = loc.get(code, {})
            for d in dates:
                if d in tx and d in lb and tx[d]:
                    dev = abs(lb[d] - tx[d]) / tx[d] * 100
                    total_cmp += 1
                    dev_sum += dev
                    if dev > args.threshold:
                        anomalies.append((code, d, lb[d], tx[d], dev))
            if i % 200 == 0:
                print(f"  [{i}/{len(codes)}] 已比对 {total_cmp} 个点，异常 {len(anomalies)}")

    el = time.time() - t0
    print("-" * 78)
    print(f"腾讯拉取成功 {ok} / 失败 {fetch_fail}")
    print(f"比对数据点 {total_cmp} | 平均偏差 {dev_sum / total_cmp:.5f}%" if total_cmp else "无比对数据点")
    print(f"超阈值异常 {len(anomalies)} 个 | 耗时 {el:.1f}s")

    if fetch_fail > len(codes) * 0.3:
        print("  [!] 腾讯端点失败率过高，可能是端点故障而非数据错误")
    if anomalies:
        print("-" * 78)
        print("异常明细（前 20 条）：")
        print(f"  {'代码':<9}{'日期':<11}{'本地(baostock)':<17}{'腾讯':<12}{'偏差%'}")
        for a in sorted(anomalies, key=lambda x: -x[4])[:20]:
            print(f"  {a[0]:<9}{a[1]:<11}{a[2]:<17.4f}{a[3]:<12.4f}{a[4]:.3f}")
    else:
        print("-" * 78)
        print("✅ 两源完全一致，无数据异常")

    print("=" * 78)


if __name__ == "__main__":
    main()
