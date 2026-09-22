# -*- coding: utf-8 -*-
"""诊断：本地库 vs 腾讯 的长历史偏差结构

判据：
  - 若 ratio = local/tx 是「分段常数」（在除权日跳变）→ 复权基准差异，收益率仅除权日不同
  - 若是随机噪声 → 精度问题
  - 逐日定位 >1% 的收益率偏差，打印前后各 3 根的原始数据
"""
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/WorkBuddy")
import klines_local as KL  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
START, END = "2024-01-01", "2026-09-18"


def fetch_tx_long(code):
    full = ("sh" if code[0] in ("6", "9") else "sz") + code
    url = ("https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get?param=%s,day,%s,%s,800,qfq"
           % (full, START, END))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"})
    j = __import__("json").loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
    node = j.get("data", {}).get(full, {})
    arr = node.get("qfqday") or node.get("day") or []
    return {r[0]: (float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in arr if len(r) >= 6}


for code in ("300750", "301310", "688002"):
    lb = KL.recent_bars(code, START, END)
    tx = fetch_tx_long(code)
    lp = {b[0]: b[2] for b in lb}
    common = sorted(set(lp) & set(tx))
    ratios = [(d, lp[d] / tx[d][1]) for d in common if tx[d][1]]
    rmin = min(r for _, r in ratios)
    rmax = max(r for _, r in ratios)
    print("=" * 78)
    print("%s  ratio(L/TX) 区间 %.6f ~ %.6f   跨度 %.4f%%" % (code, rmin, rmax, (rmax - rmin) * 100))

    # 分段常数检验：ratio 变化点
    jumps = []
    for i in range(1, len(ratios)):
        if abs(ratios[i][1] - ratios[i - 1][1]) / ratios[i - 1][1] > 1e-4:
            jumps.append((ratios[i][0], ratios[i - 1][1], ratios[i][1]))
    print("  ratio 变化点(>0.01%%) 共 %d 个" % len(jumps))
    for d, a, b in jumps[:8]:
        print("     %s  %.6f -> %.6f  (%.3f%%)" % (d, a, b, (b / a - 1) * 100))

    # 逐日收益率偏差
    bigs = []
    for i in range(1, len(common)):
        d0, d1 = common[i - 1], common[i]
        ra = (lp[d1] - lp[d0]) / lp[d0]
        rb = (tx[d1][1] - tx[d0][1]) / tx[d0][1]
        if abs(ra - rb) * 100 > 1.0:
            bigs.append((d1, ra * 100, rb * 100, (ra - rb) * 100))
    print("  >1%% 收益率偏差 %d 处:" % len(bigs))
    for d1, ra, rb, dd in bigs:
        print("     %s  本地 %.2f%%  腾讯 %.2f%%  差 %.2f%%" % (d1, ra, rb, dd))
    # 打印最大偏差日附近
    if bigs:
        d = bigs[0][0]
        idx = common.index(d)
        print("  明细（%s 前后 3 根）:" % d)
        for j in range(max(0, idx - 3), min(len(common), idx + 2)):
            dd0 = common[j]
            print("     %s  本地close=%.4f  腾讯close=%.4f  ratio=%.6f"
                  % (dd0, lp[dd0], tx[dd0][1], lp[dd0] / tx[dd0][1]))
