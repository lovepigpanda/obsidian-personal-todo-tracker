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

  📌 定位：Agent 不是计算器，是**主动管家**。
  - 主动跑 daily_todo_check.py，不等用户问"我今天有什么"
  - 主动给 due 临近的 todo 发提醒
  - 主动问"这个 todo 要不要 snooze 到下周"
  - 主动问"BLOCKED 状态超过 3 天的 todo 怎么办"
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
version: V1.0
# V1.0 = 最小可落地 (M1)
#   交付: SKILL.md + install.sh + 2 个 stdlib 脚本 (validate_todo / todo_create)
#         + 1 个每日巡检 (daily_todo_check) + 1 个默认优先级配置 (default_priorities.yaml)
#   故意不做: 6 段 plist 模板 / weekly / monthly / 多语言 en / aweskill 同步 / Dataview
#   后续: V1.1 plist 模板真交付 (学 finance track V1.3.4 教训);
#         V1.2 weekly_summary.py; V1.3 monthly_summary.py; V1.4 en 翻译;
#         V1.5 aweskill 同步; V1.6 Dataview 仪表盘
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

### V1.0 范围说明

| 类别 | V1.0 真实交付 | 故意不做（V1.x 后续） |
|------|---------------|---------------------|
| 脚本 | validate_todo / todo_create / daily_todo_check (3 个) | weekly_summary / monthly_summary / snooze_helper / done_helper / due_reminder / 等 |
| 文档 | zh SKILL.md + zh README.md | en SKILL / en README |
| 模板 | 文件名规范（脚本生成） | 手写 .md 模板 |
| 安装 | install.sh 一键 cp + dry-run | aweskill 同步（V1.5） |
| 定时 | 无（Agent 会话内主动跑） | 6 段 plist 模板（V1.1） |
| 仪表盘 | alerts.md（脚本写）+ Agent 主动推送 | Dataview 仪表盘（V1.6） |

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

## 🎯 Agent 定位: 主动管家, 不是被动工具

| 被动 ❌ | 主动 ✅ |
|---------|---------|
| 用户说"建个 todo"才工作 | 会话开始就主动跑 daily_todo_check 拿今日 todo |
| 等用户问"我今天做什么" | 主动说"你今天有 3 项 P1, 1 项已逾期" |
| 用户配 cron / launchd | **V1.1 Agent 主动问**"要不要我帮你配每日定时?" |
| 用户配 webhook 通知 | **Agent 用自己已有的通道**主动推送 |
| 等用户发现过期 todo | 提前发现并告警 |

**判断标准**: 如果一件事**用户必须主动做**才能享受, 那就是 Agent 失职。

**⚠️ V1.0 已知承诺未交付**: 6 段 plist 模板在 V1.1 真交付（学 finance track V1.1.4→V1.3.3 教训——4 个版本承诺没真配过）。V1.0 文档明确说"等用户问"才配，**不假装已经配好**。

---

## 🚀 步骤 0: Onboarding (新用户引导, 7 步)

**触发**: 用户第一次加载本技能（或说"装好了"/"开始用"）。

**不要默默开始建 todo**。先做 7 步配置：

1. **确认 vault 目录** — 默认 `~/Obsidian/todo`，确认或改
2. **验证/clone 仓库** — 检查 `~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/scripts/` 存在；不存在就 `git clone https://github.com/lovepigpanda/obsidian-personal-todo-tracker.git`（V1.0 必须仓库方式，不走 aweskill）
3. **验证必需文件** — 检查 `todo-config.md` / `alerts.md` / `ACTIVE|DONE|BLOCKED|SNOOZED|CANCELED/` 5 个目录在，缺则 Agent 主动帮创建
4. **引导填 todo-config.md** — 问"你想怎么分工作/生活"，帮写哨兵文件
5. **⚠️ V1.0 不配 plist**（V1.1 真配）— 明确告诉用户"现在你得手动跑 daily_todo_check.py，V1.1 我会真交付 6 段 plist 模板"
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
| 完成了 / done / 标完成 | done | "合同续签完了，标 done" |
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
python3 scripts/todo_create.py \
  --vault ~/Obsidian/todo \
  --type create \
  --title "续签劳动合同" \
  --due 2026-06-15 \
  --note "合同 6/30 到期"
```

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
{date}-{slug}-{priority}-{STATUS}.md
```

slug = title 的连字符小写版本（中文保留，英文 lowercase）。

示例：
- `ACTIVE/2026-06-15-renew-contract-P1-ACTIVE.md`
- `DONE/2026-06-10-renew-contract-P1-DONE.md`

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
python3 scripts/validate_todo.py ~/Obsidian/todo/ACTIVE/2026-06-15-renew-contract-P1-ACTIVE.md
```

退出码：
- `0` = 通过
- `1` = 失败，**软告警**——文件保留，Agent 告诉用户问题并询问
- `2` = 文件找不到

**V1.0 必跑**（不要让用户配置；agent-config.md 里 `auto_validate: true` 是默认，false 才不跑）

### 步骤 7：主动巡检（Agent 责任）

Agent **会话开始时主动跑**：
```bash
python3 scripts/daily_todo_check.py
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

