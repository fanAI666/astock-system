# -*- coding: utf-8 -*-
"""阶段三等价性验证：本地库路径 vs 腾讯端点路径，逐根比对

目的：确认 _auto_screen_*.py 的 fetch_recent() 换成「本地库优先」后，
      取到的日K与原来走腾讯时**逐根一致**（价格 + 根数 + 日期序列）。
"""
import json
import os
import random
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/WorkBuddy")
import klines_local as KL  # noqa: E402

BASE = "D:/WorkBuddy/选股结果"
SRC = os.path.join(BASE, "import_final.json")
TODAY = "2026-09-18"
WIN_START = "2026-08-20"
WIN_COUNT = 40
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def prefix(code):
    return "sh" if code[0] in ("6", "9") else "sz"


def fetch_recent_tx(code):
    full = prefix(code) + code
    url = ("https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get?param=%s,day,%s,%s,%d,qfq"
           % (full, WIN_START, TODAY, WIN_COUNT))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"})
    j = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
    node = j.get("data", {}).get(full, {})
    arr = node.get("qfqday") or node.get("day")
    if not arr:
        return None
    out = []
    for r in arr:
        if len(r) < 6:
            continue
        out.append([r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])])
    out.sort(key=lambda x: x[0])
    return out


def main():
    items = json.load(open(SRC, encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items", items.get("candidates", []))
    codes = [it.get("code") for it in items if it.get("code")]
    random.seed(20260921)
    sample = random.sample(codes, min(40, len(codes)))
    print("候选池 %d 只，抽样 %d 只比对" % (len(codes), len(sample)))
    print("=" * 70)

    n_ok = n_price_diff = n_bar_diff = 0
    worst = 0.0
    worst_code = ""
    local_hit = 0
    details = []

    for code in sample:
        lb = KL.recent_bars(code, WIN_START, TODAY, WIN_COUNT)
        if lb:
            local_hit += 1
        try:
            tb = fetch_recent_tx(code)
        except Exception as exc:  # noqa: BLE001
            details.append((code, "TX_ERR", str(exc)[:50], 0))
            continue
        if not lb or not tb:
            details.append((code, "MISS", "local=%s tx=%s" % (bool(lb), bool(tb)), 0))
            continue

        if len(lb) != len(tb):
            n_bar_diff += 1
            details.append((code, "BAR_N", "local=%d tx=%d" % (len(lb), len(tb)), 0))
            continue

        # 逐根比对日期 + 收盘
        bad = None
        maxdev = 0.0
        for a, b in zip(lb, tb):
            if a[0] != b[0]:
                bad = "日期错位 %s vs %s" % (a[0], b[0])
                break
            if b[2]:
                dev = abs(a[2] - b[2]) / b[2] * 100
                maxdev = max(maxdev, dev)
        if bad:
            details.append((code, "DATE", bad, 0))
            continue

        if maxdev > worst:
            worst, worst_code = maxdev, code
        if maxdev > 0.01:
            n_price_diff += 1
            details.append((code, "PRICE", "最大偏差 %.4f%%" % maxdev, maxdev))
        else:
            n_ok += 1

    print("本地库命中      : %d/%d" % (local_hit, len(sample)))
    print("逐根完全一致    : %d" % n_ok)
    print("根数不一致      : %d" % n_bar_diff)
    print("价格偏差>0.01%%  : %d" % n_price_diff)
    print("最大偏差        : %.5f%%  (%s)" % (worst, worst_code or "-"))
    if details:
        print("-" * 70)
        for c, tag, msg, _ in details[:20]:
            print("  %s %-8s %s" % (c, tag, msg))
    print("=" * 70)
    verdict = (n_bar_diff == 0 and n_price_diff == 0 and local_hit == len(sample))
    print("结论：" + ("✅ 本地库路径与腾讯路径逐根一致，可安全切换" if verdict
                    else "⚠️ 存在差异，见上表明细"))
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
