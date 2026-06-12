---
name: obsidian-todo-track
tagline: 你的 AI 待办管家 · Your AI Todo Partner
description: >
  Obsidian 个人待办追踪 AI Agent Skill。当用户描述待办/任务相关的内容
  （建 todo、做任务、催进度、改 due、标 done 等），或明确说"建个 todo"、
  "催一下"、"我有什么要做的"等触发词时，加载此 Skill。

  支持中文和英文用户，自动解析自然语言输入，在 Obsidian vault 中创建 todo
  .md 文件，并写每日 alerts.md 提醒。

  ⚠️ 技能代码与 todo 数据完全分离，这是本项目的核心设计原则：
  - 技能代码在 ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/（Git 同步）
  - 用户 todo 数据在 ~/Obsidian/todo/（私有，不上传）

  🚨 首次加载强制入口：当用户说"装好了"/"开始用"/"设置 todo"/
  "初始化"等关键词，或 vault 目录缺少 todo/_config.md 时，
  **必须**立即执行「Onboarding 7 步」，不能直接进入 todo 流程。
  未完成 Onboarding = 未真正启用本技能。

  📌 定位：Agent 不是计算器，是**主动管家** (V1.0.2 已完整交付)。
  - 主动跑 daily_todo_check.py (每日 18:00 launchd)
  - 主动给 due 临近的 todo 发提醒
  - 主动问"这个 todo 要不要 snooze 到下周"
  - 主动问"BLOCKED 状态超过 3 天的 todo 怎么办" (V1.0.2 新)
  - 每周日 20:00 自动跑 weekly_summary, 月末自动跑 monthly_summary
  - 主动推送到 macOS 桌面通知 (V1.0.2 新; 飞书/微信 webhook 配 ~/.obsidian-todo/push_config.json)
triggers:
  # === 初始化触发词（首次使用）===
  - 装好了
  - 开始用
  - 初始化
  - 设置todo
  - 设置待办
  - 配置todo
  - onboard
  - setup
  - initialize
  # === todo 触发词 ===
  - todo
  - 待办
  - 做个todo
  - 建个todo
  - 催一下
  - 改due
  - 标done
  - 我有什么要做的
  - 今天的任务
  - 延期
  - 阻塞
  - 取消todo
  - snooze
  - block
  - task
  - reminder
version: V1.0.5
# V1.0 = 最小可落地 (M1)
#   交付: SKILL.md + install.sh + 3 个 stdlib 脚本 (validate_todo / todo_create / daily_todo_check)
#         + 1 个每日巡检 (daily_todo_check) + 1 个默认优先级配置 (default_priorities.yaml)
# V1.0.1 = 仓库重构 (move all into skills/obsidian-todo-track/, aweskill install 自动完整带)
# V1.0.2 = 主动能力全面交付 (跟 finance track V1.3.4 齐平)
#   新增: 3 个脚本 (weekly_summary / monthly_summary / push_alerts)
#         daily_todo_check 增强 (BLOCKED >3 天 主动问)
#         3 段 launchd plist 模板 (daily 18:00 / weekly 周日 20:00 / monthly 月末 21:00)
#         install.sh --install-plist 真装 (学 finance V1.3.4 教训, 不只问要不要)
# V1.0.3 = 路径 bug 修复 batch (Evan 测试发现 3 bug, 16/16 e2e 全过, 6 端 SHA256 一致)
# V1.0.4 = 工作流教训沉淀: Evan 反馈"没确认状态就给方案"+"别把问题埋进选项表"
#   新增: references/fact-check-before-recommendation.md (6 项核查模板 + 配套写作规则)
#         SKILL.md § 注意事项 §9 (跨系统假设必须 fact-check)
#         SKILL.md § 注意事项 §10 (别把问题埋进选项表)
#   故意不做: fact-check 自动化脚本 (V1.1 再说; V1.0.4 仍由 agent 手动跑 6 项 + 写表)
# V1.0.5 = done_helper.py 落地 (Evan 测试 2 笔标 done 暴露的 3 个 SKILL.md 错位)
#   新增: scripts/done_helper.py (V1.1 计划提前交付)
#         - --file 精确 / --match 模糊两种入口
#         - 标 done 时自动: filename 前缀换完成日 / frontmatter due 跟 filename 对齐 (满足 validate 强校验)
#         - 自动追加 completed_on / original_due 双日期字段 (保逾期历史)
#         - 自动改 status / updated / 进度区追加 "完成" 行
#         - 原子写 + 自动跑 validate_todo.py
#   改 SKILL.md: § 步骤 2 引用 done_helper.py (不再让 Agent 手改 status + mv)
#                § 步骤 4 命名规则澄清: filename 日期 = frontmatter due = **完成日** (不是 due 日)
#                § 注意事项 §8 改写, 配合 §11 新增 completed_on / original_due 字段用法
#                § V1.0.2 脚本清单 加 #7 done_helper.py
#                § V1.x 后续要做的脚本 划掉 done_helper.py (V1.0.5 ✓)
#   故意不做: snooze_helper / block_helper / cancel_helper (V1.1)
# 故意不做: en 翻译 (V1.4) / Dataview 仪表盘 (V1.6) / project (multi-step) 支持 (明确不做)
status: ACTIVE
tags: [todo, obsidian, agent, productivity, task-tracking]
author: lovepigpanda
github: https://github.com/lovepigpanda/obsidian-personal-todo-tracker
---

