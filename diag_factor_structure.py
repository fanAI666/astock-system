# -*- coding: utf-8 -*-
"""决定性判定：两源的复权因子序列结构

原理：真正的前复权因子 factor(t) 是「分段常数」——只在除权除息日跳变。
      复权后价 = 原始价 × factor(t)。
      故只要拿到「原始价」和「复权价」，就能反解 factor，再检验它是不是分段常数。

结论用途：判定「本地库 vs 腾讯」的偏差到底是谁的口径问题，
          以及长历史回测用哪一源更可信。
"""
import json
import sys
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
START, END = "2024-01-01", "2026-09-18"


def tx_fetch(code, mode):
    """mode: 'qfq' → qfqday（前复权）; 'raw' → day（不复权）"""
    full = ("sh" if code[0] in ("6", "9") else "sz") + code
    typ = "qfq" if mode == "qfq" else ""
    url = ("https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get?param=%s,day,%s,%s,800,%s"
           % (full, START, END, typ))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"})
    j = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
    node = j.get("data", {}).get(full, {})
    arr = node.get("qfqday") or node.get("day") or []
    return {r[0]: float(r[2]) for r in arr if len(r) >= 6}


def bs_fetch(code, adjustflag):
    import baostock as bs
    sym = ("sh." if code[0] in ("6", "9") else "sz.") + code
    rs = bs.query_history_k_data_plus(sym, "date,close", start_date=START, end_date=END,
                                      frequency="d", adjustflag=adjustflag)
    out = {}
    while rs.next():
        r = rs.get_row_data()
        if r[0] and r[1]:
            out[r[0]] = float(r[1])
    return out


def structure(name, series, dates):
    """检验序列是否分段常数；返回 (跳变次数, 相对跳变幅度列表)"""
    jumps, mags = [], []
    for i in range(1, len(dates)):
        a, b = series[dates[i - 1]], series[dates[i]]
        if a and b:
            rel = (b - a) / a
            if abs(rel) > 1e-4:
                jumps.append(dates[i])
                mags.append(rel * 100)
    print("   %-10s 跳变 %3d 次  最大幅度 %6.3f%%  >1%% 的跳变 %d 次"
          % (name, len(jumps), max([abs(m) for m in mags] + [0]), sum(1 for m in mags if abs(m) > 1)))
    return jumps, mags


def main():
    import baostock as bs
    lg = bs.login()
    if lg.error_code != "0":
        print("baostock 登录失败:", lg.error_msg)
        return 1

    for code in ("300750", "301310"):
        print("=" * 74)
        print("股票 %s" % code)
        bs_q = bs_fetch(code, "2")   # 前复权
        bs_r = bs_fetch(code, "3")   # 不复权
        tx_q = tx_fetch(code, "qfq")
        tx_r = tx_fetch(code, "raw")

        common = sorted(set(bs_q) & set(bs_r) & set(tx_q) & set(tx_r))
        print("   共同交易日 %d 根 (%s ~ %s)" % (len(common), common[0], common[-1]))

        # 1) 原始价是否一致（数据本身正确性）
        raw_dev = max(abs(bs_r[d] - tx_r[d]) / tx_r[d] * 100 for d in common)
        n_raw_diff = sum(1 for d in common if abs(bs_r[d] - tx_r[d]) > 0.005)
        print("   [原始价] 最大偏差 %.4f%%  不一致(>0.005元) %d 根" % (raw_dev, n_raw_diff))

        # 2) 各自反解的复权因子
        f_bs = {d: bs_q[d] / bs_r[d] for d in common}
        f_tx = {d: tx_q[d] / tx_r[d] for d in common}
        print("   反解复权因子 factor=复权价/原始价：")
        structure("本地(baostock)", f_bs, common)
        structure("腾讯(tx qfq)", f_tx, common)

        # 3) 因子比值序列（决定收益率偏差的直接原因）
        ratio = {d: f_bs[d] / f_tx[d] for d in common}
        structure("因子比值", ratio, common)

    bs.logout()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
