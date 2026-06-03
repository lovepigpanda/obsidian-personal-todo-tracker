#!/usr/bin/env python3
"""
daily_todo_check.py - 每日 todo 巡检 (V1.0)

用法:
    python3 scripts/daily_todo_check.py
    python3 scripts/daily_todo_check.py --vault ~/Obsidian/todo
    python3 scripts/daily_todo_check.py --list-only      # 只列不打 alerts
    python3 scripts/daily_todo_check.py --json            # JSON 输出

行为:
1. 扫 ~/Obsidian/todo/ACTIVE/ 下所有 todo
2. 算每个 todo 距 due 多少天:
   - days < 0  → OVERDUE (ERROR 级, 红色)
   - days = 0  → TODAY (WARN 级, 黄色)
   - 0 < days ≤ 3 → SOON (WARN 级, 黄色)
   - 3 < days ≤ 7 → UPCOMING (INFO 级, 蓝色)
   - days > 7  → FAR (不报)
3. 按 priority + days 排序
4. 写到 ~/Obsidian/todo/alerts.md (Agent 后续读这个文件主动推)

退出码:
    0 - 写成功 (有/无 alerts 都算成功)
    1 - 写失败 / vault 不存在
    2 - 参数错误

学 finance track V1.3.4 daily_integrity_check.py 模式:
- alerts.md 始终写, 用户在 Obsidian 看
- Agent 读后用自己通道推
- 不依赖 cron, Agent 会话开始主动跑 (V1.0 不配 plist)
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 让脚本可独立运行, 也可被 import
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from parsers import parse_todo_file


# ============================================================
# 巡检逻辑
# ============================================================

def categorize(todo: Dict[str, Any], today: date) -> Tuple[str, str]:
    """
    给 todo 打 severity + bucket:
        (severity, bucket)
        severity: ERROR / WARN / INFO / OK
        bucket: OVERDUE / TODAY / SOON / UPCOMING / FAR
    """
    due = todo.get("due")
    if not due:
        return ("INFO", "NO_DUE")

    days = (due - today).days
    if days < 0:
        return ("ERROR", "OVERDUE")
    if days == 0:
        return ("WARN", "TODAY")
    if days <= 3:
        return ("WARN", "SOON")
    if days <= 7:
        return ("INFO", "UPCOMING")
    return ("OK", "FAR")


# Priority 排序权重
PRIORITY_WEIGHT = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def scan_vault(vault: Path, today: date) -> List[Dict[str, Any]]:
    """
    扫 vault/ACTIVE/ 下所有 todo, 返回排序后的列表.

    V1.0.2 增强: 同时扫 BLOCKED/ 找超 3 天的 (stale blocked)

    每项: {path, todo, severity, bucket, days}
    """
    results: List[Dict[str, Any]] = []
    active_dir = vault / "ACTIVE"
    if not active_dir.exists():
        return results

    for md_file in sorted(active_dir.glob("*.md")):
        todo, warnings = parse_todo_file(md_file)
        if todo is None:
            # 解析失败, 仍加入但用 ERROR 标记
            results.append({
                "path": md_file,
                "filename": md_file.name,
                "title": md_file.stem,
                "status": "?",
                "priority": "P3",
                "due": None,
                "severity": "ERROR",
                "bucket": "PARSE_FAILED",
                "days": None,
                "parse_error": warnings,
            })
            continue

        severity, bucket = categorize(todo, today)
        days = (todo["due"] - today).days if todo["due"] else None
        results.append({
            "path": md_file,
            "filename": md_file.name,
            "title": todo.get("title", md_file.stem),
            "status": todo.get("status", "?"),
            "priority": todo.get("priority", "P3"),
            "due": todo["due"].isoformat() if todo["due"] else None,
            "severity": severity,
            "bucket": bucket,
            "days": days,
            "note": todo.get("note", ""),
        })

    # 排序: severity asc (ERROR < WARN < INFO < OK), priority asc, days asc
    severity_weight = {"ERROR": 0, "WARN": 1, "INFO": 2, "OK": 3}
    results.sort(key=lambda r: (
        severity_weight.get(r["severity"], 9),
        PRIORITY_WEIGHT.get(r["priority"], 9),
        r["days"] if r["days"] is not None else 9999,
    ))
    return results


def scan_stale_blocked(vault: Path, today: date, min_days: int = 3) -> List[Dict[str, Any]]:
    """
    扫 BLOCKED/ 找超 min_days 天的 (mtime 距今 >= min_days).

    V1.0.2 主动能力: Agent 拿到这个列表会主动问"X 这个 BLOCKED N 天了, 怎么办?"
    """
    results = []
    blocked_dir = vault / "BLOCKED"
    if not blocked_dir.exists():
        return results
    for md_file in sorted(blocked_dir.glob("*.md")):
        todo, _ = parse_todo_file(md_file)
        if todo is None:
            continue
        mtime = datetime.fromtimestamp(md_file.stat().st_mtime)
        days_blocked = (today - mtime.date()).days
        if days_blocked >= min_days:
            results.append({
                "path": md_file,
                "filename": md_file.name,
                "title": todo.get("title", md_file.stem),
                "priority": todo.get("priority", "P3"),
                "due": todo["due"].isoformat() if todo["due"] else None,
                "days_blocked": days_blocked,
            })
    results.sort(key=lambda r: -r["days_blocked"])
    return results


# ============================================================
# 渲染 alerts.md
# ============================================================

SEVERITY_EMOJI = {
    "ERROR": "❌",
    "WARN": "⚠️",
    "INFO": "ℹ️",
    "OK": "✅",
}

BUCKET_LABEL = {
    "OVERDUE": "已逾期",
    "TODAY": "今天到期",
    "SOON": "3 天内到期",
    "UPCOMING": "本周内",
    "FAR": "远期",
    "NO_DUE": "无 due",
    "PARSE_FAILED": "解析失败",
}


def render_alerts_md(
    results: List[Dict[str, Any]],
    today: date,
    stale_blocked: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """渲染 ~/Obsidian/todo/alerts.md.

    V1.0.2 增强: 加 stale_blocked 段 (BLOCKED > 3 天的, Agent 主动问)
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if stale_blocked is None:
        stale_blocked = []

    # 统计
    count_overdue = sum(1 for r in results if r["bucket"] == "OVERDUE")
    count_today = sum(1 for r in results if r["bucket"] == "TODAY")
    count_soon = sum(1 for r in results if r["bucket"] == "SOON")
    count_upcoming = sum(1 for r in results if r["bucket"] == "UPCOMING")
    count_far = sum(1 for r in results if r["bucket"] == "FAR")
    count_no_due = sum(1 for r in results if r["bucket"] == "NO_DUE")
    count_failed = sum(1 for r in results if r["bucket"] == "PARSE_FAILED")

    lines = [
        f"# Todo Alerts — {today.isoformat()}",
        "",
        f"> 自动生成: {now_str}  ·  source: `daily_todo_check.py` V1.0",
        "",
        "## 摘要",
        "",
        f"- ❌ 逾期: **{count_overdue}**",
        f"- ⚠️ 今天到期: **{count_today}**",
        f"- ⚠️ 3 天内: **{count_soon}**",
        f"- ℹ️ 本周内: **{count_upcoming}**",
        f"- ✅ 远期: {count_far}",
        f"- ℹ️ 无 due: {count_no_due}",
        f"- ❌ 解析失败: {count_failed}",
        "",
    ]

    if count_overdue + count_today + count_soon > 0:
        lines.append("## 🚨 需要关注 (按 priority 排序)")
        lines.append("")
        for r in results:
            if r["bucket"] not in ("OVERDUE", "TODAY", "SOON"):
                continue
            emoji = SEVERITY_EMOJI.get(r["severity"], "•")
            bucket_label = BUCKET_LABEL.get(r["bucket"], r["bucket"])
            days_str = f"{r['days']}天" if r["days"] is not None and r["days"] >= 0 else f"逾期{-r['days'] if r['days'] is not None else '?'}天"
            lines.append(
                f"- {emoji} **{r['priority']}** {r['title']} "
                f"({bucket_label} {days_str}, due {r['due'] or '?'})"
            )
        lines.append("")

    if count_upcoming > 0:
        lines.append("## ℹ️ 本周内")
        lines.append("")
        for r in results:
            if r["bucket"] != "UPCOMING":
                continue
            lines.append(
                f"- {r['priority']} {r['title']} (due {r['due']}, {r['days']}天后)"
            )
        lines.append("")

    if count_far > 0:
        lines.append("## ✅ 远期 (不报)")
        lines.append("")
        for r in results:
            if r["bucket"] != "FAR":
                continue
            lines.append(f"- {r['priority']} {r['title']} (due {r['due']}, {r['days']}天后)")
        lines.append("")

    if count_no_due > 0:
        lines.append("## ℹ️ 无 due 日期")
        lines.append("")
        for r in results:
            if r["bucket"] != "NO_DUE":
                continue
            lines.append(f"- {r['priority']} {r['title']}")
        lines.append("")

    if count_failed > 0:
        lines.append("## ❌ 解析失败 (需修复)")
        lines.append("")
        for r in results:
            if r["bucket"] != "PARSE_FAILED":
                continue
            lines.append(f"- {r['filename']}: {r.get('parse_error', [])}")
        lines.append("")

    if stale_blocked:
        lines.append("## 🚨 BLOCKED 超期 (Agent 主动问: 这个怎么办?)")
        lines.append("")
        for t in stale_blocked:
            lines.append(
                f"- {t['priority']} {t['title']} "
                f"(BLOCKED {t['days_blocked']} 天, due {t['due'] or '?'})"
            )
        lines.append("")
        lines.append("> 建议: 跟 Agent 商量, 该继续/延期/取消/拆分")
        lines.append("")

    if not results:
        lines.append("🎉 当前 ACTIVE/ 目录为空, 无 todo.")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"扫描目录: `~/Obsidian/todo/ACTIVE/` ({len(results)} 文件)")
    lines.append("")
    lines.append("> 本文件由 `daily_todo_check.py` 自动维护, Agent 读后推送.")
    lines.append("> 手工编辑会被下次巡检覆盖.")

    return "\n".join(lines)


