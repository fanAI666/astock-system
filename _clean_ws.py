# -*- coding: utf-8 -*-
"""清理工作区：删除日期化一次性脚本（保留白名单），并处理会话目录与回收区。

用法：
  python _clean_ws.py scripts   # 删除剩余日期化脚本
  python _clean_ws.py sessions  # 会话导出目录移入回收区
  python _clean_ws.py trash     # 彻底删除回收区中的废数据（保留 sessions/）
"""
import os
import shutil
import subprocess
import sys

BASE = r"D:\WorkBuddy"
TRASH = os.path.join(BASE, "_trash_20260922")
KEEP = {"_auto_screen_0918.py", "_patch_today_0901.py"}

sys.stdout.reconfigure(encoding="utf-8")


def dated_scripts() -> list[str]:
    import re
    pat = re.compile(r"[0-9]{4}\.(py|js)$")
    out = []
    for f in os.listdir(BASE):
        fp = os.path.join(BASE, f)
        if os.path.isfile(fp) and pat.search(f) and f not in KEEP:
            out.append(f)
    return sorted(out)


def cmd_scripts() -> None:
    files = dated_scripts()
    print("待删除日期化脚本:", len(files))
    n = 0
    for f in files:
        try:
            os.remove(os.path.join(BASE, f))
            n += 1
        except Exception as exc:  # noqa: BLE001
            print("  删除失败", f, exc)
    print("已删除:", n)
    print("剩余:", len(dated_scripts()))


def cmd_sessions() -> None:
    dst = os.path.join(TRASH, "sessions")
    os.makedirs(dst, exist_ok=True)
    moved = 0
    for d in sorted(os.listdir(BASE)):
        fp = os.path.join(BASE, d)
        if not os.path.isdir(fp) or not d.startswith("2026-"):
            continue
        target = os.path.join(dst, d)
        try:
            shutil.move(fp, target)
            moved += 1
            print("  moved:", d)
        except Exception as exc:  # noqa: BLE001
            print("  失败", d, exc)
    print("会话目录已移入回收区:", moved)


def cmd_trash() -> None:
    """彻底删除回收区废数据，但保留 sessions/（含其他项目交付物，需用户确认）。"""
    keep_dirs = {"sessions"}
    removed = freed = 0
    for name in sorted(os.listdir(TRASH)):
        if name in keep_dirs:
            continue
        fp = os.path.join(TRASH, name)
        try:
            size = os.path.getsize(fp) if os.path.isfile(fp) else sum(
                os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(fp) for f in fs
            )
            if os.path.isfile(fp):
                os.remove(fp)
            else:
                shutil.rmtree(fp)
            removed += 1
            freed += size
            print("  deleted:", name, f"({size / 1024 / 1024:.1f}MB)")
        except Exception as exc:  # noqa: BLE001
            print("  失败", name, exc)
    print(f"回收区已清理 {removed} 项，释放 {freed / 1024 / 1024:.1f}MB（sessions/ 保留）")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    {"scripts": cmd_scripts, "sessions": cmd_sessions, "trash": cmd_trash}[cmd]()


if __name__ == "__main__":
    main()
