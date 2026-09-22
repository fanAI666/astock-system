# -*- coding: utf-8 -*-
"""生成覆盖长历史的大盘开关指数（baostock 版，替代 fetch_switch_index.js 的腾讯端点）

背景：chuang/fetch_switch_index.js 的 BEG/END 写死 2023-08-28 ~ 2026-06-30，
      而「大盘开关指数的覆盖范围 = 回测区间的硬上限」—— 写死后 2022 起的长历史宇宙
      白白用不上（2026-09-22 实测：BT_FROM=20220101 与默认 20230828 结果完全一致，
      分年无 2023）。本脚本用 baostock 拉指数，可任意指定区间。

输出格式与 fetch_switch_index.js 严格一致：
  { updated, period:[beg,end], cyb:[[date,o,c,h,l,v],...], hs300:[...] }
  日期为紧凑 'YYYYMMDD'，价格顺序 [open, close, high, low, volume]
"""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import baostock as bs  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else r"D:\WorkBuddy\选股结果\switch_index_ext.json")
BEG = sys.argv[2] if len(sys.argv) > 2 else "2022-01-01"
END = sys.argv[3] if len(sys.argv) > 3 else "2026-09-21"

# 创业板指 / 沪深300（baostock 指数代码）
CODES = {"cyb": "sz.399006", "hs300": "sh.000300"}


def fetch(code):
    for attempt in range(4):
        rs = bs.query_history_k_data_plus(
            code, "date,open,close,high,low,volume",
            start_date=BEG, end_date=END, frequency="d", adjustflag="3",  # 指数不复权
        )
        if rs.error_code != "0":
            print(f"    [{code}] 第{attempt + 1}次失败: {rs.error_msg}")
            time.sleep(3 * (attempt + 1))
            continue
        out = []
        while rs.next():
            r = rs.get_row_data()
            if not r[0] or not r[1]:
                continue
            try:
                out.append([r[0].replace("-", ""), float(r[1]), float(r[2]),
                            float(r[3]), float(r[4]), int(float(r[5] or 0))])
            except (TypeError, ValueError):
                continue
        if out:
            return out
        time.sleep(3 * (attempt + 1))
    return []


def main():
    if bs.login().error_code != "0":
        print("baostock 登录失败")
        return 1
    print(f"拉取指数 {BEG} ~ {END}")
    data = {}
    for key, code in CODES.items():
        bars = fetch(code)
        print(f"  {key}({code}): {len(bars)} 根"
              + (f"  {bars[0][0]} ~ {bars[-1][0]}" if bars else "  ❌ 空"))
        if not bars:
            bs.logout()
            return 1
        data[key] = bars
    bs.logout()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "updated": time.strftime("%Y-%m-%d"),
        "period": [BEG.replace("-", ""), END.replace("-", "")],
        "cyb": data["cyb"],
        "hs300": data["hs300"],
    }, ensure_ascii=False), encoding="utf-8")
    print(f"→ {OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
