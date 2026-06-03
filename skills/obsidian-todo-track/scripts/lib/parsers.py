#!/usr/bin/env python3
"""
parsers.py - frontmatter + todo 字段解析器 (V1.0)

零依赖, 仅用 Python 3.8+ 标准库。被 validate_todo / todo_create /
daily_todo_check 三个脚本共用。

学 finance track V1.3.3 parsers.py 模式 (nested YAML + 注释剥离 + parse_config_yaml),
但简化为只支持 todo frontmatter 的扁平 key:value 形式 (V1.0 不需要嵌套)。

设计原则:
1. **不抛异常, 返回 (ok, value, error_msg) 三元组** - 调用方决定怎么处理
2. **解析失败的字段单独标, 不让一个字段错带崩整个文件** - 跟 daily_integrity_check 哲学一致
3. **frontmatter 边界检测用首块 --- ---**, 跟 finance track parsers.py 一致
   (life/ai/google-gemini-tamic 那种 "文件里嵌多块 --- ---" 的边角 V1.0 不处理,
   V1.x 后续按需加 strip_embedded_fm_blocks)
"""

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# ============================================================
# 常量
# ============================================================

VALID_STATUS = {"ACTIVE", "DONE", "BLOCKED", "SNOOZED", "CANCELED"}
VALID_PRIORITY = {"P0", "P1", "P2", "P3"}
VALID_SOURCES = {"user", "agent", "cron"}
REQUIRED_FIELDS = ("title", "status", "priority", "due")
ALL_FIELDS = (
    "type", "title", "created", "updated", "status", "priority",
    "due", "project", "tags", "source", "note"
)


# ============================================================
# Frontmatter 解析
# ============================================================

def parse_frontmatter(content: str) -> Tuple[Optional[Dict[str, str]], str]:
    """
    解析 markdown 文件的首块 ---...--- frontmatter.

    Returns:
        (None, error_msg) - 解析失败
        ({key: value}, "") - 解析成功 (value 都是 str, 调用方按需 type-cast)

    规则:
    - 首行必须是 ---
    - 第二块 --- 是结束
    - 中间是 key: value 形式
    - value 可以是:
        - 纯字符串 (含中文)
        - "[a, b, c]" YAML 列表 (V1.0 支持最简形式, 嵌套 V1.x 加)
        - '"双引号字符串"' (含特殊字符)
    - 注释行 (以 # 开头) 跳过
    - 空行跳过
    """
    if not content.startswith("---\n"):
        return None, "missing leading ---"

    # 找第二个 ---
    end_match = re.search(r"\n---\n", content[4:])
    if not end_match:
        return None, "missing closing ---"

    block = content[4:4 + end_match.start()]
    result: Dict[str, str] = {}
    for line in block.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            # 跳过无法解析的行, 不报硬错
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if key:
            result[key] = value
    return result, ""


