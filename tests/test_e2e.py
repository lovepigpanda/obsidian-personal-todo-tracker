#!/usr/bin/env python3
"""
test_e2e.py - 端到端测试 (V1.0)

学 finance track V1.3.4 verify_4way_sync.sh 模式:
- 隔离 vault (tempfile.mkdtemp) 不污染真实 ~/Obsidian/todo
- 跑完整 pipeline: install → create → validate → daily_check
- 断言文件存在/exit code/JSON 字段全对

跑:
    cd ~/Project/obsidian-personal-todo-tracker
    python3 tests/test_e2e.py
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"


def run(cmd, **kwargs):
    """跑 subprocess, 失败时 print 完整输出."""
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0 and kwargs.get("check", False):
        print(f"  ❌ exit {result.returncode}")
        print(f"  stdout: {result.stdout}")
        print(f"  stderr: {result.stderr}")
    return result


def setup_vault():
    """建隔离 vault, 装 config."""
    vault = Path(tempfile.mkdtemp(prefix="todo_e2e_"))
    for d in ["ACTIVE", "DONE", "BLOCKED", "SNOOZED", "CANCELED"]:
        (vault / d).mkdir()
    # cp config (代替 install.sh, 简化)
    import shutil
    shutil.copy(REPO_ROOT / "config" / "default_priorities.yaml", vault / "default_priorities.yaml")
    print(f"✓ vault: {vault}")
    return vault


def test_create_with_user_priority(vault):
    """Case 1: 用户显式 P1 + due 6 天后 → P1 (user 优先)"""
    print("\n[Test 1] create with user priority")
    due = (date.today() + timedelta(days=6)).isoformat()
    result = run([
        sys.executable, str(SCRIPTS / "todo_create.py"),
        "--vault", str(vault),
        "--title", "续签劳动合同",
        "--due", due,
        "--priority", "P1",
        "--note", "合同 6/30 到期",
    ], check=True)
    data = json.loads(result.stdout)
    assert data["ok"] is True, f"expected ok, got {data}"
    assert data["type"] == "ok"
    assert data["priority"] == "P1", f"expected P1, got {data['priority']}"
    assert data["source"] == "user", f"expected user, got {data['source']}"
    assert data["validate_exit"] == 0, f"expected validate 0, got {data['validate_exit']}"
    print(f"  ✓ file: {data['file_path']}, priority={data['priority']} (source={data['source']})")

    # 验证文件存在
    expected_file = vault / data["file_path"]
    assert expected_file.exists(), f"file not created: {expected_file}"
    print(f"  ✓ file exists on disk")
    return expected_file


def test_create_note_keyword_P0(vault):
    """Case 2: note 关键词"紧急" → P0 (note_keyword 优先于 due_distance)"""
    print("\n[Test 2] note keyword '紧急' → P0")
    due = (date.today() + timedelta(days=10)).isoformat()  # 远期, 但 note 优先
    result = run([
        sys.executable, str(SCRIPTS / "todo_create.py"),
        "--vault", str(vault),
        "--title", "服务器宕机",
        "--due", due,
        "--note", "紧急处理",
    ], check=True)
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["priority"] == "P0", f"expected P0, got {data['priority']}"
    assert data["source"] == "note_keyword", f"expected note_keyword, got {data['source']}"
    print(f"  ✓ priority={data['priority']} (source={data['source']})")


def test_create_due_distance(vault):
    """Case 3: 无 priority 无 note 无 project, due 决定 priority"""
    print("\n[Test 3] due 0 天 → P0 (due_distance)")
    due = date.today().isoformat()
    result = run([
        sys.executable, str(SCRIPTS / "todo_create.py"),
        "--vault", str(vault),
        "--title", "今天还信用卡",
        "--due", due,
    ], check=True)
    data = json.loads(result.stdout)
    assert data["priority"] == "P0"
    assert data["source"] == "due_distance"
    print(f"  ✓ priority={data['priority']} (source={data['source']})")


def test_ask_on_2nd(vault):
    """Case 4: ask_on_2nd 触发 (同关键词 + 不同 priority)"""
    print("\n[Test 4] ask_on_2nd learning")
    # 第一次: 关键词 "沙县" + due 0 天 → P0 (静默记录)
    result1 = run([
        sys.executable, str(SCRIPTS / "todo_create.py"),
        "--vault", str(vault),
        "--title", "沙县午餐",
        "--due", date.today().isoformat(),
        "--note", "沙县",
    ], check=True)
    data1 = json.loads(result1.stdout)
    assert data1["ok"] is True
    assert data1["priority"] == "P0"
    assert data1["ask_message"] is None
    print(f"  ✓ 1st: priority={data1['priority']}, ask=None (silent)")

    # 第二次: 同关键词 + due 30 天 → P3 (冲突 → ask)
    result2 = run([
        sys.executable, str(SCRIPTS / "todo_create.py"),
        "--vault", str(vault),
        "--title", "沙县夜宵",
        "--due", (date.today() + timedelta(days=30)).isoformat(),
        "--note", "沙县",
    ], check=True)
    data2 = json.loads(result2.stdout)
    assert data2["ok"] is False
    assert data2["type"] == "ask", f"expected ask, got {data2['type']}"
    assert "沙县" in data2["ask_message"]
    assert data2["candidate_priority"] == "P3"
    print(f"  ✓ 2nd: type=ask, message='{data2['ask_message'][:50]}...'")


def test_validate_active_dir(vault):
    """Case 5: validate 整 ACTIVE/ 目录, 应该 0 errors"""
    print("\n[Test 5] validate ACTIVE/ directory")
    result = run([
        sys.executable, str(SCRIPTS / "validate_todo.py"),
        str(vault / "ACTIVE"), "--recursive",
    ])
    # 之前建的所有 todo 都该通过
    # parse_warnings 允许 (0 errors)
    assert result.returncode == 0, f"expected 0, got {result.returncode}\n{result.stdout}"
    print(f"  ✓ all ACTIVE todos pass validation")


def test_daily_check_writes_alerts(vault):
    """Case 6: daily_todo_check 写 alerts.md, 含所有建过的 todo"""
    print("\n[Test 6] daily_todo_check writes alerts.md")
    result = run([
        sys.executable, str(SCRIPTS / "daily_todo_check.py"),
        "--vault", str(vault),
    ], check=True)
    print(f"  stdout: {result.stdout.strip()}")

    alerts = vault / "alerts.md"
    assert alerts.exists(), "alerts.md not created"
    content = alerts.read_text(encoding="utf-8")
    # 至少 1 个 todo 应该在 alerts 里
    assert "续签" in content or "服务器" in content, f"alerts.md missing todos:\n{content[:500]}"
    print(f"  ✓ alerts.md exists, contains expected todos")


def test_validate_misplaced_file(vault):
    """Case 7: 手写一个 status=DONE 但在 ACTIVE/ 的文件, 验证能检测"""
    print("\n[Test 7] validate detects misplaced file")
    bad_file = vault / "ACTIVE" / "2026-06-10-bad-P1-DONE.md"
    bad_file.write_text("""---
