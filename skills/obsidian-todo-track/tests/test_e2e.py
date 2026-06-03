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
from datetime import date, datetime, timedelta
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


def test_weekly_summary(vault):
    """Case 8: weekly_summary 生成统计 (V1.0.2)"""
    print("\n[Test 8] weekly_summary writes alert section")
    # 多加几个 todo 让统计有内容
    (vault / "DONE").mkdir(exist_ok=True)
    cat_template = """---
type: todo
title: {title}
created: 2026-06-01
status: {status}
priority: {priority}
due: {due}
---
"""
    for i, (title, status, prio, due) in enumerate([
        ("完成的 P1", "DONE", "P1", "2026-06-01"),
        ("完成的 P2", "DONE", "P2", "2026-06-02"),
    ]):
        (vault / status / f"2026-06-0{i+1}-done-{prio}-{status}.md").write_text(
            cat_template.format(title=title, status=status, priority=prio, due=due),
            encoding="utf-8",
        )

    result = run([
        sys.executable, str(SCRIPTS / "weekly_summary.py"),
        "--vault", str(vault),
    ], check=True)
    print(f"  stdout: {result.stdout.strip()}")
    # alerts.md 末尾应该有 weekly 段
    alerts = vault / "alerts.md"
    assert alerts.exists()
    content = alerts.read_text(encoding="utf-8")
    assert "## 📊 本周复盘" in content, f"weekly section missing in alerts.md:\n{content[-500:]}"
    assert "新建:" in content and "完成:" in content
    print(f"  ✓ weekly_summary section appended to alerts.md")


def test_monthly_summary_skip(vault):
    """Case 9: monthly_summary 非月末时静默 skip (V1.0.2)"""
    print("\n[Test 9] monthly_summary skips non-end-of-month")
    result = run([
        sys.executable, str(SCRIPTS / "monthly_summary.py"),
        "--vault", str(vault),
    ], check=True)
    assert "⏭️  跳过" in result.stdout, f"expected skip message, got: {result.stdout}"
    print(f"  ✓ monthly skipped: {result.stdout.strip()[:80]}...")

    # --month 显式指定应该跑
    result2 = run([
        sys.executable, str(SCRIPTS / "monthly_summary.py"),
        "--vault", str(vault),
        "--month", "2026-05",
    ], check=True)
    assert "📅" in result2.stdout
    print(f"  ✓ monthly --month 2026-05 runs: {result2.stdout.strip()}")


def test_push_alerts_dry_run(vault):
    """Case 10: push_alerts --dry-run 工作 (V1.0.2)"""
    print("\n[Test 10] push_alerts dry-run works")
    # 先跑 daily 让 alerts.md 有内容
    run([sys.executable, str(SCRIPTS / "daily_todo_check.py"), "--vault", str(vault)], check=True)

    result = run([
        sys.executable, str(SCRIPTS / "push_alerts.py"),
        "--vault", str(vault),
        "--dry-run",
    ], check=True)
    assert "[DRY-RUN osascript]" in result.stdout
    print(f"  ✓ push dry-run: {result.stdout.strip()[:80]}...")


def test_plist_templates_exist():
    """Case 11: 3 段 plist 模板都存在且语法 OK (V1.0.2)"""
    print("\n[Test 11] 3 plist templates exist + valid syntax")
    plist_dir = REPO_ROOT / "plist"
    assert plist_dir.exists(), f"plist/ dir missing: {plist_dir}"
    plists = sorted(plist_dir.glob("com.todo.*.plist"))
    assert len(plists) == 3, f"expected 3 plists, got {len(plists)}: {plists}"
    for p in plists:
        # plutil -lint 校验
        r = subprocess.run(["plutil", "-lint", str(p)], capture_output=True, text=True)
        assert r.returncode == 0, f"plist invalid: {p}\n{r.stderr}"
        print(f"  ✓ {p.name} syntax OK")


def test_daily_check_detects_stale_blocked(vault):
    """Case 12: daily_check 检测 BLOCKED >3 天 (V1.0.2)"""
    print("\n[Test 12] daily_check detects stale BLOCKED")
    # 建 14 天前 BLOCKED 的 todo, mtime 改到 14 天前
    blocked_file = vault / "BLOCKED" / "2026-05-15-old-blocked-P1-BLOCKED.md"
    blocked_file.write_text("""---
type: todo
title: 卡住 19 天
status: BLOCKED
priority: P1
due: 2026-06-01
---
""", encoding="utf-8")
    import os
    old_time = (datetime.now() - timedelta(days=19)).timestamp()
    os.utime(blocked_file, (old_time, old_time))

    result = run([
        sys.executable, str(SCRIPTS / "daily_todo_check.py"),
        "--vault", str(vault), "--json",
    ], check=True)
    data = json.loads(result.stdout)
    stale = data.get("stale_blocked", [])
    assert len(stale) >= 1, f"expected stale_blocked, got {stale}"
    assert any(t["title"] == "卡住 19 天" for t in stale), f"expected title match: {stale}"
    print(f"  ✓ detected {len(stale)} stale BLOCKED (卡住 19 天)")