def parse_todo_file(path: Path) -> Tuple[Optional[Dict[str, Any]], list]:
    """
    解析一个 todo .md 文件, 返回结构化字段.

    Returns:
        (None, errors) - 致命错误 (frontmatter 缺失/文件不存在)
        (todo_dict, warnings) - 解析成功, warnings 是字段级警告

    todo_dict 字段:
        path: Path
        filename: str
        status: str (upper)
        priority: str (upper)
        title: str
        due: date | None
        created: date | None
        updated: date | None
        project: str | None (raw wikilink 含 [[ ]])
        tags: list[str]
        source: str
        note: str
        raw: dict (原始 frontmatter, 调试用)
    """
    if not path.exists():
        return None, [f"file not found: {path}"]

    content = path.read_text(encoding="utf-8")
    fm, err = parse_frontmatter(content)
    if fm is None:
        return None, [f"frontmatter error: {err}"]

    warnings = []
    todo: Dict[str, Any] = {
        "path": path,
        "filename": path.name,
        "raw": fm,
    }

    # 必填字段检查
    for field in REQUIRED_FIELDS:
        if field not in fm or not fm[field].strip():
            warnings.append(f"missing required field: {field}")

    # type: 默认 "todo", 不是 todo 不解析 (避免误读 finance 文件)
    todo["type"] = fm.get("type", "todo").strip()
    if todo["type"] != "todo":
        warnings.append(f"unexpected type: {todo['type']} (expected 'todo')")

    # title
    todo["title"] = fm.get("title", "").strip()

    # status (upper)
    status = fm.get("status", "").strip().upper()
    if status and status not in VALID_STATUS:
        warnings.append(f"invalid status: {status} (must be one of {sorted(VALID_STATUS)})")
    todo["status"] = status

    # priority (upper)
    priority = fm.get("priority", "").strip().upper()
    if priority and priority not in VALID_PRIORITY:
        warnings.append(f"invalid priority: {priority} (must be one of {sorted(VALID_PRIORITY)})")
    todo["priority"] = priority

    # due (date)
    todo["due"] = _parse_date_field(fm.get("due", ""), "due", warnings)

    # created / updated (date, 可选)
    todo["created"] = _parse_date_field(fm.get("created", ""), "created", warnings)
    todo["updated"] = _parse_date_field(fm.get("updated", ""), "updated", warnings)

    # project (wikilink 原始字符串)
    project = fm.get("project", "").strip()
    todo["project"] = project if project else None

    # tags (YAML 列表)
    todo["tags"] = _parse_list_field(fm.get("tags", ""), warnings, field_name="tags")

    # source
    source = fm.get("source", "").strip().lower()
    if source and source not in VALID_SOURCES:
        warnings.append(f"invalid source: {source} (must be one of {sorted(VALID_SOURCES)})")
    todo["source"] = source if source else "user"

    # note (剩余正文第一段非空行)
    todo["note"] = _extract_note(content)

    return todo, warnings


# ============================================================
# 辅助函数
# ============================================================

def _parse_date_field(value: str, field_name: str, warnings: list) -> Optional[date]:
    """解析 YYYY-MM-DD 格式日期. 空/None/无效都返回 None, 无效时加 warning."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        warnings.append(f"invalid {field_name} date format: {value!r} (expected YYYY-MM-DD)")
        return None


def _parse_list_field(value: str, warnings: list, field_name: str = "list") -> list:
    """
    解析 YAML 风格列表: [a, b, c] 或 [a,b,c]
    空字符串返回 [].
    """
    value = (value or "").strip()
    if not value:
        return []
    if not (value.startswith("[") and value.endswith("]")):
        warnings.append(f"{field_name} not in [a, b, c] format: {value!r}")
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    items = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
    return items


def _extract_note(content: str) -> str:
    """
    从 frontmatter 之后的第一段非空正文提取 note.
    简单实现: 找 --- 之后的第一个非空行 (去除 # 开头行).
    """
    end_match = re.search(r"\n---\n", content[4:])
    if not end_match:
        return ""
    body = content[4 + end_match.end():]
    for line in body.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return stripped
    return ""


# ============================================================
# Config 解析 (default_priorities.yaml 专用)
# ============================================================

def parse_simple_yaml(path: Path) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    解析 V1.0 简化版 YAML (default_priorities.yaml 专用).

    V1.0 不依赖 pyyaml, 只支持:
    - key: value
    - key: [a, b, c]
    - 注释行 (# 开头)
    - 嵌套 key: (缩进 2 空格表示子级)

    Returns:
        (None, error_msg) - 失败
        (parsed_dict, "") - 成功
    """
    if not path.exists():
        return None, f"file not found: {path}"

    text = path.read_text(encoding="utf-8")
    root: Dict[str, Any] = {}
    stack: list = [(-1, root)]  # (indent_level, dict)

    for line_no, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # 计算缩进 (基于原始 line, 不是 stripped)
        indent = len(line) - len(line.lstrip())

        # 列表项 (- 或 * 开头): 追加到父 list
        if stripped.startswith("- ") or stripped.startswith("* "):
            item_value = stripped[2:].strip()
            # pop stack 到合适层 (列表项至少要比父缩进深)
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent = stack[-1][1]
            if not isinstance(parent, list):
                return None, f"line {line_no}: list item but parent is not list"
            parent.append(_parse_yaml_value(item_value))
            continue

        # pop stack 到合适层
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]

        if ":" not in stripped:
            return None, f"line {line_no}: no ':' in {stripped!r}"

        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()

        if not value:
            # 嵌套 dict 或 list? 启发式: 看 stack[-2] (祖父) 的最后一个 key 的类型
            # V1.0 简化: 默认 dict. 遇到列表项时报 "parent is not list" 错误
            # 改进: 总是初始化为 dict, 然后 patch 让它知道下面是 list
            # 更稳的方案: 在写时检查, 但 V1.0 先这样, 报错时改用显式 []
            new_dict: Dict[str, Any] = {}
            parent[key] = new_dict
            stack.append((indent, new_dict))
        elif value == "[]":
            # 空列表
            parent[key] = []
        else:
            # 解析 value
            parent[key] = _parse_yaml_value(value)

    # 后处理: 把 "key: <dict> 但里面有 key 是列表项" 转成 list 父
    # V1.0 简化: 不做这个转换, config 写时如果下面有列表项就用显式 [] 占位
    # 但 note_keywords 这种嵌套 dict-of-list 写法很常见
    # 所以这里加一个回扫: 如果某个 dict 的 value 是 "marker dict with single list-like key"
    # 太复杂, 直接遍历 config 转
    return _convert_dict_to_list_where_appropriate(root), ""