# ============================================================
# CLI
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Daily todo vault check - writes alerts.md"
    )
    parser.add_argument(
        "--vault", default="~/Obsidian/todo",
        help="path to todo vault (default: ~/Obsidian/todo)",
    )
    parser.add_argument(
        "--list-only", action="store_true",
        help="only print to stdout, don't write alerts.md",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="output JSON instead of human-readable",
    )
    args = parser.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    if not vault.exists() or not vault.is_dir():
        print(f"ERROR: vault not found: {vault}", file=sys.stderr)
        return 1

    today = date.today()
    results = scan_vault(vault, today)
    stale_blocked = scan_stale_blocked(vault, today)

    if args.json:
        # JSON 不写文件
        # 去掉 Path 对象 (不序列化)
        def _clean(r):
            return {k: (str(v) if hasattr(v, "__fspath__") else v) for k, v in r.items() if k != "path"}
        output = {
            "date": today.isoformat(),
            "vault": str(vault),
            "total": len(results),
            "stale_blocked_count": len(stale_blocked),
            "results": [_clean(r) for r in results],
            "stale_blocked": [_clean(t) for t in stale_blocked],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    if args.list_only:
        # 打印列表
        for r in results:
            severity = SEVERITY_EMOJI.get(r["severity"], "•")
            days_str = f"{r['days']}d" if r["days"] is not None else "?"
            print(f"  {severity} {r['priority']} {r['title']} ({days_str})")
        if stale_blocked:
            print()
            print("  🚨 BLOCKED 超期:")
            for t in stale_blocked:
                print(f"    - {t['priority']} {t['title']} ({t['days_blocked']}d)")
        return 0

    # 写 alerts.md
    content = render_alerts_md(results, today, stale_blocked=stale_blocked)
    alerts_path = vault / "alerts.md"

    # 原子写
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".md", dir=vault)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, alerts_path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

    # 简明统计输出
    count_action = sum(1 for r in results if r["bucket"] in ("OVERDUE", "TODAY", "SOON"))
    count_total = len(results)
    print(f"✅ alerts.md updated ({count_total} todos, {count_action} need attention)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
