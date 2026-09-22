# -*- coding: utf-8 -*-
"""线上部署验证：首页 gate 检查 + import_final 大小/updated 比对 + 小文件 md5 逐字节比对"""
import urllib.request, hashlib, json, time, sys

BASE = "https://fanai666.github.io/astock-system/"
UA = {"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache", "Pragma": "no-cache"}

EXPECT_IMPORT_LEN = 25987505
EXPECT_UPDATED = "2026-08-25T15:59:33.317984+08:00"
EXPECT_MD5 = {
    "buy_signal.json": "21f5c693",
    "briefing_final.json": "4e0831ae",
    "chuang_signals.json": "7b111074",
    "fundflow.json": "b9a38664",
}


def head(url):
    req = urllib.request.Request(url, headers=UA, method="HEAD")
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.status, dict(r.headers)


def get_range(url, a, b):
    h = dict(UA)
    h["Range"] = "bytes=%d-%d" % (a, b)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def get_all(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read()


def check():
    ok = True
    # 1) 首页
    st, hd = head(BASE)
    print("[首页] HTTP", st, "Content-Length", hd.get("Content-Length"), "Last-Modified", hd.get("Last-Modified"))
    body = get_range(BASE, 18000, 30000).decode("utf-8", "ignore")
    gate = body.count('id="gate"')
    print("[首页] gate_count(@18000-30000) =", gate, "| 口令提示存在 =", ("访问口令" in body))
    if st != 200:
        ok = False

    # 2) import_final.json
    u = BASE + "data/import_final.json"
    st2, hd2 = head(u)
    cl = int(hd2.get("Content-Length", 0))
    print("[数据] HTTP", st2, "Content-Length", cl, "Last-Modified", hd2.get("Last-Modified"))
    print("      本地 blob   =", EXPECT_IMPORT_LEN, "| 一致 =", cl == EXPECT_IMPORT_LEN, "| >100000 =", cl > 100000)
    head_txt = get_range(u, 0, 500).decode("utf-8", "ignore")
    online_upd = None
    if '"updated"' in head_txt:
        seg = head_txt.split('"updated"', 1)[1]
        online_upd = seg.split('"')[1]
    print("      online updated =", online_upd, "| 本地 =", EXPECT_UPDATED, "| MATCH =", online_upd == EXPECT_UPDATED)
    if cl != EXPECT_IMPORT_LEN or online_upd != EXPECT_UPDATED:
        ok = False

    # 3) 小文件 md5
    for name, exp in EXPECT_MD5.items():
        try:
            s, b = get_all(BASE + "data/" + name)
            m = hashlib.md5(b).hexdigest()[:8]
            good = (m == exp)
            print("[md5] %-22s HTTP %s %7dB online=%s local=%s %s" % (name, s, len(b), m, exp, "MATCH" if good else "DIFF"))
            if not good:
                ok = False
        except Exception as e:
            print("[md5] %-22s ERROR %s" % (name, e))
            ok = False
    return ok


if __name__ == "__main__":
    for attempt in range(1, 5):
        print("=== 第 %d 轮验证 ===" % attempt)
        try:
            if check():
                print("\nALL_CONSISTENT: True")
                sys.exit(0)
        except Exception as e:
            print("轮次异常:", e)
        if attempt < 4:
            print("--> 未完全一致，30s 后复验\n")
            time.sleep(30)
    print("\nALL_CONSISTENT: False")
    sys.exit(1)