type: todo
title: 错位
status: DONE
priority: P1
due: 2026-06-10
---
""", encoding="utf-8")
    result = run([
        sys.executable, str(SCRIPTS / "validate_todo.py"),
        str(bad_file),
    ])
    assert result.returncode == 1, f"expected 1, got {result.returncode}"
    assert "should be in DONE" in result.stdout
    print(f"  ✓ misplaced file detected (exit 1)")

    # 清理
    bad_file.unlink()


def main():
    print("=" * 60)
    print("  obsidian-personal-todo-tracker V1.0 端到端测试")
    print("=" * 60)

    vault = setup_vault()
    try:
        test_create_with_user_priority(vault)
        test_create_note_keyword_P0(vault)
        test_create_due_distance(vault)
        test_ask_on_2nd(vault)
        test_validate_active_dir(vault)
        test_daily_check_writes_alerts(vault)
        test_validate_misplaced_file(vault)
    finally:
        # 清理 learning.json (避免污染真实环境)
        learning = Path.home() / ".obsidian-todo" / "learning.json"
        if learning.exists():
            learning.unlink()
        # 清理隔离 vault
        import shutil
        shutil.rmtree(vault, ignore_errors=True)
        print(f"\n✓ cleaned up: {vault}")

    print("\n" + "=" * 60)
    print("  ✅ 所有 7 个端到端测试通过")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
