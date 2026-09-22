import re, glob, os

BASE = r"D:\WorkBuddy\选股结果"
ROLL = os.path.join(BASE, "每日简报.md")

# 1. 收集 dated 文件
dated = []
for fn in os.listdir(BASE):
    p = os.path.join(BASE, fn)
    if not os.path.isfile(p) or not fn.endswith(".md"):
        continue
    if fn == "每日简报.md":
        continue
    m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:-(.+))?\.md$", fn)
    if m:
        dated.append((m.group(1), m.group(2), fn, p))

if not dated:
    print("今日无需归并")
    raise SystemExit(0)

# 2. 降序排列（最新日期在前）
dated.sort(key=lambda x: x[0], reverse=True)

# 3. 读取滚动文件，拆分头部元信息与历史主体
txt = open(ROLL, encoding="utf-8").read()
m = re.search(r"(?m)^## ", txt)
if m:
    header_meta = txt[:m.start()]
    history_body = txt[m.start():]
else:
    # 无 ## 段时，整份当作头部；需要建立首行
    if txt.strip() == "":
        header_meta = "# 每日选股简报（滚动归档）\n\n> 本文件由每日收盘后策略选股自动化每日追加生成，历史简报归并于此；按日期倒序、最新在最前。\n"
    else:
        header_meta = txt
    history_body = ""

# 4. 生成新段（降序）
new_segs = []
for date, suffix, fn, p in dated:
    content = open(p, encoding="utf-8").read().strip("\n")
    heading = "## " + date + (f"（{suffix}）" if suffix else "")
    new_segs.append(heading + "\n\n" + content)

new_block = "\n\n".join(new_segs)

# 5. 写回
final = header_meta.rstrip("\n") + "\n\n" + new_block.strip("\n") + "\n\n" + history_body.lstrip("\n")
with open(ROLL, "w", encoding="utf-8") as f:
    f.write(final)

# 6. 删除 dated 原文件
for date, suffix, fn, p in dated:
    os.remove(p)

print("MERGED", len(dated), "files:", [d[2] for d in dated])
print("FIRST_SEG_DATE", dated[0][0])
print("ROLL_BYTES", len(final.encode("utf-8")))
