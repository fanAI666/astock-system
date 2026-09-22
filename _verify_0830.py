import urllib.request, time, json, sys

HOME = "https://fanai666.github.io/astock-system/"
DATA = HOME + "data/import_final.json"
LOCAL_BLOB = 31031269
LOCAL_UPDATED = "2026-08-28T17:23:41.685900+08:00"
LOCAL_ITEMS = 197

def req(url, method="GET", headers=None, timeout=30):
    h = {"User-Agent": "verify/1.0"}
    if headers: h.update(headers)
    r = urllib.request.Request(url, method=method, headers=h)
    return urllib.request.urlopen(r, timeout=timeout)

def get_head(url):
    with req(url, method="HEAD") as r:
        return r.status, dict(r.getheaders())

def read_range(url, start, end):
    with req(url, headers={"Range": f"bytes={start}-{end}"}) as r:
        return r.read()

def find_updated(b):
    # b is bytes; find "updated" near the start
    s = b.decode("utf-8", "ignore")
    i = s.find('"updated"')
    if i < 0:
        return None
    j = s.find(":", i)
    k = s.find('"', j+1)
    l = s.find('"', k+1)
    return s[k+1:l]

ok = False
for attempt in range(1, 4):
    print(f"\n===== verify attempt {attempt} =====")
    try:
        # homepage
        st, hd = get_head(HOME)
        cl_home = int(hd.get("Content-Length", 0))
        body = read_range(HOME, 0, 3000).decode("utf-8", "ignore")
        gate = 'id="gate"' in body
        lm_home = hd.get("Last-Modified")
        print(f"home: HTTP {st} Content-Length={cl_home} gate={gate} Last-Modified={lm_home}")

        # data
        st2, hd2 = get_head(DATA)
        cl_data = int(hd2.get("Content-Length", 0))
        head = read_range(DATA, 0, 600).decode("utf-8", "ignore")
        updated = find_updated(head.encode("utf-8"))
        print(f"data: HTTP {st2} Content-Length={cl_data} updated={updated}")
        print(f"data >100000? {cl_data>100000}  |  blob match(local={LOCAL_BLOB})? {cl_data==LOCAL_BLOB}  |  updated match? {updated==LOCAL_UPDATED}")

        if st == 200 and gate and cl_data > 100000 and cl_data == LOCAL_BLOB and updated == LOCAL_UPDATED:
            print(">>> ALL CHECKS PASS: online == local latest (08-28)")
            ok = True
            break
        else:
            print(">>> not yet consistent, waiting 30s ...")
    except Exception as e:
        print("ERROR:", repr(e))
    if attempt < 3:
        time.sleep(30)

print("\nRESULT ok=", ok)
sys.exit(0 if ok else 1)
