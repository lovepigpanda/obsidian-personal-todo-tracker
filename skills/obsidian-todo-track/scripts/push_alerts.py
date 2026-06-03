#!/usr/bin/env python3
"""
push_alerts.py - 推送 alerts 摘要 (V1.0.2)

用法:
    python3 scripts/push_alerts.py                  # 默认从 alerts.md 读
    python3 scripts/push_alerts.py --message "..."  # 直接推自定义消息
    python3 scripts/push_alerts.py --channel osascript  # 强制桌面通知
    python3 scripts/push_alerts.py --channel wecom   # 强制企业微信 webhook
    python3 scripts/push_alerts.py --dry-run         # 不真发, 打印预览

行为:
1. 读 ~/Obsidian/todo/alerts.md 解析"需要关注"段
2. 生成短摘要 (e.g. "📋 3 个 todo 需关注: 1 逾期, 1 今天, 1 三天内")
3. 推送到 1+ 个 channel:
   - osascript (macOS 桌面通知, 默认)
   - wecom (企业微信 webhook, 读 ~/.obsidian-todo/push_config.json)
   - feishu (飞书 webhook, 同上)
4. 退出码: 0=成功, 1=alerts.md 缺失, 2=所有 channel 都失败

学 finance track V1.3.4 daily_integrity_check 模式:
- 脚本只做最基础的 (alerts.md + 桌面通知)
- 高级推送 (飞书/微信 webhook) 由用户配 ~/.obsidian-todo/push_config.json
- Agent 已有通道更稳 — 走 Agent 而不走 webhook
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PUSH_CONFIG_PATH = Path.home() / ".obsidian-todo" / "push_config.json"


# ============================================================
# 解析 alerts.md → 摘要
# ============================================================

def parse_alerts(alerts_path: Path) -> Dict[str, Any]:
    """解析 alerts.md 找 "需要关注" 段."""
    if not alerts_path.exists():
        return {"exists": False, "need_attention": [], "summary_line": None}

    text = alerts_path.read_text(encoding="utf-8")

    # 找 "🚨 需要关注" 段 (daily_check 输出的)
    need_attention = []
    in_section = False
    for line in text.split("\n"):
        if "## 🚨 需要关注" in line or "## 需要关注" in line:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            in_section = False
            break
        if in_section and line.strip().startswith("- "):
            need_attention.append(line.strip()[2:])

    # 找摘要 (overdue / today / soon)
    overdue = 0
    today = 0
    soon = 0
    for line in text.split("\n"):
        if "逾期:" in line and "**" in line:
            try:
                overdue = int(line.split("**")[1])
            except (IndexError, ValueError):
                pass
        elif "今天到期:" in line and "**" in line:
            try:
                today = int(line.split("**")[1])
            except (IndexError, ValueError):
                pass
        elif "3 天内:" in line and "**" in line:
            try:
                soon = int(line.split("**")[1])
            except (IndexError, ValueError):
                pass

    total = overdue + today + soon
    if total == 0:
        summary_line = "📋 暂无 todo 需关注"
    else:
        parts = []
        if overdue: parts.append(f"❌ 逾期 {overdue}")
        if today: parts.append(f"⚠️ 今天 {today}")
        if soon: parts.append(f"📅 3 天内 {soon}")
        summary_line = f"📋 todo 需关注 ({total}): " + ", ".join(parts)

    return {
        "exists": True,
        "need_attention": need_attention,
        "overdue": overdue,
        "today": today,
        "soon": soon,
        "summary_line": summary_line,
    }


# ============================================================
# Channel: macOS 桌面通知 (osascript)
# ============================================================

def push_osascript(message: str, dry_run: bool = False) -> bool:
    """macOS 桌面通知."""
    if dry_run:
        print(f"[DRY-RUN osascript] {message}")
        return True
    if sys.platform != "darwin":
        print(f"[skip osascript, not macOS] {message}")
        return False
    try:
        # AppleScript 转义
        escaped = message.replace('"', '\\"').replace('\\', '\\\\')
        script = f'display notification "{escaped}" with title "Todo Alerts" sound name "Submarine"'
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[osascript fail] {e}", file=sys.stderr)
        return False


# ============================================================
# Channel: Webhook (wecom / feishu)
# ============================================================

def load_push_config() -> Dict[str, Any]:
    if not PUSH_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(PUSH_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def push_webhook(url: str, message: str, channel: str, dry_run: bool = False) -> bool:
    """推送到 webhook (wecom/feishu/dingtalk 通用 POST JSON)."""
    if dry_run:
        print(f"[DRY-RUN {channel}] {message}")
        return True

    import urllib.request
    import urllib.error

    if channel == "wecom":
        # 企业微信 markdown 格式
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": f"**Todo Alerts**\n\n{message}"},
        }
    elif channel == "feishu":
        # 飞书 interactive card
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": "Todo Alerts"}},
                "elements": [{"tag": "markdown", "content": message}],
            },
        }
    elif channel == "dingtalk":
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": "Todo Alerts", "text": message},
        }
    else:
        print(f"[unknown channel: {channel}]", file=sys.stderr)
        return False

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "obsidian-todo-track/V1.0.2"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"[{channel} fail] {e}", file=sys.stderr)
        return False


# ============================================================
# Main
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="Push todo alerts to channels")
    parser.add_argument("--vault", default="~/Obsidian/todo")
    parser.add_argument("--message", help="custom message (skip alerts.md parsing)")
    parser.add_argument(
        "--channel",
        action="append",
        choices=["osascript", "wecom", "feishu", "dingtalk"],
        help="channel to push to (can repeat, default=osascript)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    alerts_path = vault / "alerts.md"

    # 1. 准备消息
    if args.message:
        message = args.message
    else:
        data = parse_alerts(alerts_path)
        if not data["exists"]:
            print(f"ERROR: alerts.md not found: {alerts_path}", file=sys.stderr)
            return 1
        message = data["summary_line"]
        if data["need_attention"]:
            # 加 top 3 项
            message += "\n\n" + "\n".join(data["need_attention"][:3])

    # 2. 推送到 channels
    channels = args.channel or ["osascript"]
    config = load_push_config()
    success = 0
    failed = 0

    for ch in channels:
        if ch == "osascript":
            if push_osascript(message, args.dry_run):
                success += 1
            else:
                failed += 1
        else:
            url = config.get(ch)
            if not url:
                print(f"[{ch}] no URL in {PUSH_CONFIG_PATH}, skipping", file=sys.stderr)
                failed += 1
                continue
            if push_webhook(url, message, ch, args.dry_run):
                success += 1
            else:
                failed += 1

    print(f"📤 push done: {success} ok, {failed} failed, total {len(channels)} channels")

    if failed == len(channels):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