### 示例 2：标 done

**用户输入：**
> "续签合同完了"

**AI Agent 执行**：
1. 搜 ACTIVE/ 找 "续签合同" 匹配的 .md
2. 找到 `ACTIVE/2026-06-15-renew-contract-P1-ACTIVE.md`
3. 改 status: DONE, updated: 今天
4. `git mv` (or os.rename) 到 `DONE/` 目录
5. 调 validate_todo.py → 退出 0
6. 告诉用户"已标 done，移到 DONE/"

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

## V1.0 脚本清单

**当前共有 3 个 stdlib 脚本** (V1.0 真实交付)：

| # | 脚本 | 用途 | 必跑时机 |
|---|------|------|----------|
| 1 | `validate_todo.py` | 单笔校验 | todo_create / done / snooze 后立即 |
| 2 | `todo_create.py` | 创建入口（5 层默认 + ask_on_2nd） | Agent 解析完用户输入 |
| 3 | `daily_todo_check.py` | 每日巡检（due 临近/逾期 → alerts.md） | Agent 会话开始 / 用户问 "我今天做什么" |

**V1.x 后续要做的脚本**（V1.0 不做，故意列出让用户有 roadmap 预期）：

| 计划版本 | 脚本 | 备注 |
|---------|------|------|
| V1.1 | snooze_helper.py / done_helper.py | done / snooze / block / cancel 走显式脚本而非 Agent 改文件 |
| V1.1 | 6 段 plist 模板（学 finance track V1.3.4） | 真交付，不只问"要不要配" |
| V1.2 | weekly_summary.py | 周末复盘 |
| V1.3 | monthly_summary.py | 月末自检 |
| V1.4 | en 翻译 | 双语 |
| V1.5 | aweskill 同步 | skills/ 投影到中心 store |
| V1.6 | Dataview 仪表盘模板 | 用户在 Obsidian 里看 |

---

## 注意事项

1. **status 一律 5 选 1**：ACTIVE / DONE / BLOCKED / SNOOZED / CANCELED
2. **priority 一律 P0-P3**：P0=立刻（小时级）/ P1=今天-3 天 / P2=本周 / P3=有空再说
3. **due 格式**：`YYYY-MM-DD`，"今天"自动转当前日期
4. **文件位置**：`~/Obsidian/todo/{STATUS}/{filename}`
5. **必跑校验**：写完每笔后立即 validate_todo.py（Agent 责任，不依赖用户配置）
6. **配对 ID**：V1.0 不支持 dependency / parent-child（V1.2 加）
7. **学习机制**：ask_on_2nd，第一次静默第二次问（同 finance track V1.3.3）

---

## 本地文件路径速查

| 文件 | 路径 |
|------|------|
| 本 SKILL.md | `~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/zh/SKILL.md` |
| 详细 AGENTS 工作流 | `~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/zh/AGENTS/` (V1.0 占位) |
| todo 模板 | `~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/zh/Templates/` (V1.0 占位) |
| 脚本 | `~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/scripts/` |
| 默认优先级 | `~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/config/default_priorities.yaml` |
| 安装脚本 | `~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/install.sh` |
| 用户配置哨兵 | `~/Obsidian/todo/todo-config.md` |
| **todo 数据** | `~/Obsidian/todo/{ACTIVE,DONE,BLOCKED,SNOOZED,CANCELED}/` |
| alerts 输出 | `~/Obsidian/todo/alerts.md` |
| 学习记录 | `~/.obsidian-todo/learning.json` |

---

## 首次安装说明

```bash
# 1. 克隆项目到本地
git clone https://github.com/lovepigpanda/obsidian-personal-todo-tracker.git ~/Project/obsidian-personal-todo-tracker

# 2. 在 Obsidian vault 中创建 todo 目录
mkdir -p ~/Obsidian/todo/{ACTIVE,DONE,BLOCKED,SNOOZED,CANCELED}

# 3. 跑 install.sh (V1.0 dry-run 模式先验证)
bash ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/install.sh --dry-run
bash ~/Project/obsidian-personal-todo-tracker/skills/obsidian-todo-track/install.sh  # 真装

# 4. AI Agent Onboarding
# 用户对 Agent 说"开始用 todo" / "装好了"
# Agent 自动跑 7 步 Onboarding, 生成 todo-config.md
```

> 注意：`ACTIVE/DONE/...` 目录是 todo 数据，**永远不上传**到 GitHub。

---

> Skill: obsidian-todo-track | Version: V1.0 (最小可落地) | For AI Agent use
> Project: https://github.com/lovepigpanda/obsidian-personal-todo-tracker
> 后续 V1.1+ roadmap 见「V1.x 后续要做的脚本」表格
