#!/usr/bin/env python3
"""
weekly_summary.py - 周末复盘 (V1.0.2)

用法:
    python3 scripts/weekly_summary.py
    python3 scripts/weekly_summary.py --vault ~/Obsidian/todo
    python3 scripts/weekly_summary.py --json

行为:
1. 扫 ACTIVE/ + DONE/ + BLOCKED/ + SNOOZED/ + CANCELED/ 5 个目录
2. 范围: 本周一 00:00 ~ 本周日 23:59 (Asia/Shanghai)
3. 统计:
   - 新建 todo 数 (按 created 字段)
   - 完成 todo 数 (按 done 移动到 DONE/ 的时间, 用 mtime)
   - 状态分布 (P0/P1/P2/P3 在 ACTIVE/ 的当前数量)
   - 完成的 priority 分布
   - BLOCKED / SNOOZED / CANCELED 数量
   - 周净增 = 新建 - 完成
4. 写到 ~/Obsidian/todo/alerts.md 末尾追加 "## 📊 本周复盘" 段
5. --json 输出机器可读

退出码: 0=成功, 1=vault 不存在, 2=参数错误

学 finance track V1.2 weekly_summary.py 模式:
- 本周一~周日 范围
- 笔数 / 总数 / priority 分布
- 写到 alerts.md, Agent 后续推
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from parsers import parse_todo_file


# ============================================================
# 范围计算
# ============================================================

def week_range(today: date) -> tuple:
    """
    返回 (本周一, 下周一) — 半开区间 [本周一, 下周一)
    """
    monday = today - timedelta(days=today.weekday())
    next_monday = monday + timedelta(days=7)
    return (monday, next_monday)


# ============================================================
# 核心统计
# ============================================================

PRIORITY_WEIGHT = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def scan_dir(dir_path: Path) -> List[Dict[str, Any]]:
    """扫一个状态目录, 返回所有 todo dict (含 path)."""
    results = []
    if not dir_path.exists():
        return results
    for md_file in dir_path.glob("*.md"):
        todo, _ = parse_todo_file(md_file)
        if todo is None:
            continue
        todo["_path"] = md_file
        todo["_mtime"] = datetime.fromtimestamp(md_file.stat().st_mtime)
        results.append(todo)
    return results


def in_range(dt: Optional[datetime], start: date, end: date) -> bool:
    if dt is None:
        return False
    d = dt.date() if isinstance(dt, datetime) else dt
    return start <= d < end


def summarize(vault: Path, today: date) -> Dict[str, Any]:
    """生成本周复盘统计."""
    week_start, week_end = week_range(today)

    # 扫所有状态目录
    active = scan_dir(vault / "ACTIVE")
    done = scan_dir(vault / "DONE")
    blocked = scan_dir(vault / "BLOCKED")
    snoozed = scan_dir(vault / "SNOOZED")
    canceled = scan_dir(vault / "CANCELED")

    # 本周新建 (created 在 week range)
    new_this_week = [t for t in (active + done + blocked + snoozed + canceled)
                     if in_range(t.get("created"), week_start, week_end)]

    # 本周完成 (DONE/ 里 mtime 在 week range = 本周被移到 DONE)
    completed_this_week = [t for t in done
                           if in_range(t["_mtime"], week_start, week_end)]

    # 当前 ACTIVE/ 状态分布
    active_by_pri: Dict[str, int] = {}
    for t in active:
        p = t.get("priority", "P3")
        active_by_pri[p] = active_by_pri.get(p, 0) + 1

    # 本周完成 priority 分布
    completed_by_pri: Dict[str, int] = {}
    for t in completed_this_week:
        p = t.get("priority", "P3")
        completed_by_pri[p] = completed_by_pri.get(p, 0) + 1

    # 当前状态计数
    state_counts = {
        "ACTIVE": len(active),
        "DONE": len(done),
        "BLOCKED": len(blocked),
        "SNOOZED": len(snoozed),
        "CANCELED": len(canceled),
    }

    # 完成的 todo 标题列表 (前 5 个, 按 priority 排)
    top_completed = sorted(
        completed_this_week,
        key=lambda t: (PRIORITY_WEIGHT.get(t.get("priority", "P3"), 9), t.get("title", "")),
    )[:5]

    # 仍未完成的临期项 (在 ACTIVE/ 里, due 距今 ≤ 3 天)
    upcoming_active = [t for t in active if t.get("due") and 0 <= (t["due"] - today).days <= 3]
    upcoming_active.sort(key=lambda t: (t["due"], PRIORITY_WEIGHT.get(t.get("priority", "P3"), 9)))

    # BLOCKED 超过 3 天的 (主动问的信号)
    stale_blocked = []
    for t in blocked:
        # 用 mtime 当作 "进入 BLOCKED 的时间" 近似
        days_blocked = (today - t["_mtime"].date()).days
        if days_blocked >= 3:
            stale_blocked.append({**{k: v for k, v in t.items() if not k.startswith("_")},
                                  "days_blocked": days_blocked})
    stale_blocked.sort(key=lambda x: -x["days_blocked"])

    return {
        "week_start": week_start.isoformat(),
        "week_end_exclusive": week_end.isoformat(),
        "today": today.isoformat(),
        "new_this_week": len(new_this_week),
        "completed_this_week": len(completed_this_week),
        "net_change": len(new_this_week) - len(completed_this_week),
        "state_counts": state_counts,
        "active_by_priority": active_by_pri,
        "completed_by_priority": completed_by_pri,
        "top_completed": [{"title": t.get("title"), "priority": t.get("priority")} for t in top_completed],
        "upcoming_active": [{"title": t.get("title"), "due": t["due"].isoformat(), "priority": t.get("priority")}
                            for t in upcoming_active],
        "stale_blocked": [{"title": t["title"], "days_blocked": t["days_blocked"], "priority": t["priority"]}
                          for t in stale_blocked],
    }


# ============================================================
# 渲染
# ============================================================

def render_markdown(data: Dict[str, Any]) -> str:
    """渲染 ## 📊 本周复盘 段 (追加到 alerts.md 末尾)."""
    lines = [
        "",
        f"## 📊 本周复盘 ({data['week_start']} ~ {data['week_end_exclusive']})",
        "",
        f"> 自动生成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ·  source: `weekly_summary.py` V1.0.2",
        "",
        "### 摘要",
        "",
        f"- 新建: **{data['new_this_week']}**",
        f"- 完成: **{data['completed_this_week']}**",
        f"- 净增: **{data['net_change']:+d}**",
        "",
        "### 当前状态分布",
        "",
        f"- ACTIVE: {data['state_counts']['ACTIVE']}",
        f"- DONE: {data['state_counts']['DONE']}",
        f"- BLOCKED: {data['state_counts']['BLOCKED']}",
        f"- SNOOZED: {data['state_counts']['SNOOZED']}",
        f"- CANCELED: {data['state_counts']['CANCELED']}",
        "",
    ]

    if data["active_by_priority"]:
        lines.append("### ACTIVE 按 priority")
        lines.append("")
        for prio in ("P0", "P1", "P2", "P3"):
            n = data["active_by_priority"].get(prio, 0)
            if n > 0:
                lines.append(f"- {prio}: {n}")
        lines.append("")

    if data["top_completed"]:
        lines.append("### 本周完成 top 5 (按 priority)")
        lines.append("")
        for t in data["top_completed"]:
            lines.append(f"- ✅ {t['priority']} {t['title']}")
        lines.append("")

    if data["upcoming_active"]:
        lines.append("### ⚠️ ACTIVE 临期 (≤3 天)")
        lines.append("")
        for t in data["upcoming_active"]:
            lines.append(f"- {t['priority']} {t['title']} (due {t['due']})")
        lines.append("")

    if data["stale_blocked"]:
        lines.append("### 🚨 BLOCKED 超 3 天 (建议处理)")
        lines.append("")
        for t in data["stale_blocked"]:
            lines.append(f"- {t['priority']} {t['title']} (BLOCKED {t['days_blocked']} 天)")
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def append_to_alerts(vault: Path, content: str) -> None:
    """追加到 alerts.md 末尾 (不覆盖)."""
    alerts = vault / "alerts.md"
    if alerts.exists():
        existing = alerts.read_text(encoding="utf-8")
    else:
        existing = "# Todo Alerts\n"
    alerts.write_text(existing + content, encoding="utf-8")


# ============================================================
# CLI
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="Weekly todo summary")
    parser.add_argument("--vault", default="~/Obsidian/todo")
    parser.add_argument("--json", action="store_true", help="JSON output (don't write alerts.md)")
    parser.add_argument("--no-write", action="store_true", help="don't append to alerts.md (stdout only)")
    args = parser.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    if not vault.exists() or not vault.is_dir():
        print(f"ERROR: vault not found: {vault}", file=sys.stderr)
        return 1

    today = date.today()
    data = summarize(vault, today)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    md = render_markdown(data)

    if not args.no_write:
        append_to_alerts(vault, md)

    # stdout 短摘要
    print(f"📊 本周 ({data['week_start']} ~ {data['week_end_exclusive']}): "
          f"新建 {data['new_this_week']}, 完成 {data['completed_this_week']}, "
          f"净增 {data['net_change']:+d}")
    if data["stale_blocked"]:
        print(f"🚨 {len(data['stale_blocked'])} 个 BLOCKED 超 3 天, 建议处理")
    return 0


if __name__ == "__main__":
    sys.exit(main())