# V1.0.3 新增 4 个 case ----------------------------------------------------
def test_todo_create_output_text(vault):
    """--output text 给人类可读 (不破坏 JSON 默认)"""
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    result = run([
        sys.executable, str(SCRIPTS / "todo_create.py"),
        "--vault", str(vault), "--type", "create",
        "--title", "测试 V1.0.3 text 模式",
        "--due", tomorrow,
        "--output", "text",
    ], check=True)
    # text 模式: 人类可读, 不是 JSON
    assert "✅" in result.stdout, f"text mode should have ✅: {result.stdout!r}"
    assert "priority:" in result.stdout, f"text mode should show priority: {result.stdout!r}"
    assert "validate:" in result.stdout, f"text mode should show validate exit: {result.stdout!r}"
    # 重要: 不应是 JSON (没开括号打头)
    assert not result.stdout.lstrip().startswith("{"), \
        f"text mode should NOT start with JSON: {result.stdout!r}"
    print(f"  ✓ --output text: 人类可读格式正确")


def test_todo_create_output_json_explicit(vault):
    """--output json 显式 flag (跟默认行为一致)"""
    tomorrow = (date.today() + timedelta(days=2)).isoformat()
    result = run([
        sys.executable, str(SCRIPTS / "todo_create.py"),
        "--vault", str(vault), "--type", "create",
        "--title", "测试 V1.0.3 json 显式",
        "--due", tomorrow,
        "--output", "json",
    ], check=True)
    # json 模式: 可被 json.loads
    data = json.loads(result.stdout)
    assert data.get("ok") is True, f"json should have ok=True: {data}"
    assert data.get("type") == "ok"
    assert "file_path" in data
    assert "priority" in data
    print(f"  ✓ --output json: 显式 flag 工作 (跟默认一致)")


def test_todo_create_output_default_is_json(vault):
    """无 --output flag 时默认 json (V1.0.3 不破坏旧行为)"""
    tomorrow = (date.today() + timedelta(days=3)).isoformat()
    result = run([
        sys.executable, str(SCRIPTS / "todo_create.py"),
        "--vault", str(vault), "--type", "create",
        "--title", "测试 V1.0.3 默认",
        "--due", tomorrow,
    ], check=True)
    data = json.loads(result.stdout)  # 默认必须能被 json.loads
    assert data.get("ok") is True
    print(f"  ✓ 默认行为 (无 --output) 仍是 JSON, 不破坏 V1.0 调用方")


def test_install_sh_runs_from_skill_dir(vault):
    """install.sh 在 skill 目录跑 (aweskill 装完后实际场景)"""
    # 找 install.sh 所在目录
    install_sh = REPO_ROOT / "install.sh"
    assert install_sh.exists(), f"install.sh 缺失: {install_sh}"
    # 跑 dry-run (不真改 vault)
    result = subprocess.run(
        ["bash", str(install_sh), "--dry-run", "--vault", str(vault)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, \
        f"install.sh dry-run from skill dir failed (exit {result.returncode}): {result.stderr}"
    assert "Skill dir:" in result.stdout, \
        f"install.sh 应输出 Skill dir 字段: {result.stdout[:500]}"
    # V1.0.3 关键: 不应说"请确认 install.sh 在仓库根目录跑"
    assert "请确认 install.sh 在仓库根目录跑" not in result.stdout, \
        "V1.0.3 修复: 不应再显示过时的 V1.0 错误文案"
    print(f"  ✓ install.sh 在 skill 目录跑 (aweskill 装完后场景) 通过")


def main():
    print("=" * 60)
    print("  obsidian-personal-todo-tracker V1.0.3 端到端测试")
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
        # V1.0.2 新增 5 个 case
        test_weekly_summary(vault)
        test_monthly_summary_skip(vault)
        test_push_alerts_dry_run(vault)
        test_plist_templates_exist()
        test_daily_check_detects_stale_blocked(vault)
        # V1.0.3 新增 4 个 case
        test_todo_create_output_text(vault)
        test_todo_create_output_json_explicit(vault)
        test_todo_create_output_default_is_json(vault)
        test_install_sh_runs_from_skill_dir(vault)
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
    print("  ✅ 所有 16 个端到端测试通过 (V1.0 = 7 + V1.0.2 = 5 + V1.0.3 = 4)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