# Obsidian Todo Track — AI Agent 待办技能 (V1.0 最小可落地)

> 本 Skill 驱动 AI Agent 完成自然语言待办：解析用户输入 → 匹配默认优先级
> → 创建 .md todo 文件 → 每日巡检 due/逾期 → 主动推送 alerts

## 🚨 强制入口：Onboarding 状态检查（AI Agent 必读）

**加载本 Skill 后第一件事** —— 在做任何 todo 操作之前：

```python
import os
vault = os.path.expanduser("~/Obsidian/todo")
config_file = os.path.join(vault, "todo-config.md")

if not os.path.exists(config_file):
    # ⚠️ 哨兵文件不存在 = 未初始化
    print("⚠️ 检测到首次使用本技能，必须先完成 Onboarding")
    # 立即跳转「步骤 0: Onboarding」章节
    # 不要执行任何 todo / 校验 / 总结操作
else:
    # 已初始化，正常进入 todo 流程
    pass
```

**为什么这是强制的**：

| 情况 | 后果 |
|------|------|
| 用户没初始化就建 todo | 没有 todo-config.md → daily_todo_check 不知道用户偏好；Agent 不知道哪些 prefix 是工作/生活 |
| 初始化但跳过仓库 clone | 找不到 scripts/ → 校验脚本跑不了 |
| **Onboarding 7 步 = 启用本技能的必要条件**，不是可选项 | 任何 agent 跳过 Onboarding = 本次加载视为失败 |

**Onboarding 完成判定**：`todo-config.md` 文件存在且包含 `onboarded: true` 字段。

---

## 数据存储架构 ⚠️ 必读

**技能代码与 todo 数据完全分离**，这是本项目的核心设计原则（学 finance track V1.3.4）：

```
GitHub 仓库                                本地 Obsidian vault（私有，不上传）
─────────────────                          ─────────────────────────────
obsidian-personal-todo-tracker             ~/Obsidian/todo/
├── skills/                              ← 技能代码（暂不发布到 aweskill）
│   └── (本 SKILL.md 的 git 仓库副本)
├── zh/                                  ← 文档（V1.0 只 zh，V1.4+ 加 en）
│   ├── SKILL.md                         ← 本文件
│   ├── AGENTS/                          ← 详细 agent 工作流（V1.0 占位）
│   └── Templates/                       ← todo 模板（V1.0 占位）
├── scripts/                             ← ⭐ stdlib 零依赖 Python 脚本
│   ├── lib/parsers.py                   ← frontmatter 解析
│   ├── validate_todo.py                 ← #1 单笔校验
│   ├── todo_create.py                   ← #2 创建入口（5 层默认 + ask_on_2nd）
│   └── daily_todo_check.py              ← #3 每日巡检（due/逾期/alerts.md）
├── config/
│   └── default_priorities.yaml          ← #4 默认优先级规则（5 层优先级真相源）
├── tests/                               ← 端到端测试
├── install.sh                           ← #5 一键安装
└── README.md

                                          ~/Obsidian/todo/
                                          ├── todo-config.md            ← Onboarding 哨兵
                                          ├── alerts.md                 ← 每日巡检输出
                                          ├── ACTIVE/                   ← ⭐ 真实 todo 数据
                                          │   └── YYYY-MM-DD-{slug}-P{n}-{STATUS}.md
                                          ├── DONE/                     ← 完成后归档
                                          ├── BLOCKED/                  ← 阻塞中
                                          ├── SNOOZED/                  ← 暂缓
                                          └── CANCELED/                 ← 取消
```

### 为什么这样设计？

