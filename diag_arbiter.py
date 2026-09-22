# -*- coding: utf-8 -*-
"""仲裁：谁的复权收益率等于「真实价格收益率」

原理（不依赖第三方数据）：
  前复权的定义是 adj(t) = raw(t) × factor(t)。
  在**非除权日**，factor(t) 不变，于是
      adj(t)/adj(t-1) - 1 = raw(t)/raw(t-1) - 1
  即：复权收益率必须等于真实价格收益率。这是无失真序列的必要条件。

  已知（diag_factor_structure 实测）：两源的 raw 完全一致（0.0000%），
  且 baostock 的 factor 只跳变 6 次（= 真实除权次数），腾讯 qfq 跳变 510 次。

  故本测试只需统计：在 baostock factor 未跳变的日子（= 非除权日，占绝大多数），
  各源的复权收益率 与 raw 收益率 的偏离幅度。偏离越小 = 越贴近真实。
"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/WorkBuddy")
import klines_local as KL  # noqa: E402
import baostock as bs  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
START, END = "2024-01-01", "2026-09-18"


def tx_fetch(code, mode):
    full = ("sh" if code[0] in ("6", "9") else "sz") + code
    typ = "qfq" if mode == "qfq" else ""
    url = ("https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get?param=%s,day,%s,%s,800,%s"
           % (full, START, END, typ))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"})
    j = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
    node = j.get("data", {}).get(full, {})
    arr = node.get("qfqday") or node.get("day") or []
    return {r[0]: float(r[2]) for r in arr if len(r) >= 6}


def bs_fetch(code, flag):
    sym = ("sh." if code[0] in ("6", "9") else "sz.") + code
    rs = bs.query_history_k_data_plus(sym, "date,close", start_date=START, end_date=END,
                                      frequency="d", adjustflag=flag)
    out = {}
    while rs.next():
        r = rs.get_row_data()
        if r[0] and r[1]:
            out[r[0]] = float(r[1])
    return out


def main():
    if bs.login().error_code != "0":
        print("baostock 登录失败")
        return 1

    codes = sys.argv[1:] or ["300750", "301310", "688002"]
    print("非除权日 收益率失真检验 | %s ~ %s" % (START, END))
    print("=" * 78)
    tot_days = 0
    agg = {"baostock": [], "tencent": []}

    for code in codes:
        bs_q = bs_fetch(code, "2")
        bs_r = bs_fetch(code, "3")          # 不复权 = 真实价格
        tx_q = tx_fetch(code, "qfq")
        common = sorted(set(bs_q) & set(bs_r) & set(tx_q))
        if len(common) < 100:
            continue

        # baostock 的 factor 跳变日 = 除权日
        fac = {d: bs_q[d] / bs_r[d] for d in common}
        ex_days = set()
        for i in range(1, len(common)):
            d0, d1 = common[i - 1], common[i]
            if abs(fac[d1] - fac[d0]) / fac[d0] > 1e-6:
                ex_days.add(d1)

        dev_l, dev_t = [], []
        for i in range(1, len(common)):
            d0, d1 = common[i - 1], common[i]
            if d1 in ex_days:      # 跳过除权日（该日本就该与 raw 不同）
                continue
            r_raw = bs_r[d1] / bs_r[d0] - 1
            r_l = bs_q[d1] / bs_q[d0] - 1
            r_t = tx_q[d1] / tx_q[d0] - 1
            dev_l.append(abs(r_l - r_raw) * 100)
            dev_t.append(abs(r_t - r_raw) * 100)

        tot_days += len(dev_l)
        agg["baostock"] += dev_l
        agg["tencent"] += dev_t
        print("  %s  非除权日 %d 根 | 除权日 %d 个" % (code, len(dev_l), len(ex_days)))
        print("       baostock 平均偏离 %.6f%%  最大 %.6f%%"
              % (sum(dev_l) / len(dev_l), max(dev_l)))
        print("       腾讯qfq   平均偏离 %.6f%%  最大 %.6f%%"
              % (sum(dev_t) / len(dev_t), max(dev_t)))

    bs.logout()
    print("=" * 78)
    print("合计 %d 个非除权日" % tot_days)
    for k in ("baostock", "tencent"):
        v = agg[k]
        if v:
            print("  %-9s 平均偏离 %.6f%%   最大 %.6f%%   偏离>0.01%% 的天数 %d (%.1f%%)"
                  % (k, sum(v) / len(v), max(v),
                     sum(1 for x in v if x > 0.01), sum(1 for x in v if x > 0.01) / len(v) * 100))
    print("=" * 78)
    lb = sum(agg["baostock"]) / max(len(agg["baostock"]), 1)
    lt = sum(agg["tencent"]) / max(len(agg["tencent"]), 1)
    print("判定：" + ("✅ baostock 前复权无失真（非除权日收益率 == 真实价格收益率），回测应优先用本地库"
                    if lb < lt else "⚠️ 腾讯更贴近真实，本地库仅适合短期窗口"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
