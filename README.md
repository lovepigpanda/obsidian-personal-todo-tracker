# Obsidian Personal Todo Tracker

> 用 AI Agent 帮你在 Obsidian vault 里管 todo — 跟 [`obsidian-personal-finance-tracker`](https://github.com/lovepigpanda/obsidian-personal-finance-tracker) 同款架构 (V1.0 最小可落地)

[English](#english) | [中文](#中文)

---

## 中文

### 这是什么

一个**纯本地**的 todo 管理系统, 数据存 Obsidian vault, Agent 帮你解析自然语言/主动推送提醒。

跟主流 todo app (Todoist / TickTick / Things) 的核心区别:
- ✅ **数据在自己手里** — 纯 markdown, 跟笔记放一起
- ✅ **AI Agent 主动管家** — 不是计算器, 是会主动催你的助理
- ✅ **零依赖** — Python 3.8+ 标准库, 不用 pip 装包
- ✅ **跟 vault wiki 互通** — `[[wikilink]]` 关联到 `~/Obsidian/work/...` / `life/...`

### V1.0 范围 (最小可落地)

| 已交付 ✅ | 故意不做 (V1.x 后续) |
|-----------|---------------------|
| 3 个 stdlib 脚本 (validate / create / daily_check) | 6 段 plist 模板 (V1.1 真交付) |
| 1 个 config (default_priorities.yaml) | weekly_summary (V1.2) |
| install.sh 一键装 | monthly_summary (V1.3) |
| SKILL.md (zh) | en 翻译 (V1.4) |
| | aweskill 同步 (V1.5) |
| | Dataview 仪表盘 (V1.6) |

### 5 步安装

```bash
# 1. 克隆仓库
git clone https://github.com/lovepigpanda/obsidian-personal-todo-tracker.git ~/Project/obsidian-personal-todo-tracker
cd ~/Project/obsidian-personal-todo-tracker

# 2. dry-run 验证 (不真改文件)
bash install.sh --dry-run

# 3. 真装
bash install.sh

# 4. 跟 AI Agent 说"开始用 todo" 触发 Onboarding 7 步
#    Agent 会写 ~/Obsidian/todo/todo-config.md 哨兵文件

# 5. 试一笔
#    跟 Agent 说"建个 todo 提醒我 6/15 续签合同"
```

### 自定义 vault 路径

```bash
# 默认装到 ~/Obsidian/todo, 可改
bash install.sh --vault ~/Documents/my-todo

# 环境变量也行
VAULT=~/Documents/my-todo bash install.sh
```

### 数据结构

```
~/Obsidian/todo/
├── todo-config.md                ← Onboarding 哨兵 (Agent 写, 用户可改)
├── alerts.md                     ← 每日巡检输出 (Agent 写)
├── default_priorities.yaml       ← 优先级规则 (跟仓库 config/ MD5 一致)
├── ACTIVE/                       ← 进行中
│   └── 2026-06-15-renew-contract-P1-ACTIVE.md
├── DONE/                         ← 完成
├── BLOCKED/                      ← 阻塞
├── SNOOZED/                      ← 暂缓
└── CANCELED/                     ← 取消
```

每个 todo 文件名格式: `{due}-YYYY-MM-DD-{slug}-P{n}-{STATUS}.md`

### 跟 finance track 的对比

| 维度 | finance track V1.3.4 | todo track V1.0 |
|------|---------------------|-----------------|
| 类型 | 记账 (expense/income/transfer) | 待办 (task only) |
| 状态 | ACTIVE (主) + DONE (尾) | 5 档: ACTIVE/DONE/BLOCKED/SNOOZED/CANCELED |
| 优先级 | 无 | P0/P1/P2/P3 |
| 校验 | transfer 配对守恒 | 文件名/frontmatter 一致性 |
| 5 层默认 | 5 层账户解析 | 5 层 priority 解析 |
| ask_on_2nd | ✅ (账户学习) | ✅ (priority 学习) |
| plist 模板 | 6 段真交付 (V1.3.4) | **V1.1 才真交付** (V1.0 留空白) |
| 脚本数 | 10 个 (V1.3.4) | 3 个 (V1.0 最小) |
| 多语言 | zh + en (V1.3.2) | zh only (V1.4 才加 en) |

### V1.0 学到的 4 个教训 (从 finance track V1.1.4→V1.3.3 失败学)

1. **V1.0 文档明确说"V1.0 不配 plist"**, 不假装"等用户问才配" (V1.0→V1.1 才真交付)
2. **6 段 plist 模板** 等 V1.1 真做出来再放, 别像 finance V1.1.4 承诺 4 个版本没真配过
3. **V1.0 范围刻意收窄**: 只 3 个脚本 + 1 个 config, 不堆功能
4. **agent-config.md / todo-config.md 哨兵强制**: 文件存在 + `onboarded: true` 才算真初始化

### V1.x Roadmap

| 版本 | 计划 | 关键交付 |
|------|------|----------|
| V1.0 (现在) | 最小可落地 | 3 脚本 + config + install.sh |
| V1.1 | plist 真交付 | 6 段 launchd plist 模板 (学 finance V1.3.4) |
| V1.2 | weekly 复盘 | weekly_summary.py + DONE 归档统计 |
| V1.3 | monthly 自检 | monthly_summary.py + 储蓄率/分类汇总 |
| V1.4 | en 翻译 | 跟 finance V1.3.2 一样 zh + en 同步 |
| V1.5 | aweskill 同步 | skills/ 投影到中心 store |
| V1.6 | Dataview 仪表盘 | vault 里看 ACTIVE/DUE 聚合 |

### 验证 (V1.0 范围)

```bash
# 仓库端自测
cd ~/Project/obsidian-personal-todo-tracker
python3 scripts/lib/parsers.py                    # parsers unit-test
python3 scripts/validate_todo.py scripts/         # 退出 1 (不是 todo, 预期)

# 真实 todo 校验
python3 scripts/validate_todo.py ~/Obsidian/todo/ACTIVE/ --recursive

# 每日巡检
python3 scripts/daily_todo_check.py --list-only
cat ~/Obsidian/todo/alerts.md
```

### 跟其他 todo 工具的关系

| 工具 | 这个项目 | Todoist | Obsidian Tasks 插件 | Things |
|------|----------|---------|--------------------|--------|
| 数据位置 | 本地 markdown | 云端 | 本地 markdown | 本地数据库 |
| AI Agent 主动 | ✅ | ❌ | ❌ | ❌ |
| 跨平台 | 任何能跑 Python | 客户端 | 任何 Obsidian | macOS/iOS |
| 跟 vault 互通 | ✅ (wikilink) | ❌ | ✅ | ❌ |
| 月费 | 免费 | $4/月 | 免费 | $50 一次 |

**这个项目的定位**: 已经有 Obsidian vault + AI Agent 的人, 不想再装一个 todo app。

---

## English

> 暂未翻译 (V1.4 计划), 先看 [中文](#中文)
