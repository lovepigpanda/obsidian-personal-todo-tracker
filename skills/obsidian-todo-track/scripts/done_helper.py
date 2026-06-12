#!/usr/bin/env python3
"""
done_helper.py - 将 ACTIVE/ 下的 todo 标 done 并移到 DONE/ (V1.0.5)

用法:
    # 单笔 done (按 path 精确指定)
    python3 scripts/done_helper.py \
        --vault ~/Obsidian/todo \
        --file "ACTIVE/2026-06-09-开用户-P0-ACTIVE.md"

    # 按 slug 模糊搜索 (title 含关键词)
    python3 scripts/done_helper.py \
        --vault ~/Obsidian/todo \
        --match "开用户"

    # 自定义完成日 (默认今天)
    python3 scripts/done_helper.py \
        --vault ~/Obsidian/todo \
        --file "ACTIVE/2026-06-09-开用户-P0-ACTIVE.md" \
        --completed-on 2026-06-12

返回 JSON (stdout):
    {
        "ok": true,
        "type": "ok",
        "moved_from": "ACTIVE/2026-06-09-开用户-P0-ACTIVE.md",
        "moved_to": "DONE/2026-06-12-开用户-P0-DONE.md",
        "original_due": "2026-06-09",
        "completed_on": "2026-06-12",
        "validate_exit": 0
    }

    # 找不到/歧义 情况
    {
        "ok": false,
        "type": "error",
        "message": "no ACTIVE file matches '开用户'"
    }

    {
        "ok": false,
        "type": "ambiguous",
        "matches": ["ACTIVE/2026-06-09-开用户-P0-ACTIVE.md", "ACTIVE/2026-06-10-开用户2-P0-ACTIVE.md"],
        "ask_message": "找到 2 个匹配, 请用 --file 精确指定"
    }

学 finance track V1.3.4 transaction_create.py 模式:
- 解析 frontmatter, 不假设 slug 格式
- filename 日期 = frontmatter due (validate_todo.py 强校验)
  → 标 done 时:
    1) filename 前缀从原 due 改为完成日
    2) frontmatter due 同步改为完成日 (这样 validator 不报"filename ≠ due")
    3) 原 due 移到新字段 original_due (保历史)
    4) 新增 completed_on = 完成日
    5) updated 改为完成日
    6) status 改 DONE
    7) 进度区追加 "- YYYY-MM-DD 完成"
- 原子写: temp file + os.replace
- 写完自动调 validate_todo.py
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 让脚本可独立运行, 也可被 import
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from parsers import (
    parse_simple_yaml, parse_todo_file, VALID_STATUS,
)


# ============================================================
# Frontmatter 序列化
# ============================================================

def render_frontmatter(fm: Dict[str, str]) -> str:
    """把 dict 重新序列化成 --- ... --- 块. 保持原顺序 (Python 3.7+ dict 有序)."""
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def update_frontmatter(
    content: str,
    updates: Dict[str, str],
    append: bool = True,
) -> str:
    """
    更新 frontmatter 字段, 保留其他字段和正文.

    Args:
        content: 原 .md 全文
        updates: 要更新/新增的字段 {key: value}
        append: 新字段是否追加到末尾 (默认 True), 已存在字段原地更新

    Returns:
        新全文
    """
    if not content.startswith("---\n"):
        raise ValueError("content missing leading ---")

    end_match = re.search(r"\n---\n", content[4:])
    if not end_match:
        raise ValueError("content missing closing ---")

    head_end = 4 + end_match.start()  # 第一个 \n---\n 的位置 (含 \n)
    head = content[:head_end]  # ---\n...第一行...\n
    body = content[head_end:]   # ---\n 之后

    # 解析现有 frontmatter
    fm, err = _parse_fm_block(content)
    if err:
        raise ValueError(f"parse frontmatter failed: {err}")

    # 应用更新
    new_fields = dict(updates)
    for k, v in updates.items():
        if k in fm:
            fm[k] = v  # 覆盖, 位置不变
            new_fields.pop(k)
    if append:
        for k, v in new_fields.items():
            fm[k] = v  # 追加到末尾

    new_head = render_frontmatter(fm) + "\n"
    return new_head + body


def _parse_fm_block(content: str) -> Tuple[Dict[str, str], str]:
    """从 ---\n...---\n 块解析 key: value. 简单实现, 不依赖 parsers.parse_frontmatter (那个返回 str 值)."""
    if not content.startswith("---\n"):
        return {}, "missing leading ---"
    end_match = re.search(r"\n---\n", content[4:])
    if not end_match:
        return {}, "missing closing ---"
    block = content[4:4 + end_match.start()]
    result: Dict[str, str] = {}
    for line in block.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if key:
            result[key] = value
    return result, ""


# ============================================================
# 文件名生成 (跟 validate_todo.py 的 FILENAME_PATTERN 一致)
# ============================================================

FILENAME_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2})-(.+)-(P[0-3])-(ACTIVE|DONE|BLOCKED|SNOOZED|CANCELED)\.md$"
)


def rename_for_done(orig_path: Path, completed_on: date) -> Path:
    """
    把 ACTIVE/xxx.md 重命名为 DONE/<completed_on>-<slug>-<pri>-DONE.md
    保留原 slug 和 priority, 只换日期前缀和 STATUS 段.
    """
    m = FILENAME_PATTERN.match(orig_path.name)
    if not m:
        raise ValueError(
            f"filename {orig_path.name!r} doesn't match "
            f"YYYY-MM-DD-{{slug}}-P{{n}}-{{STATUS}}.md pattern"
        )
    _, slug, pri, _ = m.groups()
    new_name = f"{completed_on.isoformat()}-{slug}-{pri}-DONE.md"
    return orig_path.parent.parent / "DONE" / new_name  # ACTIVE -> DONE 同 vault


# ============================================================
# 进度区追加 "完成" 行
# ============================================================

def append_progress_line(content: str, created_date: str, completed_on: date) -> str:
    """
    在 "## 进度" 段追加 "- YYYY-MM-DD 完成" 行.
    已存在则不重复.
    找不到 "## 进度" 段则在 frontmatter 后第一行追加.
    """
    completion_marker = f"- {completed_on.isoformat()} 完成"

    if completion_marker in content:
        return content  # 幂等

    # 找 "## 进度\n" 段
    m = re.search(r"(## 进度\n)", content)
    if m:
        # 找下一行 (可能不存在或空)
        # 简单做法: 在 "## 进度\n" 后立即插入
        insert_pos = m.end()
        return content[:insert_pos] + f"{completion_marker}\n" + content[insert_pos:]

    # 没找到 ## 进度 段, 在 frontmatter 结束 --- 后追加新段
    end_match = re.search(r"\n---\n", content[4:])
    if not end_match:
        return content
    insert_pos = 4 + end_match.end()
    block = f"\n## 进度\n- {created_date} 创建\n{completion_marker}\n"
    return content[:insert_pos] + block + content[insert_pos:]


# ============================================================
# 核心: done 一笔
# ============================================================

def mark_done(
    vault: Path,
    src_relpath: str,
    completed_on: Optional[date] = None,
) -> Dict[str, Any]:
    """
    把 ACTIVE/ 下指定文件标 done, 移到 DONE/.

    Returns:
        dict 跟 CLI 一致.
    """
    if completed_on is None:
        completed_on = date.today()

    src = (vault / src_relpath).resolve()
    if not src.exists():
        return {"ok": False, "type": "error", "message": f"file not found: {src}"}
    if src.parent.name != "ACTIVE":
        return {
            "ok": False,
            "type": "error",
            "message": f"file in {src.parent.name}/, not ACTIVE/. done_helper only handles ACTIVE -> DONE",
        }

    # 解析原 frontmatter
    todo, parse_warns = parse_todo_file(src)
    if todo is None:
        return {
            "ok": False,
            "type": "error",
            "message": f"parse failed: {parse_warns}",
        }

    if todo["status"] != "ACTIVE":
        return {
            "ok": False,
            "type": "error",
            "message": f"status={todo['status']}, not ACTIVE. already done?",
        }

    original_due = todo["due"]
    if original_due is None:
        return {
            "ok": False,
            "type": "error",
            "message": "frontmatter due is missing or invalid, can't proceed",
        }
    original_due_str = original_due.isoformat()

    # 计算新路径
    dst = rename_for_done(src, completed_on)
    if dst.exists():
        return {
            "ok": False,
            "type": "error",
            "message": f"destination already exists: {dst}",
        }

    # 读全文
    content = src.read_text(encoding="utf-8")

    # 更新 frontmatter
    created_str = todo["created"].isoformat() if todo.get("created") else completed_on.isoformat()
    fm_updates = {
        "status": "DONE",
        "updated": completed_on.isoformat(),
        "due": completed_on.isoformat(),  # 跟 filename 对齐 (validate_todo.py 强校验)
        "completed_on": completed_on.isoformat(),
        "original_due": original_due_str,
    }
    new_content = update_frontmatter(content, fm_updates, append=True)

    # 追加进度行
    new_content = append_progress_line(new_content, created_str, completed_on)

    # 原子写
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".md", dir=dst.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_content)
        os.replace(tmp, dst)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

    # 删原文件
    os.remove(src)

    # 跑 validate
    script_dir = Path(__file__).resolve().parent
    validate_script = script_dir / "validate_todo.py"
    proc = subprocess.run(
        [sys.executable, str(validate_script), str(dst)],
        capture_output=True, text=True,
    )

    return {
        "ok": True,
        "type": "ok",
        "moved_from": str(src.relative_to(vault)),
        "moved_to": str(dst.relative_to(vault)),
        "original_due": original_due_str,
        "completed_on": completed_on.isoformat(),
        "validate_exit": proc.returncode,
        "validate_output": (proc.stdout + proc.stderr) if proc.returncode != 0 else "",
    }


# ============================================================
# 模糊搜索
# ============================================================

def find_active_matches(vault: Path, keyword: str) -> List[str]:
    """
    在 ACTIVE/ 下找 title 或 filename 含 keyword 的文件.
    返回相对 vault 的路径列表.
    """
    active_dir = vault / "ACTIVE"
    if not active_dir.exists():
        return []
    matches = []
    for p in active_dir.glob("*.md"):
        if keyword in p.name:
            matches.append(str(p.relative_to(vault)))
            continue
        # 也搜一下 title
        todo, _ = parse_todo_file(p)
        if todo and keyword in todo.get("title", ""):
            matches.append(str(p.relative_to(vault)))
    return matches


# ============================================================
# CLI
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mark a todo done and move it from ACTIVE/ to DONE/"
    )
    parser.add_argument("--vault", required=True, help="path to ~/Obsidian/todo")
    parser.add_argument("--file", help="ACTIVE/ 下精确路径, e.g. 'ACTIVE/2026-06-09-开用户-P0-ACTIVE.md'")
    parser.add_argument("--match", help="在 ACTIVE/ 下模糊搜 title 或 filename 含此关键词")
    parser.add_argument("--completed-on", help="完成日 YYYY-MM-DD, 默认今天")
    parser.add_argument("--output", default="json", choices=["json", "text"])
    args = parser.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    if not vault.exists() or not vault.is_dir():
        print(json.dumps({
            "ok": False, "type": "error",
            "message": f"vault path not found or not a directory: {vault}",
        }, ensure_ascii=False))
        return 1

    completed_on = None
    if args.completed_on:
        try:
            completed_on = datetime.strptime(args.completed_on, "%Y-%m-%d").date()
        except ValueError:
            print(json.dumps({
                "ok": False, "type": "error",
                "message": f"invalid --completed-on format: {args.completed_on!r}",
            }, ensure_ascii=False))
            return 2

    # 决定要处理哪个文件
    src_relpath = None
    if args.file:
        src_relpath = args.file
    elif args.match:
        matches = find_active_matches(vault, args.match)
        if not matches:
            print(json.dumps({
                "ok": False, "type": "error",
                "message": f"no ACTIVE file matches {args.match!r}",
            }, ensure_ascii=False))
            return 1
        if len(matches) > 1:
            print(json.dumps({
                "ok": False, "type": "ambiguous",
                "matches": matches,
                "ask_message": f"找到 {len(matches)} 个匹配 {args.match!r}, 请用 --file 精确指定",
            }, ensure_ascii=False))
            return 0  # ambiguous 不算硬错
        src_relpath = matches[0]
    else:
        print(json.dumps({
            "ok": False, "type": "error",
            "message": "must specify --file or --match",
        }, ensure_ascii=False))
        return 2

    result = mark_done(vault, src_relpath, completed_on)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
