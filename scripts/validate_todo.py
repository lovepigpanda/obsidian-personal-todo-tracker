#!/usr/bin/env python3
"""
validate_todo.py - 单个 todo .md 文件校验 (V1.0)

用法:
    python3 scripts/validate_todo.py <todo_file.md>
    python3 scripts/validate_todo.py <todo_file.md> --json     # JSON 输出
    python3 scripts/validate_todo.py <dir> --recursive        # 递归校验目录下所有 .md

退出码:
    0 - 校验通过
    1 - 校验失败 (有 ERROR 级问题, 文件保留, Agent 走软告警)
    2 - 参数错误 / 文件找不到

校验内容:
    1. 必填字段: title / status / priority / due
    2. status 是 5 选 1: ACTIVE / DONE / BLOCKED / SNOOZED / CANCELED
    3. priority 是 P0-P3 之一
    4. due 是合法 YYYY-MM-DD
    5. 文件位置跟 status 一致 (ACTIVE/ 下文件 status 必须是 ACTIVE)
    6. 文件名格式: YYYY-MM-DD-{slug}-P{n}-{STATUS}.md
    7. created / updated 是合法 YYYY-MM-DD (警告级, 不阻塞)
    8. tags 是 [a, b, c] 格式 (警告级)

学 finance track V1.3.4 validate_transaction.py 模式:
- 软告警不阻塞, 文件保留, Agent 询问 fix/ignore/delete
- 退出码语义清晰: 0=pass, 1=fixable, 2=broken
- 支持 --json 给 Agent 用, 纯文本给用户看
"""

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 让脚本可独立运行, 也可被 import
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from parsers import (
    REQUIRED_FIELDS, VALID_PRIORITY, VALID_SOURCES, VALID_STATUS,
    parse_todo_file,
)


# ============================================================
# 校验规则
# ============================================================

EXPECTED_DIR = {
    "ACTIVE": "ACTIVE",
    "DONE": "DONE",
    "BLOCKED": "BLOCKED",
    "SNOOZED": "SNOOZED",
    "CANCELED": "CANCELED",
}

FILENAME_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2})-(.+)-(P[0-3])-(ACTIVE|DONE|BLOCKED|SNOOZED|CANCELED)\.md$"
)


def validate_todo(todo: Dict[str, Any], warnings: Optional[List[str]] = None) -> Tuple[List[str], List[str]]:
    """
    校验一个 todo 字典 (parse_todo_file 的输出).

    Args:
        todo: parse_todo_file 的输出
        warnings: 外部传入的 parsers 警告 (用于合并和抑制), 默认新建空 list

    Returns:
        (errors, warnings) - 错误 (exit 1) 和 警告 (exit 0 但提示)
    """
    errors: List[str] = []
    if warnings is None:
        warnings = []

    # 1. 必填字段 (parsers 已经把缺失的报为 warning, 升级为 error)
    for field in REQUIRED_FIELDS:
        value = todo.get(field)
        if not value or (isinstance(value, str) and not value.strip()):
            errors.append(f"missing required field: {field}")
            # 抑制 parsers 的同字段 warning, 避免重复
            warnings[:] = [w for w in warnings if f"missing required field: {field}" not in w]

    # 2. status 合法
    status = todo.get("status", "")
    if status and status not in VALID_STATUS:
        errors.append(f"invalid status: {status!r} (must be one of {sorted(VALID_STATUS)})")

    # 3. priority 合法
    priority = todo.get("priority", "")
    if priority and priority not in VALID_PRIORITY:
        errors.append(f"invalid priority: {priority!r} (must be one of {sorted(VALID_PRIORITY)})")

    # 4. due 合法 (parsers 已经把无效的转 None + warning, 这里二次确认)
    if not todo.get("due"):
        # parsers 已经报过 warning, 但 due 必填, 升级为 error
        if "due" in todo["raw"] and todo["raw"]["due"].strip():
            errors.append(f"due field exists but unparseable: {todo['raw']['due']!r}")
        # 如果 due 字段本身缺失, 上面 #1 已经报 missing required field, 这里不重复

    # 5. 文件位置跟 status 一致
    if status in EXPECTED_DIR:
        parent_dir = todo["path"].parent.name
        expected_dir = EXPECTED_DIR[status]
        if parent_dir != expected_dir:
            errors.append(
                f"file in {parent_dir}/ but status={status} "
                f"(should be in {expected_dir}/)"
            )

    # 6. 文件名格式
    m = FILENAME_PATTERN.match(todo["filename"])
    if m:
        file_due_str, slug, file_pri, file_status = m.groups()
        if status and file_status != status:
            errors.append(
                f"filename STATUS={file_status} but frontmatter status={status} "
                f"(mismatch)"
            )
        if priority and file_pri != priority:
            errors.append(
                f"filename priority={file_pri} but frontmatter priority={priority} "
                f"(mismatch)"
            )
        if todo.get("due") and file_due_str != todo["due"].isoformat():
            errors.append(
                f"filename date={file_due_str} but frontmatter due={todo['due'].isoformat()} "
                f"(mismatch)"
            )
    else:
        warnings.append(
            f"filename {todo['filename']!r} doesn't match "
            f"YYYY-MM-DD-{{slug}}-P{{n}}-{{STATUS}}.md pattern"
        )

    # 7. created / updated 合法 (parsers 已经 warning 过, 这里只检查业务)
    if todo.get("created") and todo.get("updated"):
        if todo["updated"] < todo["created"]:
            warnings.append(
                f"updated {todo['updated']} is before created {todo['created']}"
            )

    # 8. source 合法 (如果给了)
    source = todo.get("source", "")
    if source and source not in VALID_SOURCES:
        warnings.append(f"invalid source: {source!r} (must be one of {sorted(VALID_SOURCES)})")

    return errors, warnings


