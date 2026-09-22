# -*- coding: utf-8 -*-
"""阶段四决定性验证：长历史「逐日收益率序列」一致性

为什么必须测收益率而不是价格水平：
  - 前复权的「价格水平」取决于复权基准，两源基准不同时水平会有整体缩放（无害）
  - 但回测真正吃的是**收益率序列**：若两源在除权日的处理不同，收益率会在该日出现
    巨幅偏差，直接改变回测结论
  - 故只比对：逐日收益率的最大偏差 + 大偏差（>1%）出现的次数与日期
"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/WorkBuddy")
import klines_local as KL  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
START = "2024-01-01"
END = "2026-09-18"


def fetch_tx_long(code):
    """腾讯 qfq 长区间（一次请求可返回数百根）"""
    full = ("sh" if code[0] in ("6", "9") else "sz") + code
    url = ("https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get?param=%s,day,%s,%s,800,qfq"
           % (full, START, END))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"})
    j = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
    node = j.get("data", {}).get(full, {})
    arr = node.get("qfqday") or node.get("day") or []
    out = {}
    for r in arr:
        if len(r) >= 6:
            out[r[0]] = float(r[2])
    return out


def main():
    codes = sys.argv[1:] or ["600000", "000001", "600519", "300750", "688002", "301310",
                             "600664", "002127", "603127", "688621"]
    print("长历史收益率序列一致性 | %s ~ %s | %d 只" % (START, END, len(codes)))
    print("=" * 76)

    tot_bars = tot_big = 0
    worst = 0.0
    worst_info = ""
    level_devs = []

    for code in codes:
        lb = KL.recent_bars(code, START, END)
        if not lb:
            print("  %s 库内无数据，跳过" % code)
            continue
        try:
            tx = fetch_tx_long(code)
        except Exception as exc:  # noqa: BLE001
            print("  %s 腾讯取数失败: %s" % (code, str(exc)[:40]))
            continue

        lp = {b[0]: b[2] for b in lb}
        common = sorted(set(lp) & set(tx))
        if len(common) < 100:
            print("  %s 重叠仅 %d 根，跳过" % (code, len(common)))
            continue

        big = 0
        mx = 0.0
        mx_date = ""
        for i in range(1, len(common)):
            d0, d1 = common[i - 1], common[i]
            if not lp[d0] or not tx[d0]:
                continue
            ra = (lp[d1] - lp[d0]) / lp[d0]
            rb = (tx[d1] - tx[d0]) / tx[d0]
            dev = abs(ra - rb) * 100
            if dev > mx:
                mx, mx_date = dev, d1
            if dev > 1.0:
                big += 1
        # 价格水平偏差（仅参考）
        lvl = max(abs(lp[d] - tx[d]) / tx[d] * 100 for d in common)
        level_devs.append(lvl)

        tot_bars += len(common)
        tot_big += big
        if mx > worst:
            worst, worst_info = mx, "%s @ %s" % (code, mx_date)
        print("  %s  重叠%4d根  日收益最大偏差 %.4f%%  大偏差(>1%%) %d 次  水平最大偏差 %.3f%%"
              % (code, len(common), mx, big, lvl))

    print("=" * 76)
    print("合计比对各 %d 个交易日" % tot_bars)
    print("日收益最大偏差 : %.4f%%  (%s)" % (worst, worst_info or "-"))
    print("大偏差(>1%%)次数: %d" % tot_big)
    if level_devs:
        print("价格水平最大偏差: %.3f%%  （前复权基准差异，对收益率无影响）" % max(level_devs))
    print("=" * 76)
    verdict = tot_big == 0
    print("结论：" + ("✅ 收益率序列一致 → 长历史回测结论可信" if verdict
                    else "⚠️ 存在除权日处理差异，需逐笔排查上表大偏差日期"))
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
