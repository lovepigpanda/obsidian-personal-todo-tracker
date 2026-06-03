#!/usr/bin/env python3
"""
monthly_summary.py - 月末自检 (V1.0.2)

用法:
    python3 scripts/monthly_summary.py
    python3 scripts/monthly_summary.py --vault ~/Obsidian/todo
    python3 scripts/monthly_summary.py --month 2026-05
    python3 scripts/monthly_summary.py --json

行为:
1. 范围: 当月 1 号 ~ 当月最后一天 (未结束则截止到今日)
2. 统计:
   - 本月新建 todo
   - 本月完成 (DONE/ 移动时间)
   - 完成率 = 完成 / (新建 + 上月末遗留) × 100%
   - 当前 ACTIVE/ 数量 (未处理)
   - BLOCKED / SNOOZED / CANCELED 数量
   - 跨月遗留 (上月末 ACTIVE 本月还在 ACTIVE)
   - 平均完成时间 (从 created 到 done mtime)
   - 滞销清单 (created 超 30 天还在 ACTIVE)
3. 写到 ~/Obsidian/todo/alerts.md 末尾追加 "## 📅 月度报告" 段
4. --json 输出

退出码: 0/1/2 同 weekly_summary

学 finance track V1.3 monthly_summary.py 模式:
- 储蓄率 (finance) → 完成率 (todo, 完成/新增+遗留)
- 月度分类汇总 → 状态分布
"""

import argparse
import calendar
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from parsers import parse_todo_file

PRIORITY_WEIGHT = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def month_range(year: int, month: int) -> tuple:
    """返回 (本月第一天, 下月第一天)"""
    first = date(year, month, 1)
    if month == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month + 1, 1)
    return (first, next_first)


def scan_dir(dir_path: Path) -> List[Dict[str, Any]]:
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


def summarize(vault: Path, year: int, month: int) -> Dict[str, Any]:
    month_start, month_end = month_range(year, month)
    today = date.today()

    active = scan_dir(vault / "ACTIVE")
    done = scan_dir(vault / "DONE")
    blocked = scan_dir(vault / "BLOCKED")
    snoozed = scan_dir(vault / "SNOOZED")
    canceled = scan_dir(vault / "CANCELED")
    all_now = active + done + blocked + snoozed + canceled

    # 本月新建
    new_this_month = [t for t in all_now
                      if in_range(t.get("created"), month_start, month_end)]

    # 本月完成 (DONE/ 的 mtime 在本月)
    completed_this_month = [t for t in done
                            if in_range(t["_mtime"], month_start, month_end)]

    # 上月末遗留 (created < month_start 且当前在 ACTIVE/)
    carried_over = [t for t in active
                    if t.get("created") and t["created"] < month_start]

    # 完成率
    total_in_scope = len(new_this_month) + len(carried_over)
    completion_rate = (len(completed_this_month) / total_in_scope * 100) if total_in_scope else 0.0

    # 平均完成时间 (created -> mtime in DONE)
    completion_times = []
    for t in completed_this_month:
        if t.get("created") and t["_mtime"]:
            days = (t["_mtime"].date() - t["created"]).days
            if days >= 0:
                completion_times.append(days)
    avg_completion_days = sum(completion_times) / len(completion_times) if completion_times else None

    # 滞销: created 距今 > 30 天 还在 ACTIVE/
    stale_active = []
    for t in active:
        if t.get("created"):
            age = (today - t["created"]).days
            if age > 30:
                stale_active.append({**{k: v for k, v in t.items() if not k.startswith("_")}, "age_days": age})
    stale_active.sort(key=lambda x: -x["age_days"])

    # priority 分布
    active_by_pri = {}
    for t in active:
        p = t.get("priority", "P3")
        active_by_pri[p] = active_by_pri.get(p, 0) + 1
    completed_by_pri = {}
    for t in completed_this_month:
        p = t.get("priority", "P3")
        completed_by_pri[p] = completed_by_pri.get(p, 0) + 1

    return {
        "year": year,
        "month": month,
        "month_start": month_start.isoformat(),
        "month_end_exclusive": month_end.isoformat(),
        "today": today.isoformat(),
        "is_complete_month": month_end <= today,
        "new_this_month": len(new_this_month),
        "completed_this_month": len(completed_this_month),
        "carried_over": len(carried_over),
        "completion_rate": round(completion_rate, 1),
        "avg_completion_days": round(avg_completion_days, 1) if avg_completion_days is not None else None,
        "state_counts": {
            "ACTIVE": len(active),
            "DONE": len(done),
            "BLOCKED": len(blocked),
            "SNOOZED": len(snoozed),
            "CANCELED": len(canceled),
        },
        "active_by_priority": active_by_pri,
        "completed_by_priority": completed_by_pri,
        "stale_active": [{"title": t["title"], "age_days": t["age_days"], "priority": t["priority"]}
                        for t in stale_active[:10]],  # top 10
    }


