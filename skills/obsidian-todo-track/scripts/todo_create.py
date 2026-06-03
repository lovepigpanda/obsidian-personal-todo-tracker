#!/usr/bin/env python3
"""
todo_create.py - 创建 todo 的 Agent 入口 (V1.0)

用法:
    python3 scripts/todo_create.py \
        --vault ~/Obsidian/todo \
        --type create \
        --title "续签劳动合同" \
        --due 2026-06-15 \
        --note "合同 6/30 到期"

    # 完整参数
    python3 scripts/todo_create.py \
        --vault ~/Obsidian/todo \
        --type create \
        --title "X" \
        --due 2026-06-15 \
        --priority P1 \
        --project "[[taibs-hr-portal-V1.0-ACTIVE]]" \
        --tags "[todo, work, hr]" \
        --note "..."

返回 JSON (stdout):
    {
        "ok": true,
        "type": "ok",
        "file_path": "ACTIVE/2026-06-15-renew-contract-P1-ACTIVE.md",
        "priority": "P1",
        "source": "user" | "note_keyword" | "due_distance" | "project_prefix" | "fallback",
        "ask_message": null,
        "validate_exit": 0
    }

    # ask 情况 (ask_on_2nd 触发)
    {
        "ok": false,
        "type": "ask",
        "ask_message": "你上次给 keyword '午餐' 用了 Alipay, 这次用 CMB Credit. 改默认吗?",
        "ask_options": ["改默认 (以后用 CMB Credit)", "不改 (这次例外)"]
    }

    # error 情况
    {
        "ok": false,
        "type": "error",
        "message": "vault path not found: ..."
    }

退出码:
    0 - ok 或 ask (ask 不算错误, Agent 走 clarify 流程)
    1 - error (硬错, Agent 中止)
    2 - 参数错误

学 finance track V1.3.3 transaction_create.py 模式:
- 5 层优先级 (user > note_keyword > due_distance > project_prefix > fallback)
- ask_on_2nd 学习机制 (第一次静默记录, 第二次冲突问用户)
- type='ask'/'error'/'ok' 三种返回
- 写完文件后自动调 validate_todo.py
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
    VALID_PRIORITY, VALID_STATUS, parse_simple_yaml, parse_todo_file,
)

# 学习记录路径
LEARNING_PATH = Path.home() / ".obsidian-todo" / "learning.json"


# ============================================================
# 5 层优先级解析
# ============================================================

def resolve_priority(
    user_priority: Optional[str],
    note: str,
    due: Optional[date],
    project: Optional[str],
    config: Dict[str, Any],
) -> Tuple[str, str]:
    """
    按 5 层规则解析 priority.

    Returns:
        (priority, source) - source 是 "user" / "note_keyword" / "due_distance" /
                            "project_prefix" / "fallback"
    """
    # 第 1 层: user 显式声明
    if user_priority:
        up = user_priority.strip().upper()
        if up in VALID_PRIORITY:
            return up, "user"
        # 显式但非法, 走 fallback 但记录 warning
        return _fallback(config), "fallback"

    # 第 2 层: note 关键词
    if note:
        note_lower = note.lower()
        for prio in ("P0", "P1", "P3"):  # P2 不在 note 关键词里 (太中性)
            keywords = config.get("note_keywords", {}).get(prio, [])
            for kw in keywords:
                if kw.lower() in note_lower:
                    return prio, "note_keyword"

    # 第 3 层: due 距今天数
    # V1.0 config 是 due_distance_P0/P1/P2/P3 4 个独立 key
    if due:
        days = (due - date.today()).days
        for prio_suffix in ("P0", "P1", "P2", "P3"):
            rule = config.get(f"due_distance_{prio_suffix}")
            if not rule:
                continue
            from_d = rule.get("from_days", 0)
            to_d = rule.get("to_days", 9999)
            if from_d <= days <= to_d:
                return rule.get("priority", "P2"), "due_distance"

    # 第 4 层: project 前缀
    if project:
        # project 形如 "[[taibs-hr-portal-V1.0-ACTIVE]]"
        match = re.search(r"\[\[([^\]]+)\]\]", project)
        if match:
            proj_name = match.group(1)
            # V1.0 config: 两个 list, 索引对齐
            prefixes = config.get("project_prefix_rules", [])
            priorities = config.get("project_prefix_priorities", [])
            # 找最长前缀匹配
            best_match = None
            best_len = -1
            for i, prefix in enumerate(prefixes):
                if proj_name.startswith(prefix) and len(prefix) > best_len:
                    best_match = i
                    best_len = len(prefix)
            if best_match is not None and best_match < len(priorities):
                return priorities[best_match], "project_prefix"

    # 第 5 层: fallback
    return _fallback(config), "fallback"


def _fallback(config: Dict[str, Any]) -> str:
    fb = config.get("fallback", "P2")
    return fb if fb in VALID_PRIORITY else "P2"


# ============================================================
# ask_on_2nd 学习机制
# ============================================================

def _load_learning() -> Dict[str, Any]:
    if not LEARNING_PATH.exists():
        return {}
    try:
        return json.loads(LEARNING_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_learning(data: Dict[str, Any]) -> None:
    LEARNING_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEARNING_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _learning_key(note: str) -> Optional[str]:
    """
    从 note 提取一个稳定的"关键词 key"用于学习.
    V1.0 简化: 取第一个名词/动词 (按空格或中文标点切).
    V1.x 后续可用 jieba / 关键词提取.
    """
    note = (note or "").strip()
    if not note:
        return None
    # 中文标点切
    parts = re.split(r"[\s,，。；;;、\.\?!]", note)
    parts = [p.strip() for p in parts if p.strip()]
    return parts[0] if parts else None


def check_ask_on_2nd(
    note: str,
    resolved_priority: str,
    source: str,
) -> Optional[str]:
    """
    检查是否触发 ask_on_2nd.

    Returns:
        None - 不触发 (第一次用默认 / 一致 / 用户显式)
        str - ask_message (第二次冲突)
    """
    if source == "user":
        return None  # 用户显式说了, 不学

    key = _learning_key(note)
    if not key:
        return None

    learning = _load_learning()
    key_history = learning.get(key, [])
    if not key_history:
        # 第一次用默认 → 静默记录
        learning[key] = [{"priority": resolved_priority, "source": source, "at": _now_iso()}]
        _save_learning(learning)
        return None

    # 检查上一次是不是同 priority
    last = key_history[-1]
    if last["priority"] == resolved_priority:
        return None  # 一致, 不触发

    # 冲突! 触发 ask
    return (
        f"你上次给关键词 '{key}' 用了 {last['priority']} ({last['source']}), "
        f"这次默认是 {resolved_priority} ({source}). "
        f"要改默认吗?"
    )


def record_user_decision(
    note: str,
    final_priority: str,
    source: str,
) -> None:
    """用户确认后, 记录到 learning.json."""
    key = _learning_key(note)
    if not key:
        return
    learning = _load_learning()
    if key not in learning:
        learning[key] = []
    learning[key].append({"priority": final_priority, "source": source, "at": _now_iso()})
    _save_learning(learning)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ============================================================
# 文件名生成
# ============================================================

def make_slug(title: str) -> str:
    """
    从 title 生成 slug.

    规则:
    - 转小写
    - 空格 → -
    - 中文保留 (不强行转拼音, V1.0 简单实现)
    - 去除标点 (除了 -)
    - 最长 60 字符
    """
    s = title.strip().lower()
    s = re.sub(r"\s+", "-", s)
    # 保留中文/英文/数字/-, 去除其他标点
    s = re.sub(r"[^\w\u4e00-\u9fff\-]+", "", s, flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    if len(s) > 60:
        s = s[:60].rstrip("-")
    return s or "todo"


def make_filename(due: date, slug: str, priority: str, status: str) -> str:
    return f"{due.isoformat()}-{slug}-{priority}-{status}.md"


# ============================================================
# 文件内容生成
# ============================================================

def render_todo_md(
    title: str,
    status: str,
    priority: str,
    due: date,
    project: Optional[str],
    tags: List[str],
    source: str,
    note: str,
) -> str:
    """渲染 todo .md 文件内容 (含 frontmatter + 简单正文)."""
    now_iso = _now_iso()
    project_line = f'project: "{project}"' if project else "project: "

    frontmatter = f"""---
