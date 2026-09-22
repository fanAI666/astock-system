# -*- coding: utf-8 -*-
import os, re, glob

BASE = r"D:\WorkBuddy\选股结果"
ROLL = os.path.join(BASE, "每日简报.md")

# 1. 列出 dated 文件（YYYY-MM-DD.md / YYYY-MM-DD-xxx.md，排除 每日简报.md）
all_md = [f for f in os.listdir(BASE) if f.lower().endswith(".md") and f != "每日简报.md"]
pat = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-(.+))?\.md$")
dated = []
for f in all_md:
    m = pat.match(f)
    if m:
        dated.append((f, m.group(1), m.group(2)))  # (filename, date, suffix)

if not dated:
    print("今日无需归并")
    raise SystemExit(0)

# 2. 按日期降序
dated.sort(key=lambda x: x[1], reverse=True)

# 3. 读取滚动文件并拆分
if os.path.exists(ROLL):
    with open(ROLL, encoding="utf-8") as fh:
        roll = fh.read()
    # 按第一个 '## ' 拆分
    idx = roll.find("\n## ")
    if idx == -1:
        header = roll.rstrip("\n") + "\n"
        body = ""
    else:
        header = roll[:idx].rstrip("\n")
        body = roll[idx:]  # 含首行 '## '
    if not header.endswith("\n"):
        header += "\n"
else:
    header = "# 每日选股简报（滚动归档）\n\n> 本文件由每日收盘后策略选股自动化每日追加生成，历史简报归并于此；按日期倒序、最新在最前。\n"
    body = ""

# 解析 body 中已有的 '## YYYY-MM-DD' 段，用于重复防护
sec_pat = re.compile(r"^## (\d{4}-\d{2}-\d{2})", re.M)
def split_body_sections(body_text):
    """返回 {date: section_text} 与 原始顺序列表 [(date, section_text)]"""
    lines = body_text.split("\n")
    result = []
    cur_date = None
    cur = []
    for ln in lines:
        m = sec_pat.match(ln)
        if m:
            if cur_date is not None:
                result.append((cur_date, "\n".join(cur).strip("\n")))
            cur_date = m.group(1)
            cur = [ln]
        else:
            cur.append(ln)
    if cur_date is not None:
        result.append((cur_date, "\n".join(cur).strip("\n")))
    return result

existing = split_body_sections(body)
existing_map = {d: s for d, s in existing}
existing_dates = set(existing_map.keys())

merged = []      # 本次真正并入的新段 [(date, title, content)]
skipped = []     # 仅删除不并入的文件
for fname, date, suffix in dated:
    path = os.path.join(BASE, fname)
    with open(path, encoding="utf-8") as fh:
        content = fh.read().strip("\n")
    # 重复防护：若该日期段已存在于 body
    if date in existing_dates:
        ex_sec = existing_map[date]
        # 去标准化比较：dated 内容是否已是已有段的子集
        dated_norm = content.strip()
        ex_norm = ex_sec
        # 若 dated 内容完全包含于已有段 -> 视为子集 -> 只删不并
        if dated_norm in ex_norm or ex_norm.strip() == dated_norm:
            skipped.append(fname)
            os.remove(path)
            continue
        else:
            # 修正版：覆盖已有段（从 body 移除旧段，后续在顶部以新段插入）
            # 重建 body 去掉该日期旧段
            new_existing = [(d, s) for d, s in existing if d != date]
            body = "\n\n".join([s for d, s in new_existing if s.strip()])
            if body and not body.endswith("\n"):
                body += "\n"
            existing_map.pop(date, None)
            existing_dates.discard(date)
    title = f"## {date}" + (f"（{suffix}）" if suffix else "")
    merged.append((date, title, content))
    os.remove(path)

# 4. 组装：header + 空行 + 本次新段(降序) + 空行 + 历史主体
out = header.rstrip("\n") + "\n\n"
for date, title, content in merged:
    out += title + "\n\n" + content + "\n\n"
out = out.rstrip("\n") + "\n"
if body.strip():
    out += "\n" + body.strip() + "\n"

with open(ROLL, "w", encoding="utf-8") as fh:
    fh.write(out)

size = os.path.getsize(ROLL)
print(f"已归并文件数（新并入）: {len(merged)}")
print(f"仅删除不并入（重复防护）: {len(skipped)} -> {skipped}")
print(f"合并清单（降序）: {[d for d,_,_ in merged]}")
print(f"滚动文件字节数: {size}")
print(f"首段日期: {merged[0][0] if merged else '无（本次无新段）'}")