| 对比项 | GitHub 项目（技能） | 本地 vault（数据） |
|--------|-------------------|-------------------|
| 内容 | 模板、规则、脚本、说明文档 | 你的真实 todo |
| 同步 | `git pull` 从 GitHub 更新 | 永远不上传，私有 |
| 定制 | 可以提交 PR 优化通用规则 | 用户自己的 todo 命名、备注 |
| 风险 | 误操作不会影响 todo 数据 | todo 数据完全隔离 |

### V1.0.2 范围说明 (跟 finance track V1.3.4 齐平)

| 类别 | V1.0.2 真实交付 | 故意不做（V1.x 后续） |
|------|------------------|---------------------|
| 脚本 | validate_todo / todo_create / daily_todo_check / weekly_summary / monthly_summary / push_alerts / **done_helper (V1.0.5 新)** (7 个) | snooze_helper / block_helper / cancel_helper (V1.1) |
| 文档 | zh SKILL.md + zh README.md | en SKILL / en README (V1.4) |
| 模板 | 文件名规范（脚本生成） | 手写 .md 模板 |
| 安装 | install.sh 一键 cp + dry-run + --install-plist | aweskill 自动（V1.5） |
| 定时 | **3 段 plist 真交付** (daily 18:00 / weekly 周日 20:00 / monthly 月末 21:00) | snooze/done/block/cancel 显式 helper (V1.1) |
| 仪表盘 | alerts.md (脚本写) + macOS 桌面通知 + 可选 webhook 推送 | Dataview 仪表盘（V1.5） |

---

## 本地 vault 路径

```
~/Obsidian/todo/
```

**目录结构**（V1.0）：

```
~/Obsidian/todo/
├── todo-config.md                ← Onboarding 哨兵 (agent 写, 用户可改)
├── alerts.md                     ← 每日巡检输出 (agent 写, 用户只读)
├── ACTIVE/                       ← 状态对应的子目录
│   └── YYYY-MM-DD-{slug}-P{n}-{STATUS}.md
├── DONE/
├── BLOCKED/
├── SNOOZED/
└── CANCELED/
```

## 工作原理

```
用户自然语言输入
       ↓
AI Agent 读取 ~/Obsidian/todo/todo-config.md (user preferences)
       ↓
AI Agent 读取 ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/config/default_priorities.yaml
       ↓
解析字段：type / title / due / priority / project / status / note
       ↓
判断 type:
  - create   → 调 todo_create.py → 写 .md 到对应状态目录
  - done     → 改 status=DONE, 移到 DONE/
  - snooze   → 改 due, 移到 SNOOZED/
  - block    → 改 status=BLOCKED, 移到 BLOCKED/
  - cancel   → 改 status=CANCELED, 移到 CANCELED/
  - list     → Agent 自己 query，不写文件
       ↓
todo_create.py 自动调 validate_todo.py (V1.0 强制，V1.0 之前可省)
       ↓
Agent 推送 (Agent 自带通道):
  - 会话开始: 主动跑 daily_todo_check.py 拿今日 todo
  - 每日巡检: launchd 跑 daily_todo_check.py (V1.1 配, V1.0 手动)
  - 写到 alerts.md, Agent 读后用飞书/QQ 推给用户
```

## 触发条件

满足以下任一条件时，加载此 Skill：

1. **明确触发词**：todo / 待办 / 做个todo / 建个todo / 催一下 / 改due / 标done
2. **意图触发词**：我有什么要做的 / 今天的任务 / 延期 / 阻塞 / 取消todo
3. **英文关键词**：todo / task / reminder / snooze / block
4. **意图判断**：用户描述了一件要做的事，不管用什么词

## 🎯 Agent 定位: 主动管家, 不是被动工具 (V1.0.2 已完整交付)

| 被动 ❌ | 主动 ✅ (V1.0.2 真实交付) |
|---------|---------------------------|
| 用户说"建个 todo"才工作 | 会话开始就主动跑 daily_todo_check 拿今日 todo |
| 等用户问"我今天做什么" | 主动说"你今天有 3 项 P1, 1 项已逾期" |
| 用户配 cron / launchd | **Agent 真交付 3 段 plist** (daily 18:00 / weekly 周日 20:00 / monthly 月末), `bash install.sh --install-plist` 一键装 |
| 用户配 webhook 通知 | **Agent 主动推 macOS 桌面通知** (V1.0.2 真交付); 飞书/微信 webhook 配 `~/.obsidian-todo/push_config.json` |
| 等用户发现过期 todo | 提前发现并告警 |
| 等用户发现 BLOCKED 超 3 天 | **V1.0.2 新** daily_check 自动扫, 主动问"这个怎么办?" |