type: todo
title: {title}
created: {now_iso[:10]}
updated: {now_iso[:10]}
status: {status}
priority: {priority}
due: {due.isoformat()}
{project_line}
tags: [{', '.join(tags)}]
source: {source}
note: {note}
---"""

    body = f"""

# {title}

## 为什么
{note or '(无)'}

## 验收
- [ ] 

## 进度
- {now_iso[:10]} 创建
"""
    return frontmatter + body


# ============================================================
# 写文件 + 校验
# ============================================================

def write_and_validate(
    vault: Path,
    status: str,
    filename: str,
    content: str,
) -> Tuple[Path, int, str]:
    """
    原子写文件 + 调 validate_todo.py.

    Returns:
        (file_path, validate_exit, validate_output)
    """
    target_dir = vault / status
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename

    # 原子写: 先写临时文件, 再 os.replace
    fd, tmp = tempfile.mkstemp(suffix=".md", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, target_path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

    # 调 validate_todo.py
    script_dir = Path(__file__).resolve().parent
    validate_script = script_dir / "validate_todo.py"
    proc = subprocess.run(
        [sys.executable, str(validate_script), str(target_path)],
        capture_output=True,
        text=True,
    )
    return target_path, proc.returncode, proc.stdout + proc.stderr


# ============================================================
# 主流程
# ============================================================

def create_todo(
    vault: Path,
    title: str,
    due: date,
    note: str = "",
    priority: Optional[str] = None,
    project: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """create 类型的核心逻辑. 返回 dict 跟 CLI 一致."""
    if tags is None:
        tags = ["todo"]

    # 1. 加载 config
    config_path = vault / "default_priorities.yaml"
    if not config_path.exists():
        # vault 没 copy, 用仓库端
        repo_root = Path(__file__).resolve().parent.parent
        config_path = repo_root / "config" / "default_priorities.yaml"
    if not config_path.exists():
        return {
            "ok": False,
            "type": "error",
            "message": f"default_priorities.yaml not found (vault or repo)",
        }

    config, err = parse_simple_yaml(config_path)
    if config is None:
        return {
            "ok": False,
            "type": "error",
            "message": f"failed to parse {config_path}: {err}",
        }

    # 2. 解析 priority
    resolved_pri, source = resolve_priority(priority, note, due, project, config)

    # 3. ask_on_2nd 检查
    ask_message = check_ask_on_2nd(note, resolved_pri, source)
    if ask_message:
        return {
            "ok": False,
            "type": "ask",
            "ask_message": ask_message,
            "ask_options": ["改默认 (以后都用这个)", "不改 (这次例外)"],
            "candidate_priority": resolved_pri,
            "candidate_source": source,
        }

    # 4. 写文件
    status = "ACTIVE"  # create 永远是 ACTIVE
    slug = make_slug(title)
    filename = make_filename(due, slug, resolved_pri, status)
    content = render_todo_md(title, status, resolved_pri, due, project, tags, "user", note)

    target_path, validate_exit, validate_output = write_and_validate(vault, status, filename, content)

    return {
        "ok": True,
        "type": "ok",
        "file_path": str(target_path.relative_to(vault)),
        "priority": resolved_pri,
        "source": source,
        "ask_message": None,
        "validate_exit": validate_exit,
        "validate_output": validate_output if validate_exit != 0 else "",
    }


# ============================================================
# CLI
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a todo .md file in the Obsidian todo vault"
    )
    parser.add_argument("--vault", required=True, help="path to ~/Obsidian/todo")
    parser.add_argument(
        "--type", default="create", choices=["create"],
        help="V1.0 只支持 create",
    )
    parser.add_argument("--title", required=True, help="todo 标题")
    parser.add_argument("--due", required=True, help="due 日期 YYYY-MM-DD")
    parser.add_argument("--priority", help="显式 priority (P0/P1/P2/P3)")
    parser.add_argument("--project", help='wikilink, 形如 "[[taibs-hr-portal-V1.0-ACTIVE]]"')
    parser.add_argument("--tags", help='YAML 列表, 形如 "[todo, work, hr]"')
    parser.add_argument("--note", default="", help="备注/原始描述")
    parser.add_argument(
        "--no-validate", action="store_true",
        help="V1.0 默认必跑 validate, 加这个 flag 才不跑 (一般不用)",
    )
    parser.add_argument(
        "--output", default="json", choices=["json", "text"],
        help="V1.0.3 起可选, 默认 json (跟之前兼容); text 给人读, json 给 Agent pipe",
    )
    args = parser.parse_args()

    # 校验 vault
    vault = Path(args.vault).expanduser().resolve()
    if not vault.exists() or not vault.is_dir():
        print(json.dumps({
            "ok": False,
            "type": "error",
            "message": f"vault path not found or not a directory: {vault}",
        }, ensure_ascii=False))
        return 1

    # 解析 due
    try:
        due = datetime.strptime(args.due, "%Y-%m-%d").date()
    except ValueError:
        print(json.dumps({
            "ok": False,
            "type": "error",
            "message": f"invalid --due format: {args.due!r} (expected YYYY-MM-DD)",
        }, ensure_ascii=False))
        return 2

    # 解析 tags
    tags: Optional[List[str]] = None
    if args.tags:
        tags_str = args.tags.strip()
        if tags_str.startswith("[") and tags_str.endswith("]"):
            inner = tags_str[1:-1].strip()
            tags = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()] if inner else []

    # 主流程
    result = create_todo(
        vault=vault,
        title=args.title,
        due=due,
        note=args.note,
        priority=args.priority,
        project=args.project,
        tags=tags,
    )

    # 输出
    if args.output == "text":
        # 人类可读: 关键字段一行总结
        if result.get("type") == "ok":
            print(
                f"✅ 创建: {result.get('file_path', '?')}\n"
                f"   priority: {result.get('priority', '?')} (via {result.get('source', '?')})\n"
                f"   validate: exit {result.get('validate_exit', '?')}"
            )
        elif result.get("type") == "ask":
            print(f"❓ {result.get('ask_message', '?')}")
            for opt in result.get("ask_options", []):
                print(f"   - {opt}")
        else:  # error
            print(f"❌ 错误: {result.get('message', '?')}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    # 退出码
    if result.get("type") == "error":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
