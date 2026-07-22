import json, datetime

# 大盘(上证指数 000001)硬过滤：信号日上证收盘 < MA20 → 当日全市场不交易。
#
# ⚠️ 数值校验(重要)：回测脚本 backtest_winrate.js 曾因 index_sh.json 的收盘是
#    字符串('9.600000')而未转 float，导致 MA20 变成字符串拼接、'< '退化为字典序比较，
#    大盘过滤静默失效(空头日交易被误判为正常)。本脚本所有指数收盘必须经 to_num() 强制转数，
#    并在比较前用 assert 守卫，杜绝同类 bug。
#
# 数据源：优先使用与回测同源的 index_sh.json 做【方向交叉校验】；因 index_sh.json 的量纲
#        (≈真实值/350) 与展示量纲不一致，输出仍以 EMBEDDED 真实量纲行(手动快照)为准。

INDEX_FILE = r"D:\WorkBuddy\选股结果\index_sh.json"
OUT = r"D:\WorkBuddy\选股结果\buy_signal.json"


def to_num(x, ctx="index close"):
    """强制转 float，失败即报错(不做静默字符串比较)。"""
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise TypeError(f"[数值校验失败] {ctx} 无法转为 float: {x!r} (类型 {type(x).__name__})")
    if v != v:  # NaN 守卫
        raise ValueError(f"[数值校验失败] {ctx} 为 NaN")
    return v


# Extracted closes from tdx_kline(000001, setcode=1, period=4) — Rows in date order
# (date, close). 真实量纲(与展示一致)。Last row 20260721 is the current trading-day partial bar.
EMBEDDED = [
    ("20260526", 4145.37), ("20260527", 4093.73), ("20260528", 4098.64), ("20260529", 4068.57),
    ("20260601", 4057.74), ("20260602", 4075.10), ("20260603", 4083.97), ("20260604", 4057.78),
    ("20260605", 4027.74), ("20260608", 3959.34), ("20260609", 4010.03), ("20260610", 3993.23),
    ("20260611", 3987.01), ("20260612", 4031.51), ("20260615", 4096.47), ("20260616", 4091.89),
    ("20260617", 4108.08), ("20260618", 4090.48), ("20260622", 4163.10), ("20260623", 4106.25),
    ("20260624", 4110.81), ("20260625", 4120.28), ("20260626", 4027.26), ("20260629", 4073.90),
    ("20260630", 4094.40), ("20260701", 4112.45), ("20260702", 4028.90), ("20260703", 4043.64),
    ("20260706", 4041.24), ("20260707", 3990.24), ("20260708", 3970.88), ("20260709", 4036.59),
    ("20260710", 3996.16), ("20260713", 3913.79), ("20260714", 3967.13), ("20260715", 3955.58),
    ("20260716", 3882.41), ("20260717", 3764.15), ("20260720", 3796.28), ("20260721", 3819.66),
]
# 全部转数(防御：即便有人把 EMBEDDED 改成字符串也不会出错)
EMBEDDED = [(d, to_num(c, f"EMBEDDED[{d}]")) for d, c in EMBEDDED]


def compute_bearish(rows, label):
    """rows: list[(date, close_float)]；返回 (latest_date, latest_close, ma20, bear)。"""
    if len(rows) < 20:
        raise ValueError(f"{label}: 指数数据不足 20 根，无法计算 MA20 (仅有 {len(rows)} 根)")
    last = rows[-1]
    completed = rows[:-1]  # 剔除最后一根未完成的当日棒
    last_completed = completed[-1]
    window = completed[-20:]
    ma20 = sum(c for _, c in window) / 20
    latest_close = to_num(last_completed[1], f"{label} latest close")
    ma20 = to_num(ma20, f"{label} MA20")
    assert isinstance(latest_close, float) and isinstance(ma20, float), \
        f"[数值校验失败] {label}: 比较操作数非数值 ({type(latest_close)}, {type(ma20)})"
    bear = latest_close < ma20
    return last_completed[0], latest_close, ma20, bear


# ---- 主路径：EMBEDDED 真实量纲(权威输出) ----
last_completed_date, latest_close, ma20, bear = compute_bearish(EMBEDDED, "EMBEDDED")
index_source = "embedded(真实量纲快照)"

# ---- 交叉校验：index_sh.json 同源方向(量纲不同，仅比对 bearish 方向) ----
cross_note = "未做交叉校验"
try:
    with open(INDEX_FILE, encoding="utf-8") as f:
        idx = json.load(f)
    ibars = idx.get("bars") or []
    ix_rows = [(b[0], to_num(b[2], f"index_sh[{b[0]}]")) for b in ibars]
    if len(ix_rows) >= 20:
        _, _, ix_ma20, ix_bear = compute_bearish(ix_rows, "index_sh.json")
        agree = (ix_bear == bear)
        cross_note = f"index_sh.json 方向={'空头' if ix_bear else '多头'}，" \
                     f"{'✅与EMBEDDED一致' if agree else '⚠️与EMBEDDED不一致，请人工核对'}"
        if not agree:
            print("⚠️ 警告：index_sh.json 与 EMBEDDED 对大盘多空判断不一致！")
    else:
        cross_note = "index_sh.json 数据不足，跳过交叉校验"
except Exception as e:
    cross_note = f"交叉校验跳过(读取失败: {e})"

print("指数数据源:", index_source)
print("last completed bar:", last_completed_date, "close=", latest_close)
print("MA20 (last 20 completed bars):", round(ma20, 4))
print("latest_close < MA20 ?", bear)
print("gap %:", round((latest_close - ma20) / ma20 * 100, 3))
print("MARKET:", "BEAR (空头)" if bear else "BULL (多头)")
print("交叉校验:", cross_note)

result = {
    "date": "2026-07-21",
    "baselineDate": "2026-07-17",
    "top3": [],
    "trade": False,
    "reason": "大盘空头(上证<MA20)" if bear else "大盘多头",
    "market": {
        "shIndex": "000001",
        "lastCompletedDate": last_completed_date,
        "lastCompletedClose": latest_close,
        "ma20": round(ma20, 4),
        "belowMa20": bear,
        "note": f"按惯例剔除当日(20260721)盘中未完成棒；最新已完成收盘{latest_close}({last_completed_date}) < MA20≈{round(ma20,2)} → {'空头' if bear else '多头'}。数值已强制float校验。",
        "indexSource": index_source,
        "numericValidated": True,
        "crossCheck": cross_note,
    },
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print("WROTE", OUT)
