import urllib.request, json, sys

BASE="https://fanai666.github.io/astock-system/"

def get_head(url):
    req=urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.getheaders())
    except Exception as e:
        return None, str(e)

def get_range(url, start, end):
    req=urllib.request.Request(url)
    req.add_header("Range", f"bytes={start}-{end}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8","ignore")
    except Exception as e:
        return None, str(e)

def get_full(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=40) as r:
            return r.status, r.read().decode("utf-8","ignore")
    except Exception as e:
        return None, str(e)

print("=== 1) 首页 ===")
st, body = get_full(BASE)
if st==200:
    print("HTTP", st, "len", len(body))
    print("gate_count=", body.count('id="gate"'))
    print("含口令提示:", ("访问口令" in body) or ("请输入" in body))
else:
    print("HTTP", st, body)

print("=== 2) data/import_final.json HEAD ===")
st, h = get_head(BASE+"data/import_final.json")
if st==200:
    cl=h.get("Content-Length")
    print("HTTP", st, "Content-Length", cl)
    print(">100000:", int(cl)>100000)
else:
    print("HTTP", st, h)

print("=== 3) 线上 import_final updated 比对 ===")
st, chunk = get_range(BASE+"data/import_final.json", 0, 400)
if st in (200,206):
    # find updated field
    import re
    m=re.search(r'"updated"\s*:\s*"([^"]+)"', chunk)
    print("online updated =", m.group(1) if m else "(not found in 0-400)")
else:
    print("range HTTP", st, chunk)