**判断标准**: 如果一件事**用户必须主动做**才能享受, 那就是 Agent 失职。

**✅ V1.0.2 已交付的"主动"** (学 finance V1.3.4):
- 3 段 plist 模板 (不再"等用户问", install.sh --install-plist 真装)
- daily_check 增强 (BLOCKED >3 天 主动问)
- weekly_summary / monthly_summary 脚本 + plist 定时
- push_alerts.py 推 macOS 桌面通知 (webhook 配 push_config.json)

**V1.0.2 仍不做的**:
- 飞书/微信 webhook 推送 (需要用户配 push_config.json, 不是 skill 责任)
- Dataview 仪表盘 (V1.6 计划)
- en 翻译 (V1.4 计划)

---

## 🚀 步骤 0: Onboarding (新用户引导, 7 步)

**触发**: 用户第一次加载本技能（或说"装好了"/"开始用"）。

**不要默默开始建 todo**。先做 7 步配置：

1. **确认 vault 目录** — 默认 `~/Obsidian/todo`，确认或改
2. **验证/clone 仓库** — 检查 `~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/scripts/` 存在；不存在就 `git clone https://github.com/lovepigpanda/obsidian-personal-todo-tracker.git`（V1.0 必须仓库方式，不走 aweskill）
3. **验证必需文件** — 检查 `todo-config.md` / `alerts.md` / `ACTIVE|DONE|BLOCKED|SNOOZED|CANCELED/` 5 个目录在，缺则 Agent 主动帮创建
4. **引导填 todo-config.md** — 问"你想怎么分工作/生活"，帮写哨兵文件
5. **V1.0.2 真配 plist** — Agent 主动 `bash ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/install.sh --install-plist` (3 段 plist 装到 ~/Library/LaunchAgents/ + launchctl load), 不只问"要不要"
6. **配置通知偏好** — 主动问"每日巡检结果我用我自己的通道 (飞书/微信) 发给你，还是只写 alerts.md 你自己看？"
7. **试一个 todo** — 验证整个流程通：Agent 调 `todo_create.py` → 自动调 `validate_todo.py` → 写到 ACTIVE/

**`todo-config.md` 模板** (Agent 主动生成, 用户确认)：

```markdown
---
title: Todo Configuration
type: todo-config
onboarded: true
onboarded_at: 2026-06-03
agent_name: Hermes
notification_channel: feishu   # feishu | wechat | qq | alerts-md
vault_path: ~/Obsidian/todo
auto_validate: true            # todo_create 后自动调 validate_todo
work_prefix: work-             # wikilink 关联到 ~/Obsidian/work/
life_prefix: life-             # wikilink 关联到 ~/Obsidian/life/
default_remind_days: 3         # 距 due ≤ N 天 WARN
---

# AI Agent Todo 配置

> 本文件由 AI Agent 在 Onboarding 时生成, 用户可手动修改。
> **重要**: `onboarded: true` 是 Onboarding 完成哨兵, 删除它 = 强制重做 Onboarding。
> 修改后请告知 Agent, 让它重新校验配置完整性。
```

---

## 执行流程（AI Agent 标准步骤）

### 步骤 1：识别意图

用户输入 → 判断是 **create / done / snooze / block / cancel / list** 六种之一

| 触发词 | 意图 | 示例 |
|--------|------|------|
| 建个 todo / 做个 / 提醒我 | create | "建个 todo 提醒我 6/15 续签合同" |
| 完成了 / done / 标完成 | done | "合同续签完了，标 done" | 调 `done_helper.py --match "合同续签"` (V1.0.5 起, 不再 Agent 手改 status + mv) |
| 暂缓 / snooze / 推迟到下周 | snooze | "续签这个推到下周" |
| 阻塞 / block / 卡住了 | block | "续签被 HR 部门卡住了，标 block" |
| 取消 / cancel / 不用了 | cancel | "续签不用了" |
| 看看 / 列一下 / 我有什么 | list | "我今天有什么要做的" |

### 步骤 2：提取字段

从用户输入提取：

| 字段 | 提取方法 | 示例 |
|------|---------|------|
| `type` | 意图判断 | "建个 todo 提醒我..." → create |
| `title` | 核心名词 | "建个 todo 提醒我 X" → title=X |
| `due` | 时间词 → YYYY-MM-DD | "6/15" → 2026-06-15，"下周一" → 计算 |
| `priority` | 关键词 + 默认规则 | "P0"/"紧急" → P0；没说走 5 层默认 |
| `project` | wikilink 关联 | "工作" → work-，说"项目" → 关联 [[xxx]] |
| `note` | 原始描述 | 用户原话 |
| `status` | 固定值 | ACTIVE（新建）/ DONE / BLOCKED / SNOOZED / CANCELED |

