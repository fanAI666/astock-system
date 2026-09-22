# -*- coding: utf-8 -*-
"""重建上证指数 index_sh.json（baostock 版）

🔴 为什么要重建（2026-09-22 发现的生产级 bug）：
  原 `选股结果/index_sh.json` 只覆盖 **20240925 ~ 20260722**（440 根），而 G4 相对强度门
  依赖 `index.idxPos[dateD]` —— 指数缺失的交易日 `ir == null` → **G4 直接 continue**。
  后果有两个：
    1. 回测有效区间被锁死在 ~1.8 年，2022 起的长历史宇宙白白用不上（BT_FROM 怎么设都没用）
    2. **2026-07-23 之后的双创信号被静默全部剔除**（生产端正在持续丢信号）
  原 rebuild_index.py 依赖已停用的 tdx-connector，无法再更新 → 改走 baostock。

用法：
  python rebuild_index_baostock.py                     # 默认 2022-01-01 ~ 今天 → 选股结果/index_sh.json
  python rebuild_index_baostock.py <out> <beg> <end>   # 自定义
  python rebuild_index_baostock.py <out> <beg> <end> --check   # 只校验不写入

输出格式与原文件严格一致：{ name, code, setcode, bars:[[date,o,c,h,l,v],...] }
"""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import baostock as bs  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else r"D:\WorkBuddy\选股结果\index_sh.json")
BEG = sys.argv[2] if len(sys.argv) > 2 else "2022-01-01"
END = sys.argv[3] if len(sys.argv) > 3 else time.strftime("%Y-%m-%d")
CHECK_ONLY = "--check" in sys.argv
CODE = "sh.000001"


def fetch():
    for attempt in range(4):
        rs = bs.query_history_k_data_plus(
            CODE, "date,open,close,high,low,volume",
            start_date=BEG, end_date=END, frequency="d", adjustflag="3",  # 指数不复权
        )
        if rs.error_code != "0":
            print(f"  第{attempt + 1}次失败: {rs.error_msg}")
            time.sleep(3 * (attempt + 1))
            continue
        out = []
        while rs.next():
            r = rs.get_row_data()
            if not r[0] or not r[1]:
                continue
            try:
                out.append([r[0].replace("-", ""), float(r[1]), float(r[2]),
                            float(r[3]), float(r[4]), float(r[5] or 0)])
            except (TypeError, ValueError):
                continue
        if out:
            return out
        time.sleep(3 * (attempt + 1))
    return []


def main():
    print(f"拉取上证指数 {CODE}  {BEG} ~ {END}")
    if bs.login().error_code != "0":
        print("baostock 登录失败")
        return 1
    bars = fetch()
    bs.logout()
    if not bars:
        print("❌ 抓取为空")
        return 1
    print(f"  取到 {len(bars)} 根  {bars[0][0]} ~ {bars[-1][0]}")

    # 与现有文件交叉校验（重叠区间）
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
            o = {b[0]: b for b in old.get("bars", [])}
            n = {b[0]: b for b in bars}
            common = sorted(set(o) & set(n))
            if common:
                devs = [abs(o[d][2] - n[d][2]) / n[d][2] * 100 for d in common if n[d][2]]
                print(f"  与现有文件重叠 {len(common)} 根：收盘平均偏差 {sum(devs) / len(devs):.4f}%"
                      f"  最大 {max(devs):.4f}%")
                bad = [d for d in common if abs(o[d][2] - n[d][2]) / n[d][2] > 0.005]
                print(f"  偏差>0.5% 的天数：{len(bad)}" + (f"  {bad[:5]}" if bad else ""))
        except Exception as exc:  # noqa: BLE001
            print(f"  [!] 交叉校验跳过: {exc}")

    if CHECK_ONLY:
        print("--check 指定，不写入")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "name": "上证指数", "code": "000001", "setcode": 1, "bars": bars,
    }, ensure_ascii=False), encoding="utf-8")
    print(f"→ {OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
