import os, json, glob

d = r"C:/Users/fanfan/.workbuddy/projects/d-WorkBuddy/925680f7-b88a-408a-b476-c3f88660e22f/tool-results"
files = sorted(glob.glob(os.path.join(d, "*.txt")))
files = [f for f in files if "chatcmpl" not in f]
print("num files:", len(files))
for f in files:
    try:
        txt = open(f, encoding="utf-8", errors="replace").read()
    except Exception as e:
        print(f, "read err", e); continue
    # header line may precede JSON
    idx = txt.find("{")
    obj = json.loads(txt[idx:]) if idx >= 0 else None
    if not obj:
        print(os.path.basename(f), "NO JSON"); continue
    code = obj.get("Code")
    att = obj.get("AttachInfo") or {}
    name = att.get("Name") if isinstance(att, dict) else None
    rows = obj.get("Rows") or []
    stats = obj.get("Stats") or {}
    rbc = stats.get("RangeBarCount")
    second_in = "Second" in rows[0] if rows else False
    # detect period
    period = "min5" if (rows and "Second" in rows[0]) else "day"
    hdr = txt[:txt.find("\n")].strip() if "\n" in txt else txt[:80]
    print(f"{os.path.basename(f)[-12:]} | fileCode={code} name={name} | rows={len(rows)} rbc={rbc} period={period}")
    if rows:
        b0 = rows[0]; b1 = rows[-1]
        print(f"   first bar: Data={b0.get('Data')} O={b0.get('Open')} C={b0.get('Close')} V={b0.get('Volume')}")
        print(f"   last  bar: Data={b1.get('Data')} O={b1.get('Open')} C={b1.get('Close')} H={b1.get('High')} L={b1.get('Low')} V={b1.get('Volume')}")
        print(f"   hdr text: {hdr[:120]}")