### 步骤 3：匹配默认优先级（5 层 + ask_on_2nd）

如果用户**没指定 priority**，Agent 调 `todo_create.py`，其按 5 层优先级自动选：

1. **用户显式指定**（"P0"/"P1"/"P2"/"P3"）→ 直接用
2. **note 关键词匹配**（"紧急"/"立刻"/"马上" → P0；"重要"/"必须" → P1；"有空" → P3）
3. **config/default_priorities.yaml 规则**（due 距今天数 → priority，见 config 文件）
4. **learning.json 历史偏好**（同 title 关键词 → 上次 priority）
5. **fallback**（P2，标准默认）

**学习机制** (ask_on_2nd)：
- 第一次用默认 priority → 静默记录到 `~/.obsidian-todo/learning.json`
- 第二次同 keyword 但选了不同 priority → Agent 用 `clarify` 工具问用户"改默认吗?"
- 用户确认后 → 更新 learning

**Agent 调用**:
```bash
python3 ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/scripts/todo_create.py \
  --vault ~/Obsidian/todo \
  --type create \
  --title "续签劳动合同" \
  --due 2026-06-15 \
  --note "合同 6/30 到期"
```

(完整路径, 不依赖 cwd; 用相对路径 `scripts/todo_create.py` 时必须先 `cd ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track`)

返回 JSON:
```json
{
  "ok": true,
  "file_path": "ACTIVE/2026-06-15-renew-contract-P1-ACTIVE.md",
  "priority": "P1",
  "source": "config",
  "ask_message": null
}
```

如果 `ask_message` 非空, Agent **必须**用 `clarify` 工具问用户, **不要**直接创建文件。

### 步骤 4：生成文件名

```
{完成日或原 due}-{slug}-{priority}-{STATUS}.md
```

slug = title 的连字符小写版本（中文保留，英文 lowercase）。