def _convert_dict_to_list_where_appropriate(node: Any) -> Any:
    """
    后处理: 把 "key: {子项全是 list_append}" 转成 "key: [子项]".

    启发式: 如果 dict 的所有 value 都是 dict, 且这些 dict 都只有 1 个 key
    且这个 key 是合法标识符 (P0/P1/...), 那这层是"key 是 list 元素名"的 pattern,
    转成 list.

    V1.0 简化: 不做. 让 config 用显式 - 列表项必须用 [P0, P1, P3] 内联格式.
    实际 note_keywords 不需要嵌套, 改成:
      note_keywords:
        P0: [紧急, 立刻, ...]
    """
    return node


def _parse_yaml_value(value: str) -> Any:
    """解析单值: 字符串 / [a, b, c] / {a: b, c: d} / 数字 / true/false."""
    value = value.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
    if value.startswith("{") and value.endswith("}"):
        # 内联 dict: {a: b, c: d}
        inner = value[1:-1].strip()
        if not inner:
            return {}
        result: Dict[str, Any] = {}
        # 简单 split: 不支持 value 含逗号 (V1.0 够用)
        for pair in inner.split(","):
            if ":" not in pair:
                continue
            k, _, v = pair.partition(":")
            k = k.strip().strip("'\"")
            v = v.strip()
            # value 可能是数字/字符串, 简单处理
            try:
                if "." in v:
                    result[k] = float(v)
                else:
                    result[k] = int(v)
            except ValueError:
                result[k] = v.strip("'\"")
        return result
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    # 数字
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        pass
    # 去掉外层引号
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


# ============================================================
# Module self-test
# ============================================================

if __name__ == "__main__":
    import sys
    print("parsers.py module self-test")
    print(f"  VALID_STATUS = {sorted(VALID_STATUS)}")
    print(f"  VALID_PRIORITY = {sorted(VALID_PRIORITY)}")
    print(f"  REQUIRED_FIELDS = {REQUIRED_FIELDS}")
    # 简单 sanity check
    sample = "---\ntype: todo\ntitle: 测试\nstatus: ACTIVE\npriority: P1\ndue: 2026-06-15\ntags: [test, sample]\n---\n\n# 测试 todo\n\n这是 note。"
    fm, err = parse_frontmatter(sample)
    assert err == "", f"unexpected error: {err}"
    assert fm["title"] == "测试"
    assert fm["priority"] == "P1"
    print("  ✓ parse_frontmatter OK")

    todo, warns = parse_todo_file(Path("/tmp/nonexistent.md"))
    assert todo is None and warns
    print("  ✓ parse_todo_file missing-file returns error")

    # 模拟解析
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(sample)
        tmp_path = Path(f.name)
    try:
        todo, warns = parse_todo_file(tmp_path)
        assert todo is not None
        assert todo["title"] == "测试"
        assert todo["priority"] == "P1"
        assert todo["due"] == date(2026, 6, 15)
        assert todo["tags"] == ["test", "sample"]
        assert todo["note"] == "这是 note。"
        print("  ✓ parse_todo_file full parse OK")
    finally:
        os.unlink(tmp_path)

    print("All checks passed.")