def render_markdown(data: Dict[str, Any]) -> str:
    lines = [
        "",
        f"## 📅 月度报告 ({data['year']}-{data['month']:02d})",
        "",
        f"> 自动生成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ·  "
        f"source: `monthly_summary.py` V1.0.2  ·  "
        f"{'完整月' if data['is_complete_month'] else '进行中月'}",
        "",
        "### 月度摘要",
        "",
        f"- 新建: **{data['new_this_month']}**",
        f"- 完成: **{data['completed_this_month']}**",
        f"- 上月遗留: **{data['carried_over']}**",
        f"- 完成率: **{data['completion_rate']}%**",
    ]
    if data["avg_completion_days"] is not None:
        lines.append(f"- 平均完成时间: **{data['avg_completion_days']} 天**")
    lines.append("")

    lines.append("### 当前状态分布")
    lines.append("")
    for state, n in data["state_counts"].items():
        lines.append(f"- {state}: {n}")
    lines.append("")

    if data["active_by_priority"]:
        lines.append("### ACTIVE 按 priority")
        lines.append("")
        for prio in ("P0", "P1", "P2", "P3"):
            n = data["active_by_priority"].get(prio, 0)
            if n > 0:
                lines.append(f"- {prio}: {n}")
        lines.append("")

    if data["completed_by_priority"]:
        lines.append("### 本月完成按 priority")
        lines.append("")
        for prio in ("P0", "P1", "P2", "P3"):
            n = data["completed_by_priority"].get(prio, 0)
            if n > 0:
                lines.append(f"- {prio}: {n}")
        lines.append("")

    if data["stale_active"]:
        lines.append("### 🐌 滞销清单 (ACTIVE 超过 30 天)")
        lines.append("")
        for t in data["stale_active"]:
            lines.append(f"- {t['priority']} {t['title']} (创建 {t['age_days']} 天前)")
        lines.append("")
        lines.append("> 建议: 取消/延期/拆分/继续推进, 别让 todo 烂尾")
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def append_to_alerts(vault: Path, content: str) -> None:
    alerts = vault / "alerts.md"
    if alerts.exists():
        existing = alerts.read_text(encoding="utf-8")
    else:
        existing = "# Todo Alerts\n"
    alerts.write_text(existing + content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Monthly todo summary")
    parser.add_argument("--vault", default="~/Obsidian/todo")
    parser.add_argument("--month", help="YYYY-MM (default: current month)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    if not vault.exists() or not vault.is_dir():
        print(f"ERROR: vault not found: {vault}", file=sys.stderr)
        return 1

    if args.month:
        try:
            year, month = map(int, args.month.split("-"))
        except ValueError:
            print(f"ERROR: --month must be YYYY-MM", file=sys.stderr)
            return 2
    else:
        today = date.today()
        year, month = today.year, today.month

    # launchd 简化: 每月 28 号跑, 脚本判断 "今天是不是本月最后一天"
    # 如果不是月末, 静默 skip (exit 0), 不发 alerts.md
    today = date.today()
    if args.month:
        # 用户显式指定月份, 跑 (完整月)
        pass
    else:
        # 默认当月, 检查 today 是不是最后一天
        last_day = calendar.monthrange(today.year, today.month)[1]
        if today.day != last_day:
            # 不是月末, 跳过 (launchd 28 号可能早跑)
            print(f"⏭️  跳过: 今天 {today} 不是本月最后一天 (本月最后一天 = {last_day})")
            print(f"   等到月末再跑, 或显式 --month YYYY-MM")
            return 0

    data = summarize(vault, year, month)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    md = render_markdown(data)

    if not args.no_write:
        append_to_alerts(vault, md)

    print(f"📅 {year}-{month:02d}: 新建 {data['new_this_month']}, "
          f"完成 {data['completed_this_month']}, 完成率 {data['completion_rate']}%")
    if data["stale_active"]:
        print(f"🐌 {len(data['stale_active'])} 个滞销 todo, 建议处理")
    return 0


if __name__ == "__main__":
    sys.exit(main())