# ============================================================
# CLI
# ============================================================

def validate_file(path: Path) -> Dict[str, Any]:
    """校验单个文件, 返回结果字典."""
    todo, parse_warnings = parse_todo_file(path)
    if todo is None:
        return {
            "ok": False,
            "file": str(path),
            "errors": parse_warnings,  # 致命解析错误
            "warnings": [],
        }

    # 关键: parse_warnings 先合并, 让 validate_todo 能抑制 parsers 的重复 warning
    base_warnings = list(parse_warnings)
    errors, warnings = validate_todo(todo, base_warnings)
    warnings = base_warnings + warnings

    return {
        "ok": not errors,
        "file": str(path),
        "title": todo.get("title"),
        "status": todo.get("status"),
        "priority": todo.get("priority"),
        "due": todo["due"].isoformat() if todo.get("due") else None,
        "errors": errors,
        "warnings": warnings,
    }


def validate_dir(dir_path: Path) -> List[Dict[str, Any]]:
    """递归校验目录下所有 .md 文件."""
    results = []
    for md_file in sorted(dir_path.rglob("*.md")):
        # 跳过 alerts.md 和 todo-config.md (它们不是 todo)
        if md_file.name in {"alerts.md", "todo-config.md"}:
            continue
        results.append(validate_file(md_file))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a todo .md file or directory of todo files"
    )
    parser.add_argument("path", help="todo .md file or directory")
    parser.add_argument("--json", action="store_true", help="output JSON")
    parser.add_argument(
        "--recursive", action="store_true", help="recursive when path is dir"
    )
    args = parser.parse_args()

    path = Path(args.path).expanduser().resolve()
    if not path.exists():
        print(f"ERROR: path not found: {path}", file=sys.stderr)
        return 2

    if path.is_dir():
        if not args.recursive:
            print(f"ERROR: {path} is a directory, use --recursive", file=sys.stderr)
            return 2
        results = validate_dir(path)
    else:
        results = [validate_file(path)]

    # 输出
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        total_errors = sum(len(r["errors"]) for r in results)
        total_warnings = sum(len(r["warnings"]) for r in results)
        for r in results:
            if r["ok"] and not r["warnings"]:
                print(f"✅ {r['file']}")
            elif r["ok"]:
                print(f"⚠️  {r['file']}  ({len(r['warnings'])} warnings)")
                for w in r["warnings"]:
                    print(f"     {w}")
            else:
                print(f"❌ {r['file']}")
                for e in r["errors"]:
                    print(f"     ❌ {e}")
                for w in r["warnings"]:
                    print(f"     ⚠️  {w}")
        print()
        print(f"Summary: {len(results)} files, {total_errors} errors, {total_warnings} warnings")

    # 退出码
    total_errors = sum(len(r["errors"]) for r in results)
    if total_errors > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
