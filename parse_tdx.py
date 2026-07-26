# -*- coding: utf-8 -*-
"""Parse tdx_kline MCP cache files -> internal kline dict.
Usage:
  python parse_tdx.py report           # only report what caches contain
  python parse_tdx.py merge            # merge into 选股结果/universe_klines.json (board from code prefix)
"""
import os, re, sys, json, glob

TOOLDIR = r"C:\Users\fanfan\.workbuddy\projects\d-WorkBuddy\c7177000-18dd-4fed-a648-d95908a45305\tool-results"
UNIVERSE = r"D:\WorkBuddy\选股结果\universe_klines.json"

def board_of(code):
    if code.startswith("30"): return "cyb"
    if code.startswith("688"): return "kcb"
    if code.startswith(("60",)): return "main"
    return "other"

def parse_file(path):
    txt = open(path, "r", encoding="utf-8", errors="ignore").read()
    # JSON starts at first '{' after the '详细K线数据:' marker (fallback: first '{')
    m = re.search(r"详细K线数据\s*[:：]", txt)
    start = txt.find("{", m.end()) if m else txt.find("{")
    if start < 0: return None
    blob = txt[start:]
    try:
        obj = json.loads(blob)
    except Exception:
        # try trimming to last closing brace
        end = blob.rfind("}")
        try: obj = json.loads(blob[:end+1])
        except Exception: return None
    code = str(obj.get("Code") or "").zfill(6)
    name = (obj.get("AttachInfo") or {}).get("Name") or ""
    rows = obj.get("Rows") or []
    out = []
    for r in rows:
        try:
            d = str(r.get("Data"))
            o = float(r.get("Open")); c = float(r.get("Close"))
            h = float(r.get("High")); l = float(r.get("Low"))
            v = float(r.get("Volume") or 0)
            out.append([d, o, c, h, l, v])
        except Exception:
            continue
    out.sort(key=lambda x: x[0])
    return {"code": code, "name": name, "kline": out}

def collect():
    files = sorted(glob.glob(os.path.join(TOOLDIR, "*tdx_kline-*.txt")),
                   key=os.path.getmtime)
    res = {}
    for f in files:
        p = parse_file(f)
        if not p or not p["code"] or not p["kline"]: continue
        code = p["code"]
        # keep the cache with the most bars for a given code
        if code not in res or len(p["kline"]) > len(res[code]["kline"]):
            res[code] = p
    return res

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "report"
    res = collect()
    print("parsed codes:", len(res))
    byb = {}
    for c, p in res.items():
        byb.setdefault(board_of(c), []).append(c)
    for b, cs in sorted(byb.items()):
        print(f"  {b}: {len(cs)}")
    # detail
    for c in sorted(res):
        p = res[c]; k = p["kline"]
        print(f"    {c} {p['name']:<8} {len(k):>4} bars  {k[0][0]}~{k[-1][0]}")
    if mode == "merge":
        uni = json.load(open(UNIVERSE, "r", encoding="utf-8"))
        # cleanup: remove stray top-level 6-digit code keys (wrongly added by earlier buggy merge)
        stray = [k for k in list(uni.keys()) if re.fullmatch(r"\d{6}", k)]
        for k in stray: uni.pop(k)
        if stray: print(f"cleaned {len(stray)} stray top-level keys: {stray}")
        items = uni.setdefault("items", [])
        idx = {it["code"]: it for it in items}
        added = 0; upd = 0
        for c, p in res.items():
            b = board_of(c)
            if b not in ("cyb", "kcb"):  # only merge 双创
                continue
            kl = [[str(d), float(o), float(cc), float(h), float(l), int(v)]
                  for (d, o, cc, h, l, v) in p["kline"]]
            if c in idx:
                if len(kl) > len(idx[c].get("kline", {}).get("day", [])):
                    idx[c]["kline"] = {"day": kl}; upd += 1
            else:
                items.append({"code": c, "name": p["name"], "board": b, "kline": {"day": kl}})
                idx[c] = items[-1]; added += 1
        json.dump(uni, open(UNIVERSE, "w", encoding="utf-8"), ensure_ascii=False)
        from collections import Counter
        print(f"MERGED -> +{added} new, {upd} updated; items total={len(items)}; boards={dict(Counter(it['board'] for it in items))}")