**重要 (V1.0.5 澄清)**:
- 对 **ACTIVE/ SNOOZED/ BLOCKED/ CANCELED/** 文件:`{日期}` = frontmatter `due` (V1.0.2 起的硬约束, `validate_todo.py` 强校验 filename 日期 = frontmatter due)
- 对 **DONE/** 文件:`{日期}` = frontmatter `due` = **完成日** (不是原 due),`done_helper.py` 标 done 时自动 rename 改 frontmatter. 原 due 留 `original_due` 字段(详见 §11)

示例:
- `ACTIVE/2026-06-15-renew-contract-P1-ACTIVE.md` (新建, due=2026-06-15)
- `DONE/2026-06-10-renew-contract-P1-DONE.md` (完成日 6-10, due 已同步为 6-10, 原 due 6-15 在 `original_due: 2026-06-15` 字段)

### 步骤 5：创建文件

**文件路径**：`~/Obsidian/todo/{STATUS}/{filename}`

**V1.0 简化 frontmatter**（10 字段，V1.x 后续按需扩）：

```yaml
---
type: todo
title: 续签劳动合同
created: 2026-06-03
updated: 2026-06-03
status: ACTIVE
priority: P1
due: 2026-06-15
project: "[[taibs-hr-portal-V1.0-ACTIVE]]"   # 可选, 关联 vault 已有 page
tags: [todo, work, hr]
source: user   # user | agent | cron
note: "合同 6/30 到期，提前 2 周走流程"
---

# 续签劳动合同

## 为什么
合同 6/30 到期，提前 2 周走流程。

## 验收
- [ ] HR 系统提交续签单
- [ ] 部门 leader 审批
- [ ] 收到新合同电子版

## 进度
- 2026-06-03 创建

## 相关
- [[taibs-hr-portal-V1.0-ACTIVE]]
- [[生活-合同-2024]]
```

### 步骤 6：自动校验（强制）

`todo_create.py` 写完文件后**立即**调 `validate_todo.py`：

```bash
python3 ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/scripts/validate_todo.py ~/Obsidian/todo/ACTIVE/2026-06-15-renew-contract-P1-ACTIVE.md
```

退出码：
- `0` = 通过
- `1` = 失败，**软告警**——文件保留，Agent 告诉用户问题并询问
- `2` = 文件找不到

**V1.0 必跑**（不要让用户配置；agent-config.md 里 `auto_validate: true` 是默认，false 才不跑）

### 步骤 7：主动巡检（Agent 责任）

Agent **会话开始时主动跑**：
```bash
python3 ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/scripts/daily_todo_check.py
```

读 `~/Obsidian/todo/alerts.md`，决定要不要推给用户：
- 0 个 due/逾期 → 静默（不发消息，避免噪音）
- ≥1 个 WARN/ERROR → Agent 用自己通道推（"你今天有 1 项 P1 到期，2 项 P2 距 due 2 天"）

---

## 完整示例

### 示例 1：建 todo

**用户输入：**
> "建个 todo 提醒我 6/15 续签劳动合同"

**AI Agent 执行**：
1. type = create
2. title = "续签劳动合同"
3. due = 2026-06-15（"6/15"）
4. note = "合同 6/30 到期"
5. priority: 没指定 → 走 5 层默认 → due 距今 12 天 → P1（见 config）
6. 调 todo_create.py → 返回 P1
7. 调 validate_todo.py → 退出 0
8. 写文件：`~/Obsidian/todo/ACTIVE/2026-06-15-renew-contract-P1-ACTIVE.md`

### 示例 2：标 done (V1.0.5 起, 走 done_helper.py)

**用户输入：**
> "续签合同完了"

**AI Agent 执行**:
1. 调 `done_helper.py --vault ~/Obsidian/todo --match "续签合同"`
2. `done_helper.py` 内部: 解析 ACTIVE/ 匹配文件 → 改 `status: DONE` / `updated: 今天` / `due: 今天` (filename 对齐) / 追加 `completed_on` + `original_due` / 进度区加 "完成" 行 → 原子写 → rename 到 DONE/ → 跑 validate_todo.py
3. 看到 `validate_exit: 0` → 告诉用户"已标 done, 移到 DONE/2026-06-12-renew-contract-P1-DONE.md"

**⚠️ V1.0.5 前 (V1.0.2 ~ V1.0.4) 的旧做法已废弃**:
> Agent 手动: 改 status=DONE → os.rename 到 DONE/ → 跑 validate. 手工改易踩 3 个坑 (中文 slug split / 进度区追加位置 / filename-due 对齐), 已被 done_helper.py 替代. 看到旧 SKILL.md / V1.0.4 引用的 agent 走老路, 立刻提示它用 helper.

### 示例 3：snooze

**用户输入：**
> "续签合同推到下周一"

**AI Agent 执行**：
1. 找 ACTIVE/ 匹配
2. 改 due: 下周一日期
3. 改 status: SNOOZED
4. 移到 SNOOZED/
5. 调 validate_todo.py

### 示例 4：list

**用户输入：**
> "我今天有什么要做的"

**AI Agent 执行**：
1. 调 daily_todo_check.py（不写 alerts.md，加 --list-only flag，V1.0 直接 scan 目录即可）
2. 列出 ACTIVE/ + 距 due ≤ 3 天的 SNOOZED/
3. 按 priority asc, due asc 排序
4. 告诉用户

---

## V1.0.2 脚本清单 (跟 finance V1.3.4 齐平)

**当前共有 6 个 stdlib 脚本** (V1.0.2 真实交付)：

| # | 脚本 | 用途 | 必跑时机 |
|---|------|------|----------|
| 1 | `validate_todo.py` | 单笔校验 | todo_create / done / snooze 后立即 |
| 2 | `todo_create.py` | 创建入口（5 层默认 + ask_on_2nd） | Agent 解析完用户输入 |
| 3 | `daily_todo_check.py` | 每日巡检（due 临近/逾期 + BLOCKED 超 3 天 → alerts.md） | launchd 每日 18:00 / Agent 会话开始 |
| 4 | `weekly_summary.py` | 本周复盘（新建/完成/净增/状态分布/priority 分布） | launchd 每周日 20:00 |
| 5 | `monthly_summary.py` | 月度报告（完成率/平均完成时间/滞销清单） | launchd 每月 28 号 21:00（脚本内判月末, 不是月末静默 skip） |
| 6 | `push_alerts.py` | 推送 alerts 摘要到 macOS 桌面通知（wecom/feishu/dingtalk webhook 配 `~/.obsidian-todo/push_config.json`） | daily/weekly/monthly 跑完后 Agent 调一次 |
| 7 | `done_helper.py` (V1.0.5 新) | 标 done 入口（--file 精确 / --match 模糊） | Agent 解析完"完成/标 done"后调，自动 rename / 改 frontmatter / 写 completed_on+original_due / 跑 validate |

**3 段 plist 模板** (`plist/com.todo.*.plist`)：

| Label | 触发 | 跑 |
|-------|------|-----|
| `com.todo.daily-integrity` | 每日 18:00 | `daily_todo_check.py` |
| `com.todo.weekly-summary` | 每周日 20:00 | `weekly_summary.py` |
| `com.todo.monthly-summary` | 每月 28 号 21:00 | `monthly_summary.py` |

**安装方式**: `bash ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/install.sh --install-plist` (真 cp + launchctl load, 不只问"要不要配", 学 finance V1.3.4 教训)

**V1.x 后续要做的脚本** (V1.0.2 不做, 故意列出让用户有 roadmap 预期)：

| 计划版本 | 脚本/能力 | 备注 |
|---------|-----------|------|
| V1.1 | snooze_helper.py / block_helper.py / cancel_helper.py | ~~done_helper.py~~ → V1.0.5 已交付 ✓; V1.1 继续做 snooze / block / cancel |
| V1.1 | snooze / block / cancel Agent 显式 helper | ~~done~~ → V1.0.5 已交付 ✓ |
| V1.1 | daily_integrity_check 读 `completed_on` / `original_due` 做"逾期完成率"统计 | 跟 §11 配套 |
| V1.4 | en 翻译 | 双语 (学 finance V1.3.2) |
| V1.5 | Dataview 仪表盘模板 | 用户在 Obsidian 里看 |

---

## 注意事项

1. **status 一律 5 选 1**：ACTIVE / DONE / BLOCKED / SNOOZED / CANCELED
2. **priority 一律 P0-P3**：P0=立刻（小时级）/ P1=今天-3 天 / P2=本周 / P3=有空再说
3. **due 格式**：`YYYY-MM-DD`，"今天"自动转当前日期
4. **文件位置**：`~/Obsidian/todo/{STATUS}/{filename}`
5. **必跑校验**：写完每笔后立即 validate_todo.py（Agent 责任，不依赖用户配置）
6. **配对 ID**：V1.0 不支持 dependency / parent-child（V1.2 加）
7. **学习机制**：ask_on_2nd，第一次静默第二次问（同 finance track V1.3.3）
8. **filename 日期 = frontmatter due (validate_todo.py 强校验)** —— V1.0.5 完整规则:
   - **ACTIVE/ SNOOZED/ BLOCKED/ CANCELED/** 文件:`{日期}` = due (todo_create.py 写入时已对齐)
   - **DONE/** 文件:`{日期}` = due = **完成日** (不是原 due).`done_helper.py` 标 done 时自动: (a) filename 前缀换完成日 (b) frontmatter `due` 同步改成完成日 (这样 validator 不会因"filename ≠ due"报红) (c) 原 due 移到 `original_due` 字段 (d) 新增 `completed_on` 字段. **Agent 不要手改 frontmatter + os.rename, 必跑 `done_helper.py`** (手改易踩坑: 中文 slug split / 进度区追加位置 / filename-due 对齐, 详见 V1.0.5 教训)
9. **跨系统假设必须 fact-check 后再给方案** — todo note 涉及跨 skill / 跨 vault / 外部系统状态时, **先建 `confirm-<目标>-real-state` 前置 todo 把 6 项核查完**, 再给实施建议。Evan 反馈"那你确认过finance项目目前的状态吗?"= 一次打脸,不能基于未验证假设给"4 步升级方案"。详见 `references/fact-check-before-recommendation.md`
10. **别把问题埋进选项表** — 给 Evan 总结 todo 状态时, **先一句话直说问题** (≤ 30 字), 再摆事实表格, 最后才放 A/B/C 选项。Evan 反馈"没看懂现在的问题"= 我把 P1 没闭环埋在了 4 段 todo 改名理由 + A/B/C 决策表里。详见 `references/fact-check-before-recommendation.md` § 配套规则
11. **DONE/ 文件的 `completed_on` + `original_due` 双日期字段 (V1.0.5 起, 必带)**:
    - `completed_on`: 完成日 (`done_helper.py` 写入, 默认今天, 可 `--completed-on` 覆盖)
    - `original_due`: 标 done 前的原 due (保逾期历史, e.g. 实际 6-12 完成 + 原 due 6-9 → 逾期 3 天的"账"才能查)
    - 这俩字段**只在 DONE/ 文件**出现, ACTIVE/ 不需要
    - `daily_integrity_check.py` V1.x 后续会读这俩字段做"逾期完成率"统计 (V1.1)

---

## 本地文件路径速查

| 文件 | 路径 |
|------|------|
| 本 SKILL.md | `~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/SKILL.md` (V1.0.1 重构后从 `zh/SKILL.md` 移到 skill 根) |
| 详细 AGENTS 工作流 | `~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/SKILL.md` § AGENTS 工作流 (V1.0 单文件设计) |
| todo 模板 | `~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/SKILL.md` § 模板 (V1.0 单文件设计) |
| 脚本 | `~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/scripts/` |
| 默认优先级 | `~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/config/default_priorities.yaml` |
| 安装脚本 | `~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/install.sh` |
| 用户配置哨兵 | `~/Obsidian/todo/todo-config.md` |
| **todo 数据** | `~/Obsidian/todo/{ACTIVE,DONE,BLOCKED,SNOOZED,CANCELED}/` |
| alerts 输出 | `~/Obsidian/todo/alerts.md` |
| 学习记录 | `~/.obsidian-todo/learning.json` |

---

## 首次安装说明 (V1.0.2)

```bash
# 1. 克隆项目到本地
git clone https://github.com/lovepigpanda/obsidian-personal-todo-tracker.git ~/Project/obsidian-personal-todo-tracker

# 2. 在 Obsidian vault 中创建 todo 目录
mkdir -p ~/Obsidian/todo/{ACTIVE,DONE,BLOCKED,SNOOZED,CANCELED}

# 3. 跑 install.sh (dry-run 模式先验证)
bash ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/install.sh --dry-run
bash ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/install.sh  # 真装

# 4. (V1.0.2 新) 启用定时主动 — 装 3 段 launchd plist
bash ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/install.sh --install-plist
launchctl list | grep com.todo.   # 验证 3 段都跑起来

# 5. (可选) 配 push 通道 — 飞书/微信 webhook
mkdir -p ~/.obsidian-todo
cat > ~/.obsidian-todo/push_config.json <<'EOF'
{
  "wecom": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY",
  "feishu": "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN"
}
EOF

# 6. AI Agent Onboarding
# 用户对 Agent 说"开始用 todo" / "装好了"
# Agent 自动跑 7 步 Onboarding, 生成 todo-config.md
```

> 注意：`ACTIVE/DONE/...` 目录是 todo 数据，**永远不上传**到 GitHub。

---

> Skill: obsidian-todo-track | Version: V1.0.5 (done_helper.py 落地 + 命名规则澄清 + §11 双日期字段) | For AI Agent use
> Project: https://github.com/lovepigpanda/obsidian-personal-todo-tracker
> 后续 V1.1+ roadmap 见「V1.x 后续要做的脚本」表格

## 🧪 V1.0.5 新增: done_helper.py 自测 (怎么测不要踩我踩过的坑)

**踩坑记录 (Evan 6-12 真实跑出来)**: 我第一次测 done_helper 时**直接拿 ACTIVE/ 真文件当测试数据**, 跑通后才发现 = 擅自给 Evan 标了一个他没说完成的事故. **正确做法: 用 /tmp 临时 vault 跑通再释放**.

**自测步骤** (Agent 调 done_helper 前先跑这个, 确认 OK 再动真 vault):

```bash
# 1. 准备临时 vault
TMPV=/tmp/done_helper_test
rm -rf $TMPV && mkdir -p $TMPV/{ACTIVE,DONE,BLOCKED,SNOOZED,CANCELED}
# 写一个测试 ACTIVE/ 文件
cat > $TMPV/ACTIVE/2026-06-09-测试-P0-ACTIVE.md <<'EOF'
---
type: todo
title: 测试
created: 2026-06-05
updated: 2026-06-05
status: ACTIVE
priority: P0
due: 2026-06-09
project:
tags: [todo]
source: user
note: 自测用
---

# 测试

## 验收
- [ ]

## 进度
- 2026-06-05 创建
EOF

# 2. 跑 done_helper (临时 vault 不会污染真 vault)
python3 ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/scripts/done_helper.py \
  --vault $TMPV --file "ACTIVE/2026-06-09-测试-P0-ACTIVE.md" --completed-on 2026-06-12

# 3. 验证
ls $TMPV/DONE/  # 应该有 2026-06-09-测试-P0-DONE.md (slug 保留 + status 换 DONE + 日期换完成日)
python3 ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/scripts/validate_todo.py \
  $TMPV/DONE/2026-06-09-测试-P0-DONE.md  # 应该 0 errors

# 4. 清理
rm -rf $TMPV
```

**铁律**: 写新 helper / 改 frontmatter schema 时, **永远先 /tmp 自测**, 不要拿真 vault 试错. 学 Evan 6-12 那次事故, 真 vault 错动一笔 = 至少 1 轮 rollback 才能恢复.
